"""The pagination convention, held against the application's whole API description.

`brain.api.Page` is the convention: `items`, an opaque `next_cursor`, and a route that takes
`cursor` and `limit`. Measured on 2026-09-17 the tracker audit found it on 8 of 36 routers, with
the audit routes carrying a page of their own, and nothing checked the rest. This walks every GET
whose answer carries `next_cursor` in the document `console/scripts/export-openapi.py` builds, so
a new paged route that invents its own shape fails here, not on a console screen.

Task ids: M31.1.4.4
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from brain.app import create_app
from brain.settings import Settings


class Invented(BaseModel):
    """A page shaped by a route for itself, for the sibling test."""

    rows: list[str] = []
    next_cursor: str | None = None


def the_document() -> dict[str, Any]:
    return create_app(Settings(env="development", run_migrations=False)).openapi()


def resolved(document: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    schemas: dict[str, Any] = document["components"]["schemas"]
    while "$ref" in schema:
        schema = schemas[schema["$ref"].rsplit("/", 1)[-1]]
    return schema


def paged_operations(document: dict[str, Any]) -> dict[str, list[str]]:
    """Every GET answering a body with `next_cursor`, and what it breaks of the convention."""
    found: dict[str, list[str]] = {}
    for path, operations in document["paths"].items():
        operation = operations.get("get")
        if operation is None:
            continue
        answer = operation.get("responses", {}).get("200", {})
        schema = answer.get("content", {}).get("application/json", {}).get("schema")
        if schema is None:
            continue
        properties = resolved(document, schema).get("properties", {})
        if "next_cursor" not in properties:
            continue
        query = {p["name"] for p in operation.get("parameters", []) if p.get("in") == "query"}
        broken = [
            *(["no items list"] if properties.get("items", {}).get("type") != "array" else []),
            *([f"no {name} parameter" for name in ("cursor", "limit") if name not in query]),
        ]
        found[f"GET {path}"] = broken
    return found


def test_every_paged_answer_follows_the_one_convention() -> None:
    """Delete this and a paged route can return `rows` and `after`, and the console's one pager
    (`console/src/components/useServerPage.ts`) silently shows the first page for ever."""
    found = paged_operations(the_document())

    assert len(found) >= 10, f"only {len(found)} paged routes found, so the walk is not reading"
    breaking = {name: broken for name, broken in found.items() if broken}
    assert breaking == {}, breaking


def test_the_walk_notices_a_route_that_invents_its_own_page() -> None:
    """The sibling: a walk that found nothing wrong anywhere would satisfy the test above
    whatever the routes answered."""
    app = FastAPI()

    @app.get("/api/v1/invented")
    async def invented(after: str = "") -> Invented:
        return Invented()

    assert paged_operations(app.openapi()) == {
        "GET /api/v1/invented": ["no items list", "no cursor parameter", "no limit parameter"]
    }
