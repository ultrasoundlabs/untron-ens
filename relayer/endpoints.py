import logging
from aiohttp import web
from typing import Dict, Any

from .database import store_resolved_pair, get_all_receivers, get_case_fix, store_case_fix
from .blockchain import client
from .utils import run_case_fix_binary, validate_tron_address, decode_tron_address

logger = logging.getLogger(__name__)

async def resolve_handler(request: web.Request) -> web.Response:
    """Handle /resolve endpoint."""
    logger.info("=== Starting new resolve request ===")
    try:
        data = await request.json()
        logger.info(f"Received request data: {data}")
        
        domain = data.get("data")
        if not domain:
            logger.error("Missing data field in request")
            return web.json_response(
                {"message": "Missing data field"},
                status=400
            )
            
        try:
            domain = bytes.fromhex(domain.lstrip("0x"))
            logger.info(f"Successfully decoded domain bytes: {domain.hex()}")
        except Exception as e:
            logger.error(f"Failed to decode domain hex: {domain}, error: {e}")
            return web.json_response(
                {"message": f"Invalid domain format: {e}"},
                status=400
            )
            
        # Extract Tron address from domain data
        lowercased_tron_address = domain[1:domain[0]+1].decode().lower()
        logger.info(f"Extracted Tron address from domain: {lowercased_tron_address}")
        
        if not validate_tron_address(lowercased_tron_address):
            logger.error(f"Invalid Tron address format: {lowercased_tron_address}")
            return web.json_response(
                {"message": "Invalid Tron address format"},
                status=400
            )
            
        # Check cache for case fix
        fixed_tron_address = await get_case_fix(lowercased_tron_address)
        if fixed_tron_address:
            logger.info(f"Found cached case fix: {lowercased_tron_address} -> {fixed_tron_address}")
        else:
            logger.info(f"No cached case fix found for {lowercased_tron_address}, running binary...")
            # Run case fix binary if not in cache
            fixed_tron_address = await run_case_fix_binary(lowercased_tron_address)
            if fixed_tron_address:
                logger.info(f"Successfully fixed case: {lowercased_tron_address} -> {fixed_tron_address}")
                await store_case_fix(lowercased_tron_address, fixed_tron_address)
            else:
                logger.error(f"Failed to fix case for address: {lowercased_tron_address}")
                return web.json_response(
                    {"message": "Failed to process Tron address"},
                    status=500
                )
                
        # Generate receiver address
        tron_bytes = decode_tron_address(fixed_tron_address)
        if not tron_bytes:
            logger.error(f"Failed to decode fixed Tron address: {fixed_tron_address}")
            return web.json_response(
                {"message": "Invalid Tron address"},
                status=400
            )
            
        logger.info(f"Generating receiver address for Tron bytes: {tron_bytes.hex()}")
        receiver_address = await client.generate_receiver_address(tron_bytes)
        logger.info(f"Generated receiver address: {receiver_address}")
        
        # Store the mapping
        await store_resolved_pair(fixed_tron_address, receiver_address)
        logger.info(f"Stored mapping: {fixed_tron_address} -> {receiver_address}")
        
        # Construct response
        result = "0x" + (bytes([domain[0]]) + fixed_tron_address.encode() + domain[domain[0]+1:]).hex()
        logger.info(f"=== Resolve complete: {lowercased_tron_address} -> {result} ===")
        
        return web.json_response({"data": result})
        
    except Exception as e:
        logger.exception(f"Unexpected error in resolve_handler: {e}")
        return web.json_response(
            {"message": f"Internal server error: {str(e)}"},
            status=500
        )

async def list_receivers_handler(request: web.Request) -> web.Response:
    """Handle /receivers endpoint."""
    logger.info("=== Starting list_receivers request ===")
    try:
        receivers = await get_all_receivers()
        logger.info(f"Found {len(receivers)} receiver mappings")
        return web.json_response(receivers)
    except Exception as e:
        logger.exception(f"Error in list_receivers_handler: {e}")
        return web.json_response(
            {"message": f"Internal server error: {str(e)}"},
            status=500
        )

def setup_routes(app: web.Application) -> None:
    """Configure routes for the application."""
    logger.info("Setting up HTTP routes")
    app.router.add_post("/resolve", resolve_handler)
    app.router.add_get("/receivers", list_receivers_handler)
    logger.info("HTTP routes configured successfully")
