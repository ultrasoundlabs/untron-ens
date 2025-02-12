import asyncio
import logging
from typing import List, Dict, Optional
from web3.contract import AsyncContract
import time

from .database import get_receiver_mapping
from .blockchain import client
from .utils import address_to_topic, save_last_block, load_last_block, decode_tron_address

logger = logging.getLogger(__name__)

# Status update interval (in seconds)
STATUS_UPDATE_INTERVAL = 60
last_status_update = 0

async def process_token_transfers(
    token_contract: AsyncContract,
    receiver_addresses: List[str],
    from_block: int,
    to_block: int
) -> None:
    """Process transfer logs for a specific token contract."""
    token_name = "USDT" if token_contract.address == client.usdt_contract.address else "USDC"
    
    try:
        # Get transfer logs
        logs = await client.w3.eth.get_logs({
            "fromBlock": from_block,
            "toBlock": to_block,
            "address": token_contract.address,
            "topics": [
                "0x" + client.w3.keccak(text="Transfer(address,address,uint256)").hex(),
                None,
                [address_to_topic(x) for x in receiver_addresses]
            ]
        })
        
        if logs:
            logger.info(f"Found {len(logs)} {token_name} transfer events in blocks {from_block}-{to_block}")
        
        for log in logs:
            try:
                # Process the Transfer event
                event = token_contract.events.Transfer().process_log(log)
                to_address = event.args.to
                value = event.args.value
                logger.info(f"Processing {token_name} transfer: {value} tokens to {to_address}")
                
                # Get corresponding Tron address
                mapping = await get_receiver_mapping()
                tron_address = mapping.get(to_address)
                if not tron_address:
                    logger.error(f"No Tron address mapping found for receiver {to_address}")
                    continue
                
                # Decode Tron address
                tron_bytes = decode_tron_address(tron_address)
                if not tron_bytes:
                    logger.error(f"Failed to decode Tron address: {tron_address}")
                    continue
                
                # Call intron()
                logger.info(f"Calling intron() for transfer to {to_address}")
                receipt = await client.call_intron(tron_bytes)
                logger.info(f"Intron call successful for {token_name} transfer, tx: {receipt['transactionHash'].hex()}")
                
            except Exception as e:
                logger.exception(f"Error processing {token_name} transfer event: {e}")
                continue
                
    except Exception as e:
        logger.exception(f"Error fetching {token_name} logs for blocks {from_block}-{to_block}: {e}")
        raise

async def poll_transfers() -> None:
    """
    Background task that polls for Transfer events from USDT and USDC contracts
    to any receiver address stored in the database.
    """
    global last_status_update
    logger.info("=== Starting transfer polling background task ===")
    
    # Get Transfer event signature
    transfer_event_signature = client.w3.keccak(text="Transfer(address,address,uint256)").hex()
    
    chunk_size = 1000  # Initial chunk size
    min_chunk_size = 100  # Minimum chunk size when reducing due to errors
    
    while True:
        try:
            current_time = time.time()
            
            # Get current receiver mappings
            mapping = await get_receiver_mapping()
            receiver_addresses = list(mapping.keys())
            
            # Emit periodic status update
            if current_time - last_status_update >= STATUS_UPDATE_INTERVAL:
                logger.info(f"Status: Monitoring {len(receiver_addresses)} receiver addresses for USDT/USDC transfers")
                last_status_update = current_time
            
            if receiver_addresses:
                for token_contract in [client.usdt_contract, client.usdc_contract]:
                    token_name = "USDT" if token_contract.address == client.usdt_contract.address else "USDC"
                    
                    # Load last processed block
                    last_block = await load_last_block(f"{token_name}_transfers")
                    if not last_block:
                        last_block = await client.w3.eth.block_number
                    
                    current_block = await client.w3.eth.block_number
                    
                    if current_block > last_block:
                        blocks_behind = current_block - last_block
                        if blocks_behind > 100:  # Only log if significantly behind
                            logger.info(f"Processing {blocks_behind} new blocks for {token_name}")
                        
                        from_block = last_block + 1
                        while from_block <= current_block:
                            to_block = min(from_block + chunk_size - 1, current_block)
                            
                            try:
                                await process_token_transfers(
                                    token_contract,
                                    receiver_addresses,
                                    from_block,
                                    to_block
                                )
                                
                                # Update last processed block
                                await save_last_block(f"{token_name}_transfers", to_block)
                                from_block = to_block + 1
                                
                                # Reset chunk size if successful
                                chunk_size = 1000
                                
                            except Exception as e:
                                logger.error(f"Error processing chunk {from_block}-{to_block}: {e}")
                                # Reduce chunk size and retry
                                chunk_size = max(chunk_size // 2, min_chunk_size)
                                # Don't advance from_block so we retry this chunk
                                await asyncio.sleep(1)  # Brief pause before retry
            
        except Exception as e:
            logger.exception(f"Error in polling loop: {e}")
            
        # Wait before next polling iteration
        await asyncio.sleep(2)
