"""Request and response models for the API.

Secrets are write-only: they can be set through Create/Update but are never returned,
only advertised through `has_*` flags.
"""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.odata.builder import QuerySpec
from app.templating import QueryParam

AuthMethod = Literal["none", "basic", "static_token", "oauth2"]
ODataVersion = Literal["v3", "v4"]
GrantType = Literal["password", "client_credentials"]

SECRET_FIELDS = {
    "client_password": "enc_client_password",
    "client_secret": "enc_client_secret",
    "static_token": "enc_static_token",
    "oauth_basic_credential": "enc_oauth_basic_credential",
}


class EndpointBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    tags: str = ""

    base_url: str = Field(min_length=1)
    entity_location: str = "/odata/v1/"
    default_entity_set: str = "Products"
    odata_version: ODataVersion = "v4"

    verify_ssl: bool = True
    timeout: int = Field(default=60, ge=1, le=600)
    default_page_size: int = Field(default=100, ge=1, le=5000)

    auth_method: AuthMethod = "none"
    token_field_header: str = "Authorization"

    client_username: str = ""
    token_url: str = ""
    client_id: str = ""
    scope: str = ""
    grant_type: GrantType = "password"

    @field_validator("base_url")
    @classmethod
    def _check_scheme(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith(("http://", "https://")):
            raise ValueError("Base URL must start with http:// or https://")
        return value.rstrip("/")


class EndpointCreate(EndpointBase):
    client_password: Optional[str] = None
    client_secret: Optional[str] = None
    static_token: Optional[str] = None
    oauth_basic_credential: Optional[str] = None


class EndpointUpdate(BaseModel):
    """Every field optional; an omitted secret keeps its stored value, "" clears it."""

    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[str] = None
    base_url: Optional[str] = None
    entity_location: Optional[str] = None
    default_entity_set: Optional[str] = None
    odata_version: Optional[ODataVersion] = None
    verify_ssl: Optional[bool] = None
    timeout: Optional[int] = Field(default=None, ge=1, le=600)
    default_page_size: Optional[int] = Field(default=None, ge=1, le=5000)
    auth_method: Optional[AuthMethod] = None
    token_field_header: Optional[str] = None
    client_username: Optional[str] = None
    token_url: Optional[str] = None
    client_id: Optional[str] = None
    scope: Optional[str] = None
    grant_type: Optional[GrantType] = None

    client_password: Optional[str] = None
    client_secret: Optional[str] = None
    static_token: Optional[str] = None
    oauth_basic_credential: Optional[str] = None


class EndpointRead(EndpointBase):
    id: int
    has_client_password: bool = False
    has_client_secret: bool = False
    has_static_token: bool = False
    has_oauth_basic_credential: bool = False

    last_probe_at: Optional[datetime] = None
    last_probe_status: Optional[int] = None
    last_probe_latency_ms: Optional[int] = None
    last_probe_error: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, endpoint) -> "EndpointRead":
        data = {
            field: getattr(endpoint, field)
            for field in EndpointBase.model_fields
        }
        data["id"] = endpoint.id
        for public, column in SECRET_FIELDS.items():
            data[f"has_{public}"] = bool(getattr(endpoint, column))
        for field in (
            "last_probe_at", "last_probe_status", "last_probe_latency_ms",
            "last_probe_error", "created_at", "updated_at",
        ):
            data[field] = getattr(endpoint, field)
        return cls(**data)


class ProbeResult(BaseModel):
    ok: bool
    status_code: Optional[int] = None
    latency_ms: Optional[int] = None
    url: str
    error: Optional[str] = None
    detail: Optional[str] = None


class PropertyInfo(BaseModel):
    name: str
    type: str = ""
    nullable: bool = True
    is_key: bool = False


class EntitySetInfo(BaseModel):
    name: str
    entity_type: str = ""
    properties: list[PropertyInfo] = Field(default_factory=list)
    navigation_properties: list[str] = Field(default_factory=list)
    keys: list[str] = Field(default_factory=list)


class MetadataResult(BaseModel):
    entity_sets: list[EntitySetInfo] = Field(default_factory=list)
    url: str = ""
    error: Optional[str] = None


class QueryRequest(BaseModel):
    endpoint_id: int
    spec: QuerySpec = Field(default_factory=QuerySpec)
    saved_query_id: Optional[int] = None


class QueryPreview(BaseModel):
    url: str
    filter: str = ""


class QueryResponse(BaseModel):
    url: str
    status_code: int
    duration_ms: int
    count: int
    total_count: Optional[int] = None
    has_next: bool = False
    rows: list[Any] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)


class SavedQueryBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    tags: str = ""
    endpoint_id: Optional[int] = None
    entity_set: str = ""
    mode: Literal["builder", "raw"] = "builder"
    spec: QuerySpec = Field(default_factory=QuerySpec)
    raw_query: str = ""
    params: list[QueryParam] = Field(default_factory=list)


class SavedQueryCreate(SavedQueryBase):
    pass


class SavedQueryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[str] = None
    endpoint_id: Optional[int] = None
    entity_set: Optional[str] = None
    mode: Optional[Literal["builder", "raw"]] = None
    spec: Optional[QuerySpec] = None
    raw_query: Optional[str] = None
    params: Optional[list[QueryParam]] = None


class SavedQueryRead(SavedQueryBase):
    id: int
    is_builtin: bool = False
    created_at: datetime
    updated_at: datetime


class RunSavedQueryRequest(BaseModel):
    endpoint_id: Optional[int] = None
    params: dict = Field(default_factory=dict)
    top: Optional[int] = None
    skip: Optional[int] = None
    preview_only: bool = False


class QueryRunRead(BaseModel):
    id: int
    endpoint_id: Optional[int] = None
    endpoint_name: str = ""
    saved_query_id: Optional[int] = None
    saved_query_name: str = ""
    url: str
    status_code: Optional[int] = None
    duration_ms: Optional[int] = None
    result_count: Optional[int] = None
    error: Optional[str] = None
    spec: QuerySpec = Field(default_factory=QuerySpec)
    created_at: datetime


class ImportRequest(BaseModel):
    """A pasted maas-collector credential/collector JSON document."""

    content: str
    overwrite: bool = False


class ImportedEndpoint(BaseModel):
    name: str
    action: str  # created | updated | skipped
    reason: str = ""


class ImportResult(BaseModel):
    imported: list[ImportedEndpoint] = Field(default_factory=list)
