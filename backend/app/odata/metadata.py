"""Parse an OData $metadata document into entity sets and their properties.

Used to populate the builder's entity-set and field dropdowns. Best-effort by design:
if a service does not expose $metadata, or exposes something we cannot parse, the UI
falls back to free-text input rather than failing the query.
"""

import time
from typing import Any, Optional
from xml.etree import ElementTree

import httpx

from app.auth import token_cache
from app.auth.strategies import AuthError
from app.odata.builder import build_metadata_url
from app.odata.client import make_client

# EDM namespaces differ between OData versions, so we match on local names instead.
_cache: dict[int, tuple[float, dict]] = {}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _findall(element, name: str):
    return [child for child in element.iter() if _local(child.tag) == name]


def parse_metadata(xml_text: str) -> dict:
    """Return {entity_sets: [{name, entity_type, properties: [{name, type, nullable}]}]}."""
    root = ElementTree.fromstring(xml_text)

    # Entity types, keyed by bare name and by namespace-qualified name.
    types: dict[str, dict] = {}
    for schema in _findall(root, "Schema"):
        namespace = schema.get("Namespace", "")
        for entity_type in _findall(schema, "EntityType"):
            name = entity_type.get("Name", "")
            if not name:
                continue
            keys = [
                ref.get("Name")
                for key in _findall(entity_type, "Key")
                for ref in _findall(key, "PropertyRef")
                if ref.get("Name")
            ]
            properties = []
            for prop in _findall(entity_type, "Property"):
                prop_name = prop.get("Name")
                if not prop_name:
                    continue
                properties.append(
                    {
                        "name": prop_name,
                        "type": (prop.get("Type") or "").replace("Edm.", ""),
                        "nullable": prop.get("Nullable", "true") != "false",
                        "is_key": prop_name in keys,
                    }
                )
            navigation = [
                nav.get("Name")
                for nav in _findall(entity_type, "NavigationProperty")
                if nav.get("Name")
            ]
            info = {
                "name": name,
                "properties": properties,
                "navigation_properties": navigation,
                "keys": keys,
            }
            types[name] = info
            if namespace:
                types[f"{namespace}.{name}"] = info

    entity_sets = []
    seen = set()
    for container in _findall(root, "EntityContainer"):
        for entity_set in _findall(container, "EntitySet"):
            set_name = entity_set.get("Name")
            if not set_name or set_name in seen:
                continue
            seen.add(set_name)
            type_name = entity_set.get("EntityType") or ""
            info = types.get(type_name) or types.get(type_name.rsplit(".", 1)[-1]) or {}
            entity_sets.append(
                {
                    "name": set_name,
                    "entity_type": type_name,
                    "properties": info.get("properties", []),
                    "navigation_properties": info.get("navigation_properties", []),
                    "keys": info.get("keys", []),
                }
            )

    entity_sets.sort(key=lambda item: item["name"])
    return {"entity_sets": entity_sets}


def invalidate(endpoint_id: Optional[int]) -> None:
    if endpoint_id is not None:
        _cache.pop(endpoint_id, None)


def clear() -> None:
    _cache.clear()


async def fetch_metadata(endpoint: Any, ttl: int = 600, force: bool = False) -> dict:
    """Fetch and parse $metadata, with a short in-process cache.

    Never raises: on failure it returns an `error` alongside an empty entity-set list.
    """
    endpoint_id = getattr(endpoint, "id", None)
    now = time.time()
    if not force and endpoint_id is not None:
        cached = _cache.get(endpoint_id)
        if cached and now - cached[0] < ttl:
            return cached[1]

    url = build_metadata_url(endpoint)
    result: dict
    async with make_client(endpoint) as client:
        try:
            headers = await token_cache.get_headers(endpoint, client)
            headers.setdefault("Accept", "application/xml")
            response = await client.get(url, headers=headers)
            if not 200 <= response.status_code < 300:
                result = {
                    "entity_sets": [],
                    "url": url,
                    "error": f"$metadata returned HTTP {response.status_code}.",
                }
            else:
                parsed = parse_metadata(response.text)
                result = {"entity_sets": parsed["entity_sets"], "url": url, "error": None}
        except (AuthError, httpx.RequestError) as exc:
            result = {"entity_sets": [], "url": url, "error": str(exc)}
        except ElementTree.ParseError as exc:
            result = {
                "entity_sets": [],
                "url": url,
                "error": f"$metadata is not valid XML: {exc}",
            }

    if endpoint_id is not None and not result.get("error"):
        _cache[endpoint_id] = (now, result)
    return result
