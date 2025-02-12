import asyncio
import logging
import os
from typing import Optional
import base58
from pathlib import Path

from .config import PROJECT_ROOT

logger = logging.getLogger(__name__)

# Get the relayer directory path
RELAYER_DIR = Path(__file__).parent.absolute()

async def run_case_fix_binary(address: str) -> str:
    """Run the base58bruteforce binary asynchronously."""
    try:
        process = await asyncio.create_subprocess_exec(
            str(RELAYER_DIR / "binary"), address,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if stdout:
            return stdout.decode().strip()
        if stderr:
            logger.error(f"Error from case fix binary: {stderr.decode()}")
        return ""
    except Exception as e:
        logger.exception(f"Error running case fix binary: {e}")
        return ""

def address_to_topic(address: str) -> str:
    """Convert an Ethereum address to a 32-byte topic."""
    if address.startswith("0x"):
        address = address[2:]
    return "0x" + address.rjust(64, "0")

async def save_last_block(chain_name: str, block_number: int) -> None:
    """Save the last processed block number for a chain."""
    os.makedirs(PROJECT_ROOT / "backups", exist_ok=True)
    with open(PROJECT_ROOT / "backups" / f"last_block_{chain_name}.txt", "w") as f:
        f.write(str(block_number))

async def load_last_block(chain_name: str) -> int:
    """Load the last processed block number for a chain."""
    try:
        with open(PROJECT_ROOT / "backups" / f"last_block_{chain_name}.txt", "r") as f:
            return int(f.read().strip())
    except FileNotFoundError:
        return 0

def decode_tron_address(tron_address: str) -> Optional[bytes]:
    """Decode a Tron address to bytes, returning None if invalid."""
    try:
        return base58.b58decode_check(tron_address)[1:]
    except Exception as e:
        logger.error(f"Error decoding Tron address {tron_address}: {e}")
        return None

def validate_tron_address(tron_address: str) -> bool:
    """Validate a Tron address format."""
    if not isinstance(tron_address, str):
        return False
    if len(tron_address) not in range(25, 35):
        return False
    try:
        decode_tron_address(tron_address)
        return True
    except Exception:
        return False
