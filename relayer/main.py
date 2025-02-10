import asyncio
import json
import logging
from aiohttp import web
import aiosqlite
import base58
from web3 import AsyncWeb3, AsyncHTTPProvider
import os
import subprocess

logger = logging.getLogger(__name__)
logger.info("Starting application")

logger.info("Changing to base58bruteforce directory")
os.chdir("base58bruteforce")
logger.info("Building base58bruteforce")
os.system("cargo build --release")
logger.info("Changing back to main directory")
os.chdir("..")
logger.info("Copying binary")
os.system("cp base58bruteforce/target/release/base58bruteforce binary")

# ---------------------------
# Configuration
# ---------------------------
logger.info("Loading configuration files")
# Load ABIs and configuration.
FACTORY_ABI = json.load(open("../out/ReceiverFactory.json"))["abi"]
logger.info("Loaded Factory ABI")
RECEIVER_ABI = json.load(open("../out/UntronReceiver.json"))["abi"]
logger.info("Loaded Receiver ABI")
ERC20_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"}
        ],
        "name": "Transfer",
        "type": "event"
    }
]
logger.info("Defined ERC20 ABI")

CONFIG = json.load(open("config.json"))
logger.info(f"Loaded config from config.json with RPC URL {CONFIG['rpc_url']}")
DB_FILENAME = "receivers.db"

# ---------------------------
# Setup Logging
# ---------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------
# Setup Web3
# ---------------------------
logger.info(f"Initializing Web3 with RPC URL: {CONFIG['rpc_url']}")
w3 = AsyncWeb3(AsyncHTTPProvider(CONFIG["rpc_url"]))
logger.info(f"Initializing factory contract at address: {CONFIG['factory_address']}")
factory_contract = w3.eth.contract(address=CONFIG["factory_address"], abi=FACTORY_ABI)

# Global contract variables
implementation_contract = None
usdt_contract = None
usdc_contract = None

async def setup_contracts():
    global implementation_contract, usdt_contract, usdc_contract
    logger.info("Setting up contract instances")
    
    implementation_address = await factory_contract.functions.receiverImplementation().call()
    logger.info(f"Implementation contract address: {implementation_address}")
    implementation_contract = w3.eth.contract(address=implementation_address, abi=RECEIVER_ABI)

    usdt_address = await implementation_contract.functions.usdt().call()
    logger.info(f"USDT contract address: {usdt_address}")
    usdt_contract = w3.eth.contract(address=usdt_address, abi=ERC20_ABI)

    usdc_address = await implementation_contract.functions.usdc().call()
    logger.info(f"USDC contract address: {usdc_address}")
    usdc_contract = w3.eth.contract(address=usdc_address, abi=ERC20_ABI)

logger.info("Initializing account from private key")
account = w3.eth.account.from_key(CONFIG["private_key"])
logger.info(f"Account address: {account.address}")

# ---------------------------
# Database Setup
# ---------------------------
async def setup_database():
    logger.info(f"Setting up database: {DB_FILENAME}")
    async with aiosqlite.connect(DB_FILENAME) as db:
        # Create receivers table
        logger.info("Creating receivers table if not exists")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS receivers (
                tron_address TEXT PRIMARY KEY,
                receiver_address TEXT,
                resolved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()
        logger.info("Database setup complete")

# ---------------------------
# Helper Functions
# ---------------------------
async def fix_case(address: str) -> str:
    """
    Fixes the case of a Base58 address by running the base58bruteforce program
    and capturing its output.
    """
    logger.info(f"Fixing case for address: {address}")
    result = subprocess.run(["./binary", address], 
                          capture_output=True, 
                          text=True)
    if result.stdout:
        fixed = result.stdout.strip()
        logger.info(f"Fixed case result: {fixed}")
        return fixed
    logger.warning("No output from case fixing binary")
    return ""

async def generate_receiver_address(tron_address: str) -> str:
    """
    Calls the factory's generateReceiverAddress view function.
    Expects tron_address to be a hex string (with or without "0x") representing 20 bytes.
    """
    logger.info(f"Generating receiver address for Tron address: {tron_address}")
    tron_bytes = base58.b58decode_check(tron_address)[1:]
    logger.info(f"Decoded Tron address bytes: {tron_bytes.hex()}")
    receiver_address = await factory_contract.functions.generateReceiverAddress(tron_bytes).call()
    logger.info(f"Generated receiver address: {receiver_address}")
    return receiver_address

async def store_resolved_pair(tron_address: str, receiver_address: str):
    """
    Stores the Tron->receiver mapping in the SQLite database.
    """
    logger.info(f"Storing resolved pair - Tron: {tron_address}, Receiver: {receiver_address}")
    async with aiosqlite.connect(DB_FILENAME) as db:
        await db.execute(
            "INSERT OR IGNORE INTO receivers (tron_address, receiver_address) VALUES (?, ?)",
            (tron_address, receiver_address)
        )
        await db.commit()
        logger.info("Successfully stored resolved pair")

# ---------------------------
# HTTP Endpoint Handlers
# ---------------------------
async def resolve_handler(request: web.Request):
    """
    Expects JSON input: { "tron_address": "..." }
    Fixes the case, computes the receiver address using the factory,
    stores the mapping, and returns the result.
    """
    logger.info("Received resolve request")
    try:
        data = await request.json()
        logger.info(f"Request data: {data}")
        domain = data.get("data")
        if not domain:
            logger.error("Missing tron_address in request")
            return web.json_response({"message": "Missing tron_address"}, status=404)
        try:
            domain = bytes.fromhex(domain.lstrip("0x"))
            logger.info(f"Decoded domain bytes: {domain.hex()}")
        except Exception as e:
            logger.error(f"Failed to decode domain: {e}")
            return web.json_response({"message": f"Invalid domain: {e}"}, status=404)
        lowercased_tron_address = domain[1:domain[0]+1].decode().lower()
        logger.info(f"Extracted Tron address: {lowercased_tron_address}")
        if len(lowercased_tron_address) not in range(25, 35):
            logger.error(f"Invalid Tron address length: {len(lowercased_tron_address)}")
            return web.json_response({"message": "Invalid tron_address"}, status=404)
        fixed_tron_address = await fix_case(lowercased_tron_address)
        logger.info(f"Fixed case Tron address: {fixed_tron_address}")
        receiver_address = await generate_receiver_address(fixed_tron_address)
        logger.info(f"Generated receiver address: {receiver_address}")
        await store_resolved_pair(fixed_tron_address, receiver_address)
        result = "0x" + (bytes([domain[0]]) + fixed_tron_address.encode() + domain[domain[0]+1:]).hex()
        logger.info(f"Resolved {lowercased_tron_address} to {result}")
        return web.json_response({
            "data": result
        })
    except Exception as e:
        logger.exception("Error in resolve_handler")
        return web.json_response({"message": str(e)}, status=404)

async def list_receivers(request: web.Request):
    """
    Returns a list of all stored Tron -> receiver mappings.
    """
    logger.info("Received list_receivers request")
    try:
        async with aiosqlite.connect(DB_FILENAME) as db:
            logger.info("Querying receivers table")
            async with db.execute("SELECT tron_address, receiver_address, resolved_at FROM receivers") as cursor:
                rows = await cursor.fetchall()
                result = [{"tron_address": row[0], "receiver_address": row[1], "resolved_at": row[2]} for row in rows]
                logger.info(f"Found {len(result)} receiver mappings")
        return web.json_response(result)
    except Exception as e:
        logger.exception("Error in list_receivers")
        return web.json_response({"message": str(e)}, status=404)

# ---------------------------
# Blockchain Interaction
# ---------------------------
async def call_deploy(tron_address: str):
    """
    Calls the factory contract's deploy(destinationTronAddress: bytes20) function.
    """
    logger.info(f"Deploying receiver for Tron address: {tron_address}")
    try:
        tron_bytes = bytes.fromhex(tron_address[2:]) if tron_address.startswith("0x") else base58.b58decode_check(tron_address)[1:]
        logger.info(f"Decoded Tron address bytes: {tron_bytes.hex()}")
        nonce = await w3.eth.get_transaction_count(account.address)
        logger.info(f"Got nonce: {nonce}")
        gas_price = await w3.eth.gas_price
        logger.info(f"Got gas price: {gas_price}")
        tx = await factory_contract.functions.deploy(tron_bytes).build_transaction({
            "chainId": await w3.eth.chain_id,
            "gas": 300000,  # Adjust gas limit as needed.
            "gasPrice": gas_price,
            "nonce": nonce,
        })
        logger.info(f"Built transaction: {tx}")
        signed_tx = account.sign_transaction(tx)
        logger.info("Transaction signed")
        tx_hash = await w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        logger.info(f"Called deploy() for tron_address {tron_address}, tx hash: {tx_hash.hex()}")
        receipt = await w3.eth.wait_for_transaction_receipt(tx_hash)
        logger.info(f"Transaction receipt: {receipt}")
        return receipt
    except Exception as e:
        logger.exception(f"Error calling deploy() for tron_address {tron_address}: {e}")
        return None

async def call_intron(receiver_address: str):
    """
    Calls the intron() function on the receiver contract at the given address.
    """
    logger.info(f"Calling intron() on receiver: {receiver_address}")
    try:
        receiver_contract = w3.eth.contract(address=receiver_address, abi=RECEIVER_ABI)
        nonce = await w3.eth.get_transaction_count(account.address)
        logger.info(f"Got nonce: {nonce}")
        gas_price = await w3.eth.gas_price
        logger.info(f"Got gas price: {gas_price}")
        tx = await receiver_contract.functions.intron().build_transaction({
            "chainId": await w3.eth.chain_id,
            "gas": 300000,
            "gasPrice": gas_price,
            "nonce": nonce,
        })
        logger.info(f"Built transaction: {tx}")
        signed_tx = account.sign_transaction(tx)
        logger.info("Transaction signed")
        tx_hash = await w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        logger.info(f"Called intron() on {receiver_address}, tx hash: {tx_hash.hex()}")
        receipt = await w3.eth.wait_for_transaction_receipt(tx_hash)
        logger.info(f"Transaction receipt: {receipt}")
        return receipt
    except Exception as e:
        logger.exception(f"Error calling intron() on {receiver_address}: {e}")
        return None

async def save_last_block(chain_name: str, block_number: int):
    """Save the last processed block number for a given chain."""
    logger.info(f"Saving last block {block_number} for chain {chain_name}")
    os.makedirs("backups", exist_ok=True)
    with open(f"backups/last_block_{chain_name}.txt", "w") as f:
        f.write(str(block_number))
    logger.info(f"Saved last block {block_number} for chain {chain_name}")

async def load_last_block(chain_name: str) -> int:
    """Load the last processed block number for a given chain."""
    logger.info(f"Loading last block for chain {chain_name}")
    try:
        with open(f"backups/last_block_{chain_name}.txt", "r") as f:
            block = int(f.read().strip())
            logger.info(f"Loaded last block {block} for chain {chain_name}")
            return block
    except FileNotFoundError:
        logger.info(f"No last block found for chain {chain_name}, starting from 0")
        return 0

def address_to_topic(address: str) -> str:
    """
    Convert an Ethereum address (0x prefixed, 40 hex digits) 
    to a 32-byte left-padded hex string (0x + 64 hex digits)
    """
    if address.startswith("0x"):
        address = address[2:]
    # Pad the address to 64 hex digits
    return "0x" + address.rjust(64, "0")

async def poll_transfers():
    """
    Background task that polls for Transfer events (from USDT and USDC contracts)
    whose 'to' field matches any receiver address stored in the DB.
    If a transfer is detected:
      - Check if the receiver contract is deployed.
      - If not, call deploy() on the factory (using the corresponding Tron address).
      - After a successful deployment, or if already deployed, call intron() on the receiver.
    """
    logger.info("Starting transfer polling background task")

    # Get Transfer event signatures
    transfer_event_signature = w3.keccak(text="Transfer(address,address,uint256)").hex()
    logger.info(f"Transfer event signature: {transfer_event_signature}")

    while True:
        try:
            # Retrieve current mappings: key = receiver_address, value = tron_address
            logger.info("Retrieving current receiver mappings from database")
            async with aiosqlite.connect(DB_FILENAME) as db:
                async with db.execute("SELECT tron_address, receiver_address FROM receivers") as cursor:
                    rows = await cursor.fetchall()
                    mapping = {row[1]: row[0] for row in rows}
                    receiver_addresses = list(mapping.keys())
                    logger.info(f"Found {len(receiver_addresses)} receiver addresses to monitor")

            if receiver_addresses:
                for token_contract in [usdt_contract, usdc_contract]:
                    token_name = "USDT" if token_contract.address == usdt_contract.address else "USDC"
                    logger.info(f"Processing {token_name} transfers")
                    
                    # Load last processed block
                    last_block = await load_last_block(f"{token_name}_transfers") or await w3.eth.block_number
                    current_block = await w3.eth.block_number
                    logger.info(f"Last processed block: {last_block}, current block: {current_block}")

                    if current_block > last_block:
                        chunk_size = 1000  # Process logs in chunks
                        from_block = last_block + 1

                        while from_block <= current_block:
                            to_block = min(from_block + chunk_size - 1, current_block)
                            logger.info(f"Processing blocks {from_block} to {to_block}")
                            
                            try:
                                # Get logs for the chunk
                                logger.info(f"Fetching {token_name} transfer logs")
                                logs = await w3.eth.get_logs({
                                    "fromBlock": from_block,
                                    "toBlock": to_block,
                                    "address": token_contract.address,
                                    "topics": [
                                        f"0x{transfer_event_signature}",
                                        None,
                                        [address_to_topic(x) for x in receiver_addresses]
                                    ]
                                })
                                logger.info(f"Found {len(logs)} transfer logs")

                                for log in logs:
                                    try:
                                        # Process the Transfer event
                                        event = token_contract.events.Transfer().process_log(log)
                                        to_address = event.args.to
                                        value = event.args.value
                                        logger.info(f"Detected Transfer of {value} {token_name} to {to_address}")
                                        
                                        tron_address = mapping.get(to_address)
                                        if not tron_address:
                                            logger.error(f"No tron_address mapping found for receiver {to_address}")
                                            continue

                                        # Check if the receiver contract is deployed
                                        code = await w3.eth.get_code(to_address)
                                        if code in (b'', '0x', b'0x'):
                                            logger.info(f"Receiver contract {to_address} not deployed; deploying now for tron_address {tron_address}")
                                            deploy_receipt = await call_deploy(tron_address)
                                            if deploy_receipt is None:
                                                logger.error(f"Deployment failed for tron_address {tron_address}")
                                                continue
                                            
                                            # Wait for deployment to propagate
                                            logger.info("Waiting for deployment to propagate")
                                            await asyncio.sleep(5)
                                            code = await w3.eth.get_code(to_address)
                                            if code in (b'', '0x', b'0x'):
                                                logger.error(f"Deployment did not result in contract code at {to_address}")
                                                continue

                                        # Call intron() once receiver is deployed
                                        logger.info(f"Creating task to call intron() on {to_address}")
                                        asyncio.create_task(call_intron(to_address))

                                    except Exception as e:
                                        logger.exception(f"Error processing transfer event: {e}")
                                        continue

                            except Exception as e:
                                logger.exception(f"Error fetching logs for blocks {from_block}-{to_block}: {e}")
                                # Reduce chunk size on error and retry
                                chunk_size = max(chunk_size // 2, 100)
                                logger.info(f"Reduced chunk size to {chunk_size}")
                                continue

                            # Update last processed block
                            logger.info(f"Updating last processed block to {to_block}")
                            await save_last_block(f"{token_name}_transfers", to_block)
                            from_block = to_block + 1

        except Exception as e:
            logger.exception(f"Error while polling transfers: {e}")
        
        logger.info("Sleeping for 2 seconds before next polling iteration")
        await asyncio.sleep(2)  # Poll every 2 seconds

# ---------------------------
# App Initialization
# ---------------------------
async def init_app():
    logger.info("Initializing web application")
    app = web.Application()
    app.router.add_post("/resolve", resolve_handler)
    app.router.add_get("/receivers", list_receivers)
    logger.info("Web application routes configured")
    return app

async def main():
    logger.info("Starting main application")
    await setup_database()
    await setup_contracts()
    app = await init_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 80)
    await site.start()
    logger.info("Server started at http://0.0.0.0:80")
    logger.info("Starting transfer polling task")
    asyncio.create_task(poll_transfers())
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        logger.info("Starting application main loop")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")