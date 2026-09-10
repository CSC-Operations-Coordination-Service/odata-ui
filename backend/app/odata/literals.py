"""Formatting of OData literal values.

Everything a user types in the web form passes through here before it reaches a
$filter. maas-collector interpolates values straight into an f-string, which breaks
on any value containing a quote; we escape properly instead.
"""

import re
from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import UUID

# Value types accepted from the UI.
VALUE_TYPES = ("string", "number", "boolean", "guid", "datetime", "null", "raw")

# A property path such as `Name`, `Collection/Name`, `Attributes/Value`.
_FIELD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(/[A-Za-z_][A-Za-z0-9_]*)*$")


class LiteralError(ValueError):
    """Raised when a value cannot be represented as the requested OData type."""


def escape_string(value: str) -> str:
    """Escape a string for an OData literal: single quotes are doubled."""
    return value.replace("'", "''")


def quote_string(value: str) -> str:
    """Render a string as a quoted OData literal."""
    return f"'{escape_string(value)}'"


def validate_field(field: str) -> str:
    """Reject anything that is not a plain property path.

    Field names are identifiers, never user prose, so a strict whitelist costs nothing
    and stops a field box being used to smuggle filter syntax.
    """
    field = (field or "").strip()
    if not _FIELD_RE.match(field):
        raise LiteralError(
            f"{field!r} is not a valid property name. Use names like 'Name' or "
            "'Collection/Name'."
        )
    return field


def format_datetime(value: Any, odata_version: str = "v4") -> str:
    """Render a datetime literal.

    v4 uses a bare ISO-8601 Zulu timestamp; v3 wraps it in datetime'...' without the
    trailing Z, matching how maas-collector formats its v3 date filters.
    """
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, date):
        moment = datetime(value.year, value.month, value.day)
    else:
        text = str(value).strip()
        if not text:
            raise LiteralError("Empty value for a datetime parameter.")
        try:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise LiteralError(
                f"{value!r} is not a valid date/time. Use ISO-8601, "
                "e.g. 2024-01-31T00:00:00Z."
            ) from exc

    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    zulu = moment.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    if odata_version == "v3":
        return f"datetime'{zulu[:-1]}'"
    return zulu


def format_guid(value: Any, odata_version: str = "v4") -> str:
    """Render a GUID literal, validating it is really a UUID."""
    try:
        parsed = UUID(str(value).strip())
    except (ValueError, AttributeError, TypeError) as exc:
        raise LiteralError(f"{value!r} is not a valid UUID.") from exc
    if odata_version == "v3":
        return f"guid'{parsed}'"
    return str(parsed)


def format_number(value: Any) -> str:
    if isinstance(value, bool):
        raise LiteralError("Expected a number, got a boolean.")
    if isinstance(value, (int, float)):
        return repr(value) if isinstance(value, float) else str(value)
    text = str(value).strip()
    try:
        float(text)
    except ValueError as exc:
        raise LiteralError(f"{value!r} is not a number.") from exc
    return text


def format_boolean(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip().lower()
    if text in ("true", "1", "yes"):
        return "true"
    if text in ("false", "0", "no"):
        return "false"
    raise LiteralError(f"{value!r} is not a boolean.")


def format_literal(
    value: Any, value_type: str = "string", odata_version: str = "v4"
) -> str:
    """Render `value` as an OData literal of `value_type`."""
    if value_type not in VALUE_TYPES:
        raise LiteralError(
            f"Unknown value type {value_type!r}. Expected one of {', '.join(VALUE_TYPES)}."
        )
    if value_type == "null":
        return "null"
    if value is None:
        return "null"
    if value_type == "raw":
        # Explicit opt-out, used only by the raw-filter escape hatch.
        return str(value)
    if value_type == "string":
        return quote_string(str(value))
    if value_type == "number":
        return format_number(value)
    if value_type == "boolean":
        return format_boolean(value)
    if value_type == "guid":
        return format_guid(value, odata_version)
    return format_datetime(value, odata_version)


def format_key_predicate(
    value: Any, value_type: Optional[str] = None, odata_version: str = "v4"
) -> str:
    """Render the key predicate of a by-id lookup: the `X` in `Products(X)`.

    With no explicit type we guess, because "get me this product id" is the single most
    common thing a user does and making them pick a type first would be silly.
    """
    if value_type in (None, "", "auto"):
        text = str(value).strip()
        try:
            return format_guid(text, odata_version)
        except LiteralError:
            pass
        if re.fullmatch(r"-?\d+", text):
            return text
        return quote_string(text)
    return format_literal(value, value_type, odata_version)
