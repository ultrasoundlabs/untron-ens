import asyncio
import json
import logging
from aiohttp import web
import aiosqlite
from web3 import AsyncWeb3, AsyncHTTPProvider

# ---------------------------
# Configuration
# ---------------------------
# FACTORY_ABI should include at least generateReceiverAddress(bytes20) view method.
FACTORY_ABI = json.load(open("../out/ReceiverFactory.json"))["abi"]
# RECEIVER_ABI should include at least the intron() function.
RECEIVER_ABI = json.load(open("../out/UntronReceiver.json"))["abi"]
# Minimal ERC20 ABI for Transfer events
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

CONFIG = json.load(open("config.json"))

DB_FILENAME = "receivers.db"

# ---------------------------
# Setup Logging
# ---------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------
# Setup Web3
# ---------------------------
w3 = AsyncWeb3(AsyncHTTPProvider(CONFIG["rpc_url"]))
# Create contract instances
factory_contract = w3.eth.contract(address=CONFIG["factory_address"], abi=FACTORY_ABI)

# Fetch and print implementation address
implementation_address = factory_contract.functions.receiverImplementation().call()
print(f"Implementation contract address: {implementation_address}")
implementation_contract = w3.eth.contract(address=implementation_address, abi=RECEIVER_ABI)

# Fetch and print token addresses
usdt_address = implementation_contract.functions.usdt().call()
print(f"USDT contract address: {usdt_address}")
usdt_contract = w3.eth.contract(address=usdt_address, abi=ERC20_ABI)

usdc_address = implementation_contract.functions.usdc().call() 
print(f"USDC contract address: {usdc_address}")
usdc_contract = w3.eth.contract(address=usdc_address, abi=ERC20_ABI)

account = w3.eth.account.from_key(CONFIG["private_key"])

# ---------------------------
# Helper Functions
# ---------------------------
async def fix_case(address: str) -> str:
    """
    Placeholder function to fix the case of an address.
    For now, just return the input.
    """
    # TODO: implement proper case fixing logic.
    return address

async def generate_receiver_address(tron_address: str) -> str:
    """
    Calls the factory contract's generateReceiverAddress method.
    Assumes tron_address is a hex string (with or without the 0x prefix) representing 20 bytes.
    """
    # Convert to a 20-byte value.
    addr_clean = tron_address[2:] if tron_address.startswith("0x") else tron_address
    tron_bytes = bytes.fromhex(addr_clean)
    receiver_address = await factory_contract.functions.generateReceiverAddress(tron_bytes).call()
    return receiver_address

async def store_resolved_pair(tron_address: str, receiver_address: str):
    """
    Stores the Tron->receiver mapping in the SQLite database.
    """
    async with aiosqlite.connect(DB_FILENAME) as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS receivers (tron_address TEXT PRIMARY KEY, receiver_address TEXT, resolved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        await db.execute(
            "INSERT OR IGNORE INTO receivers (tron_address, receiver_address) VALUES (?, ?)",
            (tron_address, receiver_address)
        )
        await db.commit()

# ---------------------------
# HTTP Endpoint Handlers
# ---------------------------
async def resolve_handler(request: web.Request):
    """
    Receives a JSON payload with a Tron address, fixes its case, computes the receiver address,
    stores the mapping, and returns the result.
    Expected JSON: { "tron_address": "..." }
    """
    try:
        data = await request.json()
        tron_address = data.get("tron_address")
        if not tron_address:
            return web.json_response({"error": "Missing tron_address"}, status=400)
        # Fix the case (placeholder)
        fixed_tron = await fix_case(tron_address)
        # Generate the receiver address via the factory contract
        receiver_address = await generate_receiver_address(fixed_tron)
        # Store mapping in DB
        await store_resolved_pair(fixed_tron, receiver_address)
        return web.json_response({
            "tron_address": fixed_tron,
            "receiver_address": receiver_address
        })
    except Exception as e:
        logger.exception("Error in resolve_handler")
        return web.json_response({"error": str(e)}, status=500)

async def list_receivers(request: web.Request):
    """
    Returns a list of all stored Tron -> receiver mappings.
    """
    try:
        async with aiosqlite.connect(DB_FILENAME) as db:
            async with db.execute("SELECT tron_address, receiver_address, resolved_at FROM receivers") as cursor:
                rows = await cursor.fetchall()
                result = [{"tron_address": row[0], "receiver_address": row[1], "resolved_at": row[2]} for row in rows]
        return web.json_response(result)
    except Exception as e:
        logger.exception("Error in list_receivers")
        return web.json_response({"error": str(e)}, status=500)

# ---------------------------
# Blockchain Interaction
# ---------------------------
async def call_intron(receiver_address: str):
    """
    Calls the intron() function on the receiver contract at the given address.
    """
    try:
        receiver_contract = w3.eth.contract(address=receiver_address, abi=RECEIVER_ABI)
        nonce = await w3.eth.get_transaction_count(account.address)
        gas_price = await w3.eth.gas_price
        tx = receiver_contract.functions.intron().buildTransaction({
            "chainId": w3.eth.chain_id,
            "gas": 300000,  # adjust as needed
            "gasPrice": gas_price,
            "nonce": nonce,
        })
        signed_tx = account.sign_transaction(tx)
        tx_hash = await w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        logger.info(f"Called intron() on {receiver_address}, tx hash: {tx_hash.hex()}")
        receipt = await w3.eth.wait_for_transaction_receipt(tx_hash)
        return receipt
    except Exception as e:
        logger.exception(f"Error calling intron() on {receiver_address}: {e}")
        return None

async def poll_transfers():
    """
    Background task that polls for Transfer events (for USDT and USDC) whose 'to' field
    matches any of the receiver addresses stored in the database.
    When a matching transfer is detected, call intron() on the receiver.
    """
    logger.info("Starting transfer polling background task")
    last_block = await w3.eth.get_block_number()
    while True:
        try:
            current_block = await w3.eth.get_block_number()
            # Retrieve current receiver addresses from the DB
            async with aiosqlite.connect(DB_FILENAME) as db:
                async with db.execute("SELECT receiver_address FROM receivers") as cursor:
                    rows = await cursor.fetchall()
                    # Normalize addresses to lower-case for comparisons
                    receiver_addresses = [row[0].lower() for row in rows]
            if receiver_addresses:
                # Poll both token contracts (USDT and USDC)
                for token_contract in [usdt_contract, usdc_contract]:
                    # Get the Transfer event signature topic
                    transfer_topic = token_contract.events.Transfer().signature
                    filter_params = {
                        "fromBlock": last_block + 1,
                        "toBlock": current_block,
                        "address": token_contract.address,
                        # topics[0]: event signature, topics[2]: "to" address (using OR filtering)
                        "topics": [
                            transfer_topic,
                            None,
                            [w3.toChecksumAddress(addr) for addr in receiver_addresses]
                        ]
                    }
                    logs = await w3.eth.get_logs(filter_params)
                    for log in logs:
                        event = token_contract.events.Transfer().process_log(log)
                        to_address = event["args"]["to"].lower()
                        value = event["args"]["value"]
                        logger.info(f"Detected Transfer of {value} tokens to {to_address}")
                        # Call intron() on the receiver contract (fire-and-forget)
                        asyncio.create_task(call_intron(to_address))
            last_block = current_block
        except Exception as e:
            logger.exception(f"Error while polling transfers: {e}")
        await asyncio.sleep(10)  # Poll every 10 seconds

# ---------------------------
# App Initialization
# ---------------------------
async def init_app():
    app = web.Application()
    app.router.add_post("/resolve", resolve_handler)
    app.router.add_get("/receivers", list_receivers)
    return app

async def main():
    app = await init_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    logger.info("Server started at http://0.0.0.0:8080")
    # Start the background task for transfer polling
    asyncio.create_task(poll_transfers())
    # Run indefinitely
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")