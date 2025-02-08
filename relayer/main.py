import asyncio
import json
import logging
from aiohttp import web
import aiosqlite
from web3 import AsyncWeb3, AsyncHTTPProvider

# ---------------------------
# Configuration
# ---------------------------
# Load ABIs and configuration.
FACTORY_ABI = json.load(open("../out/ReceiverFactory.json"))["abi"]
RECEIVER_ABI = json.load(open("../out/UntronReceiver.json"))["abi"]
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
factory_contract = w3.eth.contract(address=CONFIG["factory_address"], abi=FACTORY_ABI)

# Global contract variables
implementation_contract = None
usdt_contract = None
usdc_contract = None

async def setup_contracts():
    global implementation_contract, usdt_contract, usdc_contract
    
    implementation_address = await factory_contract.functions.receiverImplementation().call()
    print(f"Implementation contract address: {implementation_address}")
    implementation_contract = w3.eth.contract(address=implementation_address, abi=RECEIVER_ABI)

    usdt_address = await implementation_contract.functions.usdt().call()
    print(f"USDT contract address: {usdt_address}")
    usdt_contract = w3.eth.contract(address=usdt_address, abi=ERC20_ABI)

    usdc_address = await implementation_contract.functions.usdc().call()
    print(f"USDC contract address: {usdc_address}")
    usdc_contract = w3.eth.contract(address=usdc_address, abi=ERC20_ABI)

account = w3.eth.account.from_key(CONFIG["private_key"])

# ---------------------------
# Helper Functions
# ---------------------------
async def fix_case(address: str) -> str:
    """
    Placeholder to fix the case of an address.
    For now, simply return the input.
    """
    # TODO: implement proper case fixing logic.
    return address

async def generate_receiver_address(tron_address: str) -> str:
    """
    Calls the factory's generateReceiverAddress view function.
    Expects tron_address to be a hex string (with or without "0x") representing 20 bytes.
    """
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
    Expects JSON input: { "tron_address": "..." }
    Fixes the case, computes the receiver address using the factory,
    stores the mapping, and returns the result.
    """
    try:
        data = await request.json()
        domain = data.get("data")
        if not domain:
            return web.json_response({"message": "Missing tron_address"}, status=404)
        try:
            domain = bytes.fromhex(domain.lstrip("0x"))
        except Exception as e:
            return web.json_response({"message": f"Invalid domain: {e}"}, status=404)
        lowercased_tron_address = domain[1:domain[0]+1].decode().lower()
        if len(lowercased_tron_address) not in range(25, 35):
            return web.json_response({"message": "Invalid tron_address"}, status=404)
        fixed_tron_address = await fix_case(lowercased_tron_address)
        receiver_address = await generate_receiver_address(fixed_tron_address)
        await store_resolved_pair(fixed_tron_address, receiver_address)
        return web.json_response({
            "data": "0x" + (bytes([domain[0]]) + fixed_tron_address.encode() + domain[domain[0]+1:]).hex()
        })
    except Exception as e:
        logger.exception("Error in resolve_handler")
        return web.json_response({"message": str(e)}, status=404)

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
        return web.json_response({"message": str(e)}, status=404)

# ---------------------------
# Blockchain Interaction
# ---------------------------
async def call_deploy(tron_address: str):
    """
    Calls the factory contract's deploy(destinationTronAddress: bytes20) function.
    """
    try:
        tron_bytes = bytes.fromhex(tron_address[2:] if tron_address.startswith("0x") else tron_address)
        nonce = await w3.eth.get_transaction_count(account.address)
        gas_price = await w3.eth.gas_price
        tx = factory_contract.functions.deploy(tron_bytes).buildTransaction({
            "chainId": w3.eth.chain_id,
            "gas": 300000,  # Adjust gas limit as needed.
            "gasPrice": gas_price,
            "nonce": nonce,
        })
        signed_tx = account.sign_transaction(tx)
        tx_hash = await w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        logger.info(f"Called deploy() for tron_address {tron_address}, tx hash: {tx_hash.hex()}")
        receipt = await w3.eth.wait_for_transaction_receipt(tx_hash)
        return receipt
    except Exception as e:
        logger.exception(f"Error calling deploy() for tron_address {tron_address}: {e}")
        return None

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
            "gas": 300000,
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
    Background task that polls for Transfer events (from USDT and USDC contracts)
    whose 'to' field matches any receiver address stored in the DB.
    If a transfer is detected:
      - Check if the receiver contract is deployed.
      - If not, call deploy() on the factory (using the corresponding Tron address).
      - After a successful deployment, or if already deployed, call intron() on the receiver.
    """
    logger.info("Starting transfer polling background task")
    last_block = await w3.eth.get_block_number()
    while True:
        try:
            current_block = await w3.eth.get_block_number()
            # Retrieve current mappings: key = receiver_address.lower(), value = tron_address.
            async with aiosqlite.connect(DB_FILENAME) as db:
                async with db.execute("SELECT tron_address, receiver_address FROM receivers") as cursor:
                    rows = await cursor.fetchall()
                    mapping = {row[1].lower(): row[0] for row in rows}
                    receiver_addresses = list(mapping.keys())
            if receiver_addresses:
                for token_contract in [usdt_contract, usdc_contract]:
                    transfer_topic = token_contract.events.Transfer().signature
                    filter_params = {
                        "fromBlock": last_block + 1,
                        "toBlock": current_block,
                        "address": token_contract.address,
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
                        tron_address = mapping.get(to_address)
                        if not tron_address:
                            logger.error(f"No tron_address mapping found for receiver {to_address}")
                            continue

                        # Check if the receiver contract is deployed.
                        code = await w3.eth.get_code(to_address)
                        if code in (b'', '0x', b'0x'):
                            logger.info(f"Receiver contract {to_address} not deployed; deploying now for tron_address {tron_address}")
                            deploy_receipt = await call_deploy(tron_address)
                            if deploy_receipt is None:
                                logger.error(f"Deployment failed for tron_address {tron_address}")
                                continue
                            # Optionally wait a few seconds for the deployment to propagate.
                            await asyncio.sleep(5)
                            code = await w3.eth.get_code(to_address)
                            if code in (b'', '0x', b'0x'):
                                logger.error(f"Deployment did not result in contract code at {to_address}")
                                continue

                        # Now that the receiver contract is deployed, call intron().
                        asyncio.create_task(call_intron(to_address))
            last_block = current_block
        except Exception as e:
            logger.exception(f"Error while polling transfers: {e}")
        await asyncio.sleep(10)  # Poll every 10 seconds.

# ---------------------------
# App Initialization
# ---------------------------
async def init_app():
    app = web.Application()
    app.router.add_post("/resolve", resolve_handler)
    app.router.add_get("/receivers", list_receivers)
    return app

async def main():
    await setup_contracts()
    app = await init_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    logger.info("Server started at http://0.0.0.0:8080")
    asyncio.create_task(poll_transfers())
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")