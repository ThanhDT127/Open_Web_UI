"""
Price administration API endpoints.
Provides CRUD operations for model pricing with automatic file synchronization.
"""

import json
from typing import Dict, Any
from fastapi import Request, HTTPException
from pydantic import BaseModel

from config import PRICES_FILE, logger
from core.db import db_conn
from core.cost import load_prices


class PriceUpdateRequest(BaseModel):
    model_name: str
    pricing: Dict[str, Any]


def _sync_prices_to_file():
    """Sync the database prices state back to the fallback file backup."""
    try:
        prices = load_prices()
        with open(PRICES_FILE, "w", encoding="utf-8") as f:
            json.dump(prices, f, indent=2, ensure_ascii=False)
        logger.info("Successfully synchronized database prices to fallback file %s", PRICES_FILE)
    except Exception as e:
        logger.error("Failed to sync database prices to file backup: %s", str(e))


def list_prices(request: Request):
    """
    GET /v1/_mw/admin/prices
    List all model pricing configurations.
    """
    from utils.auth_guard import require_admin_or_session
    require_admin_or_session(request)
    
    return load_prices()


async def update_price(request: Request):
    """
    POST /v1/_mw/admin/prices
    Create or update model pricing.
    """
    from utils.auth_guard import require_admin_or_session
    require_admin_or_session(request)
    
    try:
        body = await request.json()
        req = PriceUpdateRequest(**body)
    except Exception as e:
        raise HTTPException(400, f"Invalid request body: {e}")
        
    if not req.model_name.strip():
        raise HTTPException(400, "Model name cannot be empty")
        
    # Validate non-negative pricing values
    for k, v in req.pricing.items():
        if k in ("input_per_1m", "output_per_1m", "per_image_usd") and isinstance(v, (int, float)):
            if v < 0:
                raise HTTPException(400, f"Pricing value for {k} cannot be negative")
                
    # Update in database
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO mw_prices (model_name, pricing)
            VALUES (%s, %s)
            ON CONFLICT (model_name)
            DO UPDATE SET pricing = EXCLUDED.pricing
        """, (req.model_name, json.dumps(req.pricing)))
        cur.close()
        
    # Update the backup file
    _sync_prices_to_file()
    
    return {"ok": True, "message": f"Price updated successfully for model: {req.model_name}"}


def delete_price(model_name: str, request: Request):
    """
    DELETE /v1/_mw/admin/prices/{model_name}
    Delete model pricing configuration.
    """
    from utils.auth_guard import require_admin_or_session
    require_admin_or_session(request)
    
    if not model_name.strip():
        raise HTTPException(400, "Model name cannot be empty")
        
    with db_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM mw_prices WHERE model_name = %s", (model_name,))
        rowcount = cur.rowcount
        cur.close()
        
    if rowcount == 0:
        raise HTTPException(404, f"Model pricing for '{model_name}' not found")
        
    # Update the backup file
    _sync_prices_to_file()
    
    return {"ok": True, "message": f"Price deleted successfully for model: {model_name}"}
