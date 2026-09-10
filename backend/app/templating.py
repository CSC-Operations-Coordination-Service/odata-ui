"""Parameter substitution for saved query templates.

Placeholders are written {{name}}. Values are rendered through the OData literal
formatter for their declared type, so a value containing a quote cannot escape the
literal it sits in.
"""

import re
from typing import Any, Optional

from pydantic import BaseModel

from app.odata.literals import LiteralError, format_literal

PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


class TemplateError(ValueError):
    def __init__(self, message: str, missing: Optional[list] = None):
        super().__init__(message)
        self.message = message
        self.missing = missing or []


class QueryParam(BaseModel):
    name: str
    label: str = ""
    type: str = "string"
    default: Optional[Any] = None
    required: bool = True
    help: str = ""


def find_placeholders(*texts: Optional[str]) -> list[str]:
    """Placeholder names across the given strings, in first-seen order."""
    found: list[str] = []
    for text in texts:
        for match in PLACEHOLDER_RE.finditer(text or ""):
            name = match.group(1)
            if name not in found:
                found.append(name)
    return found


def substitute(
    text: Optional[str],
    params: list[QueryParam],
    values: dict,
    odata_version: str = "v4",
    quote_strings: bool = True,
) -> Optional[str]:
    """Replace every {{name}} in `text` with its rendered literal.

    `quote_strings` is False for places that are already inside quotes or that are not
    filter expressions at all -- an entity id, or a $top value.
    """
    if not text:
        return text
    by_name = {param.name: param for param in params}
    missing: list[str] = []

    def render(match: re.Match) -> str:
        name = match.group(1)
        param = by_name.get(name)
        if name in values and values[name] not in (None, ""):
            value = values[name]
        elif param is not None and param.default not in (None, ""):
            value = param.default
        elif param is not None and not param.required:
            value = None
        else:
            missing.append(name)
            return match.group(0)

        value_type = param.type if param is not None else "string"
        if not quote_strings and value_type == "string":
            return str(value)
        try:
            return format_literal(value, value_type, odata_version)
        except LiteralError as exc:
            raise TemplateError(f"Parameter '{name}': {exc}") from exc

    result = PLACEHOLDER_RE.sub(render, text)
    if missing:
        raise TemplateError(
            "Missing value for: " + ", ".join(sorted(set(missing))), missing=sorted(set(missing))
        )
    return result


# Where a placeholder sits decides how it must be rendered. Inside an expression
# fragment such as raw_filter the value has to become a full OData literal; inside a
# clause value or an entity id the builder does the quoting itself, so substituting a
# quoted literal there would double it.
_EXPRESSION_FIELDS = ("raw_filter", "raw_query", "custom_suffix")


def resolve_spec(
    spec_dict: dict,
    params: list,
    values: dict,
    odata_version: str = "v4",
) -> dict:
    """Return a copy of `spec_dict` with every {{placeholder}} filled in."""
    resolved = dict(spec_dict or {})

    for key in _EXPRESSION_FIELDS:
        if isinstance(resolved.get(key), str):
            resolved[key] = substitute(
                resolved[key], params, values, odata_version, quote_strings=True
            )

    for key in ("entity_set", "entity_id", "entity_id_type"):
        if isinstance(resolved.get(key), str):
            resolved[key] = substitute(
                resolved[key], params, values, odata_version, quote_strings=False
            )

    for key in ("top", "skip"):
        if isinstance(resolved.get(key), str):
            resolved[key] = substitute(
                resolved[key], params, values, odata_version, quote_strings=False
            )

    clauses = resolved.get("clauses")
    if isinstance(clauses, list):
        new_clauses = []
        for clause in clauses:
            if not isinstance(clause, dict):
                continue
            clause = dict(clause)
            for key in ("field", "value"):
                if isinstance(clause.get(key), str):
                    clause[key] = substitute(
                        clause[key], params, values, odata_version, quote_strings=False
                    )
            new_clauses.append(clause)
        resolved["clauses"] = new_clauses

    for key in ("select", "expand"):
        items = resolved.get(key)
        if isinstance(items, list):
            resolved[key] = [
                substitute(item, params, values, odata_version, quote_strings=False)
                if isinstance(item, str) else item
                for item in items
            ]

    orderby = resolved.get("orderby")
    if isinstance(orderby, list):
        new_orderby = []
        for item in orderby:
            if isinstance(item, dict) and isinstance(item.get("field"), str):
                item = dict(item)
                item["field"] = substitute(
                    item["field"], params, values, odata_version, quote_strings=False
                )
            new_orderby.append(item)
        resolved["orderby"] = new_orderby

    return resolved
