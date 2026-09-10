"""CRUD, connection testing and metadata discovery for OData endpoints."""

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.auth import token_cache
from app.config import get_settings
from app.crypto import encrypt
from app.db import get_session
from app.models import Endpoint
from app.odata import metadata as metadata_module
from app.odata.builder import BuildError, build_probe_url
from app.odata.client import probe as probe_endpoint
from app.schemas import (
    EndpointCreate,
    EndpointRead,
    EndpointUpdate,
    ImportedEndpoint,
    ImportRequest,
    ImportResult,
    MetadataResult,
    ProbeResult,
    SECRET_FIELDS,
)

router = APIRouter(prefix="/api/endpoints", tags=["endpoints"])


def get_endpoint_or_404(endpoint_id: int, session: Session) -> Endpoint:
    endpoint = session.get(Endpoint, endpoint_id)
    if endpoint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No endpoint with id {endpoint_id}.")
    return endpoint


def _assert_name_free(session: Session, name: str, exclude_id: Optional[int] = None) -> None:
    statement = select(Endpoint).where(Endpoint.name == name)
    existing = session.exec(statement).first()
    if existing is not None and existing.id != exclude_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"An endpoint named {name!r} already exists."
        )


@router.get("", response_model=list[EndpointRead])
def list_endpoints(session: Session = Depends(get_session)):
    rows = session.exec(select(Endpoint).order_by(Endpoint.name)).all()
    return [EndpointRead.from_model(row) for row in rows]


@router.post("", response_model=EndpointRead, status_code=status.HTTP_201_CREATED)
def create_endpoint(payload: EndpointCreate, session: Session = Depends(get_session)):
    _assert_name_free(session, payload.name)
    data = payload.model_dump(exclude=set(SECRET_FIELDS))
    endpoint = Endpoint(**data)
    for public, column in SECRET_FIELDS.items():
        setattr(endpoint, column, encrypt(getattr(payload, public, None)))
    session.add(endpoint)
    session.commit()
    session.refresh(endpoint)
    return EndpointRead.from_model(endpoint)


@router.get("/{endpoint_id}", response_model=EndpointRead)
def read_endpoint(endpoint_id: int, session: Session = Depends(get_session)):
    return EndpointRead.from_model(get_endpoint_or_404(endpoint_id, session))


@router.patch("/{endpoint_id}", response_model=EndpointRead)
def update_endpoint(
    endpoint_id: int, payload: EndpointUpdate, session: Session = Depends(get_session)
):
    endpoint = get_endpoint_or_404(endpoint_id, session)
    changes = payload.model_dump(exclude_unset=True)

    if "name" in changes and changes["name"] != endpoint.name:
        _assert_name_free(session, changes["name"], exclude_id=endpoint_id)

    for public, column in SECRET_FIELDS.items():
        if public in changes:
            # Omitted keeps the stored secret; "" clears it.
            setattr(endpoint, column, encrypt(changes.pop(public)))

    for field, value in changes.items():
        setattr(endpoint, field, value)
    endpoint.updated_at = datetime.now(timezone.utc)

    session.add(endpoint)
    session.commit()
    session.refresh(endpoint)

    # Credentials or the service root may have moved; drop anything cached about it.
    token_cache.invalidate(endpoint_id)
    metadata_module.invalidate(endpoint_id)
    return EndpointRead.from_model(endpoint)


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_endpoint(endpoint_id: int, session: Session = Depends(get_session)):
    endpoint = get_endpoint_or_404(endpoint_id, session)
    session.delete(endpoint)
    session.commit()
    token_cache.invalidate(endpoint_id)
    metadata_module.invalidate(endpoint_id)
    return None


@router.post("/{endpoint_id}/probe", response_model=ProbeResult)
async def probe(endpoint_id: int, session: Session = Depends(get_session)):
    """Ask the service for a single row: proves it is reachable and our auth works."""
    endpoint = get_endpoint_or_404(endpoint_id, session)
    try:
        url = build_probe_url(endpoint)
    except BuildError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    result = await probe_endpoint(endpoint, url)

    endpoint.last_probe_at = datetime.now(timezone.utc)
    endpoint.last_probe_status = result["status_code"]
    endpoint.last_probe_latency_ms = result["latency_ms"]
    endpoint.last_probe_error = result["error"]
    session.add(endpoint)
    session.commit()
    return ProbeResult(**result)


@router.get("/{endpoint_id}/metadata", response_model=MetadataResult)
async def read_metadata(
    endpoint_id: int, refresh: bool = False, session: Session = Depends(get_session)
):
    """Entity sets and their properties, for the builder's dropdowns.

    Never fails the request: a service without a usable $metadata simply yields an
    empty list plus an explanation, and the UI falls back to free text.
    """
    endpoint = get_endpoint_or_404(endpoint_id, session)
    settings = get_settings()
    result = await metadata_module.fetch_metadata(
        endpoint, ttl=settings.metadata_cache_ttl, force=refresh
    )
    return MetadataResult(**result)


# Mapping from maas-collector interface keys to our columns, including the legacy
# aliases that only the importer has to understand.
_IMPORT_FIELDS = {
    "product_url": "base_url",
    "odata_product_url": "base_url",
    "odata_entity_location": "entity_location",
    "odata_entities": "default_entity_set",
    "odata_version": "odata_version",
    "protocol_version": "odata_version",
    "product_per_page": "default_page_size",
    "token_field_header": "token_field_header",
    "client_username": "client_username",
    "token_url": "token_url",
    "client_id": "client_id",
    "scope": "scope",
    "grant_type": "grant_type",
    "auth_timeout": "timeout",
}
_IMPORT_SECRETS = {
    "client_password": "enc_client_password",
    "client_secret": "enc_client_secret",
    "token": "enc_static_token",
    "oauth_basic_credential": "enc_oauth_basic_credential",
}
_AUTH_METHOD_MAP = {"OAuth": "oauth2", "Basic": "basic", "": "none", None: "none"}


@router.post("/import", response_model=ImportResult)
def import_endpoints(payload: ImportRequest, session: Session = Depends(get_session)):
    """Create endpoints from a pasted maas-collector credential file.

    Convenience only -- the app's own source of truth is this database. Accepts the
    `interfaces` list shape, including the legacy odata_* field aliases.
    """
    try:
        document = json.loads(payload.content)
    except json.JSONDecodeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Not valid JSON: {exc}") from exc

    interfaces = document.get("interfaces") if isinstance(document, dict) else None
    if not isinstance(interfaces, list):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Expected a JSON object with an 'interfaces' list, as in a maas-collector "
            "credential file.",
        )

    imported: list[ImportedEndpoint] = []
    for interface in interfaces:
        if not isinstance(interface, dict):
            continue
        name = interface.get("name")
        if not name:
            continue

        base_url = interface.get("product_url") or interface.get("odata_product_url")
        if not base_url:
            imported.append(
                ImportedEndpoint(name=name, action="skipped",
                                 reason="No product_url / odata_product_url.")
            )
            continue

        existing = session.exec(select(Endpoint).where(Endpoint.name == name)).first()
        if existing is not None and not payload.overwrite:
            imported.append(
                ImportedEndpoint(name=name, action="skipped",
                                 reason="Already exists; enable overwrite to replace.")
            )
            continue

        endpoint = existing or Endpoint(name=name, base_url=base_url)
        for source, column in _IMPORT_FIELDS.items():
            if source in interface and interface[source] not in (None, ""):
                value = interface[source]
                if column == "default_page_size":
                    value = max(1, min(int(value), 5000))
                if column == "timeout":
                    value = max(1, min(int(value), 600))
                setattr(endpoint, column, value)
        for source, column in _IMPORT_SECRETS.items():
            if interface.get(source):
                setattr(endpoint, column, encrypt(str(interface[source])))

        auth_method = interface.get("auth_method")
        if auth_method in _AUTH_METHOD_MAP:
            endpoint.auth_method = _AUTH_METHOD_MAP[auth_method]
        elif interface.get("token"):
            endpoint.auth_method = "static_token"
        if endpoint.auth_method == "oauth2" and not endpoint.token_url:
            endpoint.auth_method = "none"

        endpoint.updated_at = datetime.now(timezone.utc)
        session.add(endpoint)
        imported.append(
            ImportedEndpoint(name=name, action="updated" if existing else "created")
        )

    session.commit()
    for entry in imported:
        if entry.action == "updated":
            row = session.exec(select(Endpoint).where(Endpoint.name == entry.name)).first()
            if row is not None:
                token_cache.invalidate(row.id)
                metadata_module.invalidate(row.id)
    return ImportResult(imported=imported)
