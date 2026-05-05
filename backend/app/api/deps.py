"""Shared FastAPI dependencies."""

from typing import Annotated, Optional

from fastapi import Header, HTTPException

from app.config import settings


def require_admin_api_key(
    x_api_key: Annotated[Optional[str], Header(alias='X-API-Key')] = None,
) -> None:
    """
    When REQUIRE_API_KEY=true, every protected route must send header:
      X-API-Key: <same value as API_ADMIN_KEY in .env>

    This stops random clients on the network from enabling trading or reading positions.
    Leave REQUIRE_API_KEY=false for local-only dev on your laptop.
    """
    if not settings.require_api_key:
        return
    if not (settings.api_admin_key or '').strip():
        raise HTTPException(status_code=500, detail='REQUIRE_API_KEY is true but API_ADMIN_KEY is empty')
    if not x_api_key or x_api_key != settings.api_admin_key:
        raise HTTPException(status_code=401, detail='Invalid or missing X-API-Key')
