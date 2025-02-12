import aiosqlite
import logging
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any
from datetime import datetime

from .config import DB_FILENAME

logger = logging.getLogger(__name__)

@asynccontextmanager
async def get_db():
    """Context manager for database connections."""
    db = await aiosqlite.connect(DB_FILENAME)
    try:
        yield db
    finally:
        await db.close()

async def setup_database() -> None:
    """Initialize database tables."""
    logger.info(f"Setting up database: {DB_FILENAME}")
    async with get_db() as db:
        # Create receivers table
        logger.info("Creating receivers table if not exists")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS receivers (
                tron_address TEXT PRIMARY KEY,
                receiver_address TEXT,
                resolved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create case_fixes table
        logger.info("Creating case_fixes table if not exists")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS case_fixes (
                original_address TEXT PRIMARY KEY,
                fixed_address TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()
        logger.info("Database setup complete")

async def get_case_fix(address: str) -> Optional[str]:
    """Get cached case fix for an address."""
    async with get_db() as db:
        async with db.execute(
            "SELECT fixed_address FROM case_fixes WHERE original_address = ?",
            (address,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def store_case_fix(original: str, fixed: str) -> None:
    """Store a case fix in the cache."""
    async with get_db() as db:
        await db.execute(
            "INSERT OR IGNORE INTO case_fixes (original_address, fixed_address) VALUES (?, ?)",
            (original, fixed)
        )
        await db.commit()
        logger.info(f"Cached case fix for {original}")

async def store_resolved_pair(tron_address: str, receiver_address: str) -> None:
    """Store a Tron->receiver address mapping."""
    logger.info(f"Storing resolved pair - Tron: {tron_address}, Receiver: {receiver_address}")
    async with get_db() as db:
        await db.execute(
            "INSERT OR IGNORE INTO receivers (tron_address, receiver_address) VALUES (?, ?)",
            (tron_address, receiver_address)
        )
        await db.commit()
        logger.info("Successfully stored resolved pair")

async def get_all_receivers() -> List[Dict[str, Any]]:
    """Get all stored Tron->receiver mappings."""
    async with get_db() as db:
        async with db.execute(
            "SELECT tron_address, receiver_address, resolved_at FROM receivers"
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "tron_address": row[0],
                    "receiver_address": row[1],
                    "resolved_at": row[2]
                }
                for row in rows
            ]

async def get_receiver_mapping() -> Dict[str, str]:
    """Get mapping of receiver_address -> tron_address."""
    async with get_db() as db:
        async with db.execute(
            "SELECT tron_address, receiver_address FROM receivers"
        ) as cursor:
            rows = await cursor.fetchall()
            return {row[1]: row[0] for row in rows}
