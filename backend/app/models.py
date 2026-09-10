"""SQLModel tables.

The `endpoint` table mirrors the connection-relevant fields of maas-collector's
ODataCollectorConfiguration so both systems describe an interface the same way.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Endpoint(SQLModel, table=True):
    """A registered OData service. `name` is the equivalent of `interface_name`."""

    __tablename__ = "endpoint"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    description: str = ""
    tags: str = ""

    # Connection. base_url == maas-collector `product_url`.
    base_url: str
    entity_location: str = "/odata/v1/"
    default_entity_set: str = "Products"
    odata_version: str = "v4"

    verify_ssl: bool = True
    timeout: int = 60
    default_page_size: int = 100

    # Auth: none | basic | static_token | oauth2
    auth_method: str = "none"
    token_field_header: str = "Authorization"

    client_username: str = ""
    token_url: str = ""
    client_id: str = ""
    scope: str = ""
    grant_type: str = "password"

    # Encrypted at rest, never returned by the API.
    enc_client_password: Optional[str] = None
    enc_client_secret: Optional[str] = None
    enc_static_token: Optional[str] = None
    enc_oauth_basic_credential: Optional[str] = None

    last_probe_at: Optional[datetime] = None
    last_probe_status: Optional[int] = None
    last_probe_latency_ms: Optional[int] = None
    last_probe_error: Optional[str] = None

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class SavedQuery(SQLModel, table=True):
    """A reusable query. With endpoint_id NULL it is a template usable anywhere."""

    __tablename__ = "saved_query"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    description: str = ""
    tags: str = ""
    is_builtin: bool = False

    endpoint_id: Optional[int] = Field(default=None, foreign_key="endpoint.id", index=True)

    entity_set: str = ""
    mode: str = "builder"  # builder | raw

    spec_json: str = "{}"
    raw_query: str = ""
    params_json: str = "[]"

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class QueryRun(SQLModel, table=True):
    """One executed query, for the history view."""

    __tablename__ = "query_run"

    id: Optional[int] = Field(default=None, primary_key=True)
    endpoint_id: Optional[int] = Field(default=None, foreign_key="endpoint.id", index=True)
    endpoint_name: str = ""
    saved_query_id: Optional[int] = Field(default=None, foreign_key="saved_query.id")
    saved_query_name: str = ""

    url: str = ""
    status_code: Optional[int] = None
    duration_ms: Optional[int] = None
    result_count: Optional[int] = None
    error: Optional[str] = None

    # Enough to reopen the run in the workspace.
    spec_json: str = "{}"

    created_at: datetime = Field(default_factory=utcnow, index=True)
