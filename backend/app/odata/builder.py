"""Turn a QuerySpec into an OData request URL.

Pure and I/O-free so it can be unit-tested exhaustively, and so /api/query/preview can
show the exact URL that /api/query/run will fetch.
"""

from typing import Any, Literal, Optional
from urllib.parse import quote, urlencode

from pydantic import BaseModel, Field

from app.odata.literals import (
    LiteralError,
    format_key_predicate,
    format_literal,
    quote_string,
    validate_field,
)

# Operators offered by the guided builder.
COMPARISON_OPS = ("eq", "ne", "gt", "ge", "lt", "le")
FUNCTION_OPS = ("contains", "startswith", "endswith")
SET_OPS = ("in",)
UNARY_OPS = ("isnull", "isnotnull")
ALL_OPS = COMPARISON_OPS + FUNCTION_OPS + SET_OPS + UNARY_OPS

# Characters left un-escaped in the query string. OData filters are far easier to read
# and to paste into curl when quotes, parentheses and slashes survive intact; spaces and
# everything else are percent-encoded normally.
_SAFE = "$,()'/:"


class Clause(BaseModel):
    field: str
    op: str = "eq"
    value: Any = None
    # Second operand for range-style use; unused today but kept for `between` later.
    value_type: str = "string"


class OrderBy(BaseModel):
    field: str
    direction: Literal["asc", "desc"] = "asc"


class QuerySpec(BaseModel):
    """Everything the UI can express about a single request."""

    entity_set: str = ""
    entity_id: Optional[str] = None
    entity_id_type: Optional[str] = None

    clauses: list[Clause] = Field(default_factory=list)
    clause_logic: Literal["and", "or"] = "and"
    raw_filter: Optional[str] = None

    select: list[str] = Field(default_factory=list)
    expand: list[str] = Field(default_factory=list)
    orderby: list[OrderBy] = Field(default_factory=list)

    top: Optional[int] = None
    skip: Optional[int] = None
    count: bool = False

    # Appended verbatim, for service-specific options the builder does not model.
    custom_suffix: str = ""

    # Full escape hatch: a complete query string, used when mode == "raw".
    raw_query: Optional[str] = None


class BuildError(ValueError):
    """Raised when a spec cannot be turned into a valid URL."""


def build_clause(clause: Clause, odata_version: str = "v4") -> str:
    """Render one filter clause."""
    try:
        field = validate_field(clause.field)
    except LiteralError as exc:
        raise BuildError(str(exc)) from exc

    op = (clause.op or "eq").strip().lower()
    if op not in ALL_OPS:
        raise BuildError(f"Unsupported operator {clause.op!r}.")

    if op == "isnull":
        return f"{field} eq null"
    if op == "isnotnull":
        return f"{field} ne null"

    try:
        if op in COMPARISON_OPS:
            literal = format_literal(clause.value, clause.value_type, odata_version)
            return f"{field} {op} {literal}"

        if op in FUNCTION_OPS:
            text = quote_string(str(clause.value if clause.value is not None else ""))
            if op == "contains" and odata_version == "v3":
                # v3 has no contains(); substringof takes its arguments the other way round.
                return f"substringof({text},{field})"
            return f"{op}({field},{text})"

        # op == "in"
        values = clause.value
        if isinstance(values, str):
            values = [part.strip() for part in values.split(",") if part.strip()]
        if not values:
            raise BuildError(f"Operator 'in' on {field} needs at least one value.")
        literals = [format_literal(item, clause.value_type, odata_version) for item in values]
        if odata_version == "v3":
            # v3 predates the `in` operator; expand to an OR of equalities.
            return "(" + " or ".join(f"{field} eq {item}" for item in literals) + ")"
        return f"{field} in ({','.join(literals)})"
    except LiteralError as exc:
        raise BuildError(f"{field}: {exc}") from exc


def build_filter(spec: QuerySpec, odata_version: str = "v4") -> str:
    """Render the whole $filter. A raw_filter, when present, wins over the clauses."""
    if spec.raw_filter and spec.raw_filter.strip():
        return spec.raw_filter.strip()
    rendered = [build_clause(clause, odata_version) for clause in spec.clauses]
    if not rendered:
        return ""
    joiner = f" {spec.clause_logic} "
    return joiner.join(rendered)


def _service_root(base_url: str, entity_location: str) -> str:
    """Join the base URL and the entity location with exactly one slash between them."""
    base = (base_url or "").rstrip("/")
    location = (entity_location or "/").strip()
    if not location.startswith("/"):
        location = "/" + location
    if not location.endswith("/"):
        location = location + "/"
    return base + location


def build_url(endpoint: Any, spec: QuerySpec, max_page_size: Optional[int] = None) -> str:
    """Build the full request URL for `spec` against `endpoint`.

    `endpoint` is anything exposing base_url / entity_location / default_entity_set /
    odata_version -- the ORM row or a plain object in tests.
    """
    odata_version = getattr(endpoint, "odata_version", "v4") or "v4"
    entity_set = (spec.entity_set or getattr(endpoint, "default_entity_set", "") or "").strip()
    if not entity_set:
        raise BuildError("No entity set selected.")

    root = _service_root(
        getattr(endpoint, "base_url", ""), getattr(endpoint, "entity_location", "/")
    )
    if not getattr(endpoint, "base_url", ""):
        raise BuildError("Endpoint has no base URL.")

    path = f"{root}{quote(entity_set, safe='')}"

    if spec.entity_id not in (None, ""):
        try:
            key = format_key_predicate(spec.entity_id, spec.entity_id_type, odata_version)
        except LiteralError as exc:
            raise BuildError(str(exc)) from exc
        path = f"{path}({key})"

    # A raw query string bypasses the builder entirely.
    if spec.raw_query and spec.raw_query.strip():
        raw = spec.raw_query.strip().lstrip("?&")
        return f"{path}?{raw}" if raw else path

    params: list[tuple[str, str]] = []

    filter_text = build_filter(spec, odata_version)
    # A key predicate already identifies one entity, so a filter alongside it is ignored.
    if filter_text and spec.entity_id in (None, ""):
        params.append(("$filter", filter_text))

    if spec.select:
        params.append(("$select", ",".join(validate_field(f) for f in spec.select)))
    if spec.expand:
        params.append(("$expand", ",".join(validate_field(f) for f in spec.expand)))
    if spec.orderby:
        params.append(
            (
                "$orderby",
                ",".join(
                    f"{validate_field(item.field)} {item.direction}" for item in spec.orderby
                ),
            )
        )

    if spec.top is not None:
        top = int(spec.top)
        if top < 0:
            raise BuildError("$top cannot be negative.")
        if max_page_size:
            top = min(top, max_page_size)
        params.append(("$top", str(top)))
    if spec.skip:
        skip = int(spec.skip)
        if skip < 0:
            raise BuildError("$skip cannot be negative.")
        params.append(("$skip", str(skip)))

    if spec.count:
        # v3 spells the same idea $inlinecount=allpages.
        if odata_version == "v3":
            params.append(("$inlinecount", "allpages"))
        else:
            params.append(("$count", "true"))

    try:
        query = urlencode(params, quote_via=quote, safe=_SAFE)
    except LiteralError as exc:  # pragma: no cover - defensive
        raise BuildError(str(exc)) from exc

    suffix = (spec.custom_suffix or "").strip()
    if suffix:
        suffix = suffix.lstrip("&")
        query = f"{query}&{suffix}" if query else suffix

    return f"{path}?{query}" if query else path


def build_probe_url(endpoint: Any) -> str:
    """A cheap liveness query: one row from the default entity set.

    Same idea as maas-collector's build_probe_query, minus the date filter -- we only
    want to know that the service answers and that our credentials are accepted.
    """
    spec = QuerySpec(entity_set=getattr(endpoint, "default_entity_set", "") or "Products", top=1)
    return build_url(endpoint, spec)


def build_metadata_url(endpoint: Any) -> str:
    root = _service_root(
        getattr(endpoint, "base_url", ""), getattr(endpoint, "entity_location", "/")
    )
    return f"{root}$metadata"
