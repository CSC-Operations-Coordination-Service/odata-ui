"""Execution of OData requests against a configured endpoint."""

import time
from typing import Any, Optional

import httpx

from app.auth import token_cache
from app.auth.strategies import AuthError

# Body excerpt returned to the UI when the service answers with an error.
ERROR_EXCERPT_LEN = 800


class UpstreamError(RuntimeError):
    """The target OData service refused or failed the request."""

    def __init__(self, message: str, url: str, status_code: Optional[int] = None,
                 body: str = ""):
        super().__init__(message)
        self.message = message
        self.url = url
        self.status_code = status_code
        self.body = body[:ERROR_EXCERPT_LEN]


class QueryResult:
    def __init__(self, url: str, status_code: int, duration_ms: int, rows: list,
                 total_count: Optional[int], next_link: Optional[str], raw: Any):
        self.url = url
        self.status_code = status_code
        self.duration_ms = duration_ms
        self.rows = rows
        self.total_count = total_count
        self.next_link = next_link
        self.raw = raw

    @property
    def count(self) -> int:
        return len(self.rows)


def make_client(endpoint: Any) -> httpx.AsyncClient:
    """One client per request cycle, honouring the endpoint's TLS setting."""
    return httpx.AsyncClient(
        verify=bool(getattr(endpoint, "verify_ssl", True)),
        timeout=getattr(endpoint, "timeout", 60) or 60,
        follow_redirects=True,
    )


def _extract_rows(payload: Any) -> list:
    """Pull the row list out of a v4 or v3-JSON response.

    v4 puts them under `value`; v3's JSON verbose format nests them under `d.results`.
    A by-id lookup returns the entity itself rather than a collection.
    """
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("value"), list):
        return payload["value"]
    data = payload.get("d")
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        return data["results"]
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    # A single entity: strip the OData annotations so the table shows real fields.
    row = {k: v for k, v in payload.items() if not k.startswith("@odata.")}
    return [row] if row else []


def _extract_total(payload: Any) -> Optional[int]:
    if not isinstance(payload, dict):
        return None
    for key in ("@odata.count", "odata.count", "__count"):
        if key in payload:
            try:
                return int(payload[key])
            except (TypeError, ValueError):
                return None
    data = payload.get("d")
    if isinstance(data, dict) and "__count" in data:
        try:
            return int(data["__count"])
        except (TypeError, ValueError):
            return None
    return None


def _extract_next_link(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    for key in ("@odata.nextLink", "odata.nextLink"):
        if payload.get(key):
            return payload[key]
    data = payload.get("d")
    if isinstance(data, dict) and data.get("__next"):
        return data["__next"]
    return None


async def execute(endpoint: Any, url: str) -> QueryResult:
    """Run a GET against `url` with the endpoint's auth, and normalise the response."""
    async with make_client(endpoint) as client:
        try:
            headers = await token_cache.get_headers(endpoint, client)
        except AuthError as exc:
            raise UpstreamError(f"Authentication failed: {exc}", url) from exc

        headers.setdefault("Accept", "application/json")
        started = time.perf_counter()
        try:
            response = await client.get(url, headers=headers)
        except httpx.RequestError as exc:
            raise UpstreamError(f"Could not reach the service: {exc}", url) from exc
        duration_ms = int((time.perf_counter() - started) * 1000)

    if not 200 <= response.status_code < 300:
        raise UpstreamError(
            f"The service returned HTTP {response.status_code}.",
            url,
            status_code=response.status_code,
            body=response.text,
        )

    try:
        payload = response.json()
    except ValueError as exc:
        # v3 services often answer in Atom XML unless asked for JSON.
        raise UpstreamError(
            "The service did not return JSON. For an OData v3 service, try adding "
            "$format=json to the custom suffix.",
            url,
            status_code=response.status_code,
            body=response.text,
        ) from exc

    return QueryResult(
        url=url,
        status_code=response.status_code,
        duration_ms=duration_ms,
        rows=_extract_rows(payload),
        total_count=_extract_total(payload),
        next_link=_extract_next_link(payload),
        raw=payload,
    )


async def probe(endpoint: Any, url: str) -> dict:
    """Liveness check: report status and latency instead of raising."""
    started = time.perf_counter()
    try:
        result = await execute(endpoint, url)
    except UpstreamError as exc:
        return {
            "ok": False,
            "status_code": exc.status_code,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "url": url,
            "error": exc.message,
            "detail": exc.body,
        }
    return {
        "ok": True,
        "status_code": result.status_code,
        "latency_ms": result.duration_ms,
        "url": url,
        "error": None,
        "detail": f"{result.count} row(s) returned.",
    }
