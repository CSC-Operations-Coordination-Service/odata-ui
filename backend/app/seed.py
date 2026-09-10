"""Built-in query templates, inserted on first start.

These cover the questions the app exists to answer: fetch one product by id, find
products whose name contains something, and the usual date/collection filters. They
are endpoint-agnostic (endpoint_id NULL) so they work against any registered service.
"""

import json

from sqlmodel import Session, select

from app.models import SavedQuery

BUILTIN_TEMPLATES = [
    {
        "name": "Product by Id",
        "description": "Fetch a single product by its identifier (GUID or key).",
        "tags": "product,lookup",
        "entity_set": "Products",
        "spec": {"entity_id": "{{id}}"},
        "params": [
            {
                "name": "id",
                "label": "Product Id",
                "type": "string",
                "required": True,
                "help": "The product GUID or key. GUIDs and integers are detected automatically.",
            }
        ],
    },
    {
        "name": "Name contains",
        "description": "Find products whose Name contains a fragment.",
        "tags": "product,search",
        "entity_set": "Products",
        "spec": {
            "clauses": [{"field": "Name", "op": "contains", "value": "{{text}}",
                         "value_type": "string"}],
            "top": 50,
            "orderby": [{"field": "PublicationDate", "direction": "desc"}],
        },
        "params": [
            {"name": "text", "label": "Name contains", "type": "string", "required": True,
             "help": "e.g. S1A_IW_GRDH"}
        ],
    },
    {
        "name": "Name starts with",
        "description": "Find products whose Name starts with a prefix.",
        "tags": "product,search",
        "entity_set": "Products",
        "spec": {
            "clauses": [{"field": "Name", "op": "startswith", "value": "{{prefix}}",
                         "value_type": "string"}],
            "top": 50,
        },
        "params": [
            {"name": "prefix", "label": "Name starts with", "type": "string",
             "required": True, "help": "e.g. S2B_MSIL1C"}
        ],
    },
    {
        "name": "Published between",
        "description": "Products published within a date range.",
        "tags": "product,date",
        "entity_set": "Products",
        "spec": {
            "raw_filter": "PublicationDate ge {{start}} and PublicationDate le {{end}}",
            "orderby": [{"field": "PublicationDate", "direction": "asc"}],
            "top": 100,
        },
        "params": [
            {"name": "start", "label": "From", "type": "datetime", "required": True,
             "help": "ISO-8601, e.g. 2024-01-01T00:00:00Z"},
            {"name": "end", "label": "To", "type": "datetime", "required": True,
             "help": "ISO-8601, e.g. 2024-01-31T23:59:59Z"},
        ],
    },
    {
        "name": "By collection",
        "description": "Products belonging to a given collection.",
        "tags": "product,collection",
        "entity_set": "Products",
        "spec": {
            "raw_filter": "Collection/Name eq {{collection}}",
            "top": 100,
        },
        "params": [
            {"name": "collection", "label": "Collection", "type": "string",
             "required": True, "help": "e.g. SENTINEL-1"}
        ],
    },
    {
        "name": "Latest N products",
        "description": "The most recently published products.",
        "tags": "product,recent",
        "entity_set": "Products",
        "spec": {
            "orderby": [{"field": "PublicationDate", "direction": "desc"}],
            "top": "{{n}}",
        },
        "params": [
            {"name": "n", "label": "How many", "type": "number", "default": 20,
             "required": True}
        ],
    },
]


def seed_builtin_queries(session: Session) -> int:
    """Insert any missing built-in template. Existing rows are left untouched so a
    user's edits to a built-in survive a restart."""
    existing = {
        row.name
        for row in session.exec(select(SavedQuery).where(SavedQuery.is_builtin == True))  # noqa: E712
    }
    added = 0
    for template in BUILTIN_TEMPLATES:
        if template["name"] in existing:
            continue
        spec = dict(template["spec"])
        # `top` may carry a placeholder, which QuerySpec cannot hold as an int; such
        # templates keep it in the raw spec JSON and resolve it at run time.
        session.add(
            SavedQuery(
                name=template["name"],
                description=template["description"],
                tags=template.get("tags", ""),
                is_builtin=True,
                endpoint_id=None,
                entity_set=template.get("entity_set", ""),
                mode="builder",
                spec_json=json.dumps(spec),
                raw_query="",
                params_json=json.dumps(template.get("params", [])),
            )
        )
        added += 1
    if added:
        session.commit()
    return added
