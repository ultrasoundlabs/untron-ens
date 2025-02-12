import logging
from typing import Dict, Optional, Tuple
from web3 import AsyncWeb3, AsyncHTTPProvider
from web3.contract import AsyncContract

from .config import CONFIG, ABIS

logger = logging.getLogger(__name__)

class BlockchainClient:
    def __init__(self):
        logger.info("Initializing blockchain client")
        self.w3: AsyncWeb3 = AsyncWeb3(AsyncHTTPProvider(CONFIG["rpc_url"]))
        logger.info(f"Connected to RPC endpoint: {CONFIG['rpc_url']}")
        
        self.account = self.w3.eth.account.from_key(CONFIG["private_key"])
        logger.info(f"Initialized account: {self.account.address}")
        
        # Contract instances
        self.factory_contract: Optional[AsyncContract] = None
        self.usdt_contract: Optional[AsyncContract] = None
        self.usdc_contract: Optional[AsyncContract] = None

    async def setup_contracts(self) -> None:
        """Initialize contract instances."""
        logger.info("=== Setting up contract instances ===")
        
        # Set up factory contract
        logger.info(f"Setting up factory contract at {CONFIG['factory_address']}")
        self.factory_contract = self.w3.eth.contract(
            address=CONFIG["factory_address"],
            abi=ABIS["factory"]
        )
        
        # Set up token contracts
        logger.info("Fetching token addresses from factory contract")
        usdt_address = await self.factory_contract.functions.usdt().call()
        self.usdt_contract = self.w3.eth.contract(
            address=usdt_address,
            abi=ABIS["erc20"]
        )
        logger.info(f"Initialized USDT contract at {usdt_address}")
        
        usdc_address = await self.factory_contract.functions.usdc().call()
        self.usdc_contract = self.w3.eth.contract(
            address=usdc_address,
            abi=ABIS["erc20"]
        )
        logger.info(f"Initialized USDC contract at {usdc_address}")
        logger.info("=== Contract setup complete ===")

    async def generate_receiver_address(self, tron_bytes: bytes) -> str:
        """Generate receiver address from Tron address bytes."""
        if not self.factory_contract:
            raise RuntimeError("Factory contract not initialized")
        
        logger.info(f"Generating receiver address for Tron bytes: {tron_bytes.hex()}")
        address = await self.factory_contract.functions.generateReceiverAddress(tron_bytes).call()
        logger.info(f"Generated receiver address: {address}")
        return address

    async def _build_and_send_tx(self, func, gas_limit: int = 500000) -> Dict:
        """Helper to build and send a transaction."""
        nonce = await self.w3.eth.get_transaction_count(self.account.address)
        gas_price = await self.w3.eth.gas_price
        chain_id = await self.w3.eth.chain_id
        
        logger.info(f"Building transaction - Nonce: {nonce}, Gas Price: {gas_price}, Chain ID: {chain_id}")
        
        tx = await func.build_transaction({
            "chainId": chain_id,
            "gas": gas_limit,
            "gasPrice": gas_price,
            "nonce": nonce,
        })
        
        logger.info(f"Signing transaction: {tx}")
        signed_tx = self.account.sign_transaction(tx)
        
        logger.info("Sending transaction")
        tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        logger.info(f"Transaction sent, hash: {tx_hash.hex()}")
        
        logger.info("Waiting for transaction receipt")
        receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash)
        logger.info(f"Transaction confirmed in block {receipt['blockNumber']}")
        
        return receipt

    async def deploy_receiver(self, tron_address: bytes) -> Dict:
        """Deploy a new receiver contract."""
        if not self.factory_contract:
            raise RuntimeError("Factory contract not initialized")
            
        try:
            logger.info(f"=== Deploying receiver for Tron address: {tron_address.hex()} ===")
            receipt = await self._build_and_send_tx(
                self.factory_contract.functions.deploy(tron_address)
            )
            logger.info(f"Receiver deployment successful, gas used: {receipt['gasUsed']}")
            return receipt
        except Exception as e:
            logger.exception(f"Error deploying receiver for {tron_address.hex()}: {e}")
            raise

    async def call_intron(self, tron_address: bytes) -> Dict:
        """Call the intron function."""
        if not self.factory_contract:
            raise RuntimeError("Factory contract not initialized")
            
        try:
            logger.info(f"=== Calling intron for Tron address: {tron_address.hex()} ===")
            receipt = await self._build_and_send_tx(
                self.factory_contract.functions.intron(tron_address)
            )
            logger.info(f"Intron call successful, gas used: {receipt['gasUsed']}")
            return receipt
        except Exception as e:
            logger.exception(f"Error calling intron for {tron_address.hex()}: {e}")
            raise

    def get_token_contracts(self) -> Tuple[AsyncContract, AsyncContract]:
        """Get USDT and USDC contract instances."""
        if not all([self.usdt_contract, self.usdc_contract]):
            raise RuntimeError("Token contracts not initialized")
        return self.usdt_contract, self.usdc_contract

# Global blockchain client instance
client = BlockchainClient()
