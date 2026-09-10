"""Per-endpoint cache of authentication state.

Keeps one Authentication instance per endpoint so an OAuth2 access token is reused
across requests instead of being re-fetched every time. A per-endpoint lock stops
concurrent queries from stampeding the token endpoint after an expiry.
"""

import asyncio
from typing import Any, Optional

import httpx

from app.auth.strategies import Authentication, build_authentication

_strategies: dict[int, Authentication] = {}
_signatures: dict[int, tuple] = {}
_locks: dict[int, asyncio.Lock] = {}
_registry_lock = asyncio.Lock()


def _signature(endpoint: Any) -> tuple:
    """Fields that, when changed, make cached credential state stale."""
    return (
        endpoint.auth_method,
        endpoint.token_field_header,
        endpoint.client_username,
        endpoint.token_url,
        endpoint.client_id,
        endpoint.scope,
        endpoint.grant_type,
        endpoint.enc_client_password,
        endpoint.enc_client_secret,
        endpoint.enc_static_token,
        endpoint.enc_oauth_basic_credential,
    )


def invalidate(endpoint_id: Optional[int]) -> None:
    """Forget an endpoint's cached credentials (on update or delete)."""
    if endpoint_id is None:
        return
    strategy = _strategies.pop(endpoint_id, None)
    if strategy is not None:
        strategy.invalidate()
    _signatures.pop(endpoint_id, None)
    _locks.pop(endpoint_id, None)


def clear() -> None:
    _strategies.clear()
    _signatures.clear()
    _locks.clear()


async def _get_lock(endpoint_id: int) -> asyncio.Lock:
    async with _registry_lock:
        lock = _locks.get(endpoint_id)
        if lock is None:
            lock = asyncio.Lock()
            _locks[endpoint_id] = lock
        return lock


async def get_headers(endpoint: Any, client: httpx.AsyncClient) -> dict:
    """Return the auth headers for `endpoint`, refreshing the token if needed."""
    endpoint_id = getattr(endpoint, "id", None)
    if endpoint_id is None:
        # Unsaved endpoint (e.g. a connection test before create): no caching.
        return await build_authentication(endpoint).get_headers(client)

    lock = await _get_lock(endpoint_id)
    async with lock:
        signature = _signature(endpoint)
        if _signatures.get(endpoint_id) != signature:
            invalidate_strategy = _strategies.pop(endpoint_id, None)
            if invalidate_strategy is not None:
                invalidate_strategy.invalidate()
            _strategies[endpoint_id] = build_authentication(endpoint)
            _signatures[endpoint_id] = signature
        strategy = _strategies[endpoint_id]
        # Held across the request so only one caller refreshes an expired token.
        return await strategy.get_headers(client)
