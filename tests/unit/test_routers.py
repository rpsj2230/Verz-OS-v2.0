"""Every router is mounted, and the order they are mounted in cannot change what a request reaches.

`brain.routers` mounts every router it imports, in the order of their names, which replaced a
hand-kept list at the end of `brain.app.create_app` on 2026-09-29. Two properties make that safe,
and each is held here because each fails silently. A `*_routes` module nobody imported is a screen
whose addresses answer 404 while every test of the module passes against an application it builds
for itself. And two routers that could both match one request would have the winner decided by
the alphabet rather than by anybody, with no test naming either.

Task ids: none
"""

from __future__ import annotations

import importlib
from pathlib import Path

from fastapi import APIRouter, FastAPI

import brain
from brain import routers
from brain.app import create_app
from brain.docs_routes import router as docs_router

SRC = Path(brain.__file__).parent


def overlaps(first: str, second: str) -> bool:
    """Whether one request path could match both templates.

    A `{name}` segment matches any one segment, and a `{name:path}` segment matches whatever is
    left, as Starlette's convertors do. A segment that only starts with a parameter is counted as
    matching anything, which can report an overlap that is not one and never misses one.
    """
    left, right = first.strip("/").split("/"), second.strip("/").split("/")
    for index in range(max(len(left), len(right))):
        one = left[index] if index < len(left) else None
        other = right[index] if index < len(right) else None
        if (one or "").endswith(":path}") or (other or "").endswith(":path}"):
            return True
        if one is None or other is None:
            return False
        if one != other and not one.startswith("{") and not other.startswith("{"):
            return False
    return True


def _addresses(router: APIRouter) -> list[tuple[str, frozenset[str]]]:
    """Each route's path template and methods; a websocket route is its own method."""
    found: list[tuple[str, frozenset[str]]] = []
    for route in router.routes:
        path = getattr(route, "path", None)
        if isinstance(path, str):
            found.append((path, frozenset(getattr(route, "methods", None) or {"WEBSOCKET"})))
    return found


def _mounted(app: FastAPI) -> list[APIRouter]:
    """The routers an application includes, in the order it included them."""
    return [
        route.original_router for route in app.router.routes if hasattr(route, "original_router")
    ]


def test_every_routes_module_is_imported_by_the_registry_and_nothing_else_is() -> None:
    """Delete this and a package that writes `brain/x_routes.py` and forgets its import line in
    `brain.routers` ships a screen whose every address is a 404, which its own tests cannot see
    because each builds an application around the one router. The build tracker's router is the
    one exception: `brain.app` mounts it first, by name, before the registry."""
    modules = sorted(path.stem for path in SRC.glob("*_routes.py") if path.stem != "docs_routes")
    assert len(modules) > 60
    expected = [importlib.import_module(f"brain.{name}").router for name in modules]
    assert [one for one in expected if not any(one is held for held in routers.ROUTERS)] == []
    assert len(routers.ROUTERS) == len(expected)


def test_no_two_routers_answer_one_request() -> None:
    """Delete this and the mount order starts to matter again without anybody knowing. Starlette
    takes the first route that matches, so a path two routers both answer goes to whichever sorts
    first by name, and renaming a module would move a request from one handler to another. Held
    over the build tracker's router too, since it is mounted before all of these."""
    everyone = [docs_router, *routers.ROUTERS]
    found = []
    for at, router in enumerate(everyone):
        for later in everyone[at + 1 :]:
            for path, methods in _addresses(router):
                for other_path, other_methods in _addresses(later):
                    if methods & other_methods and overlaps(path, other_path):
                        found.append((sorted(methods & other_methods), path, other_path))
    assert found == []
    assert sum(len(_addresses(one)) for one in everyone) > 250


def test_the_overlap_reading_sees_an_overlap_and_tells_two_addresses_apart() -> None:
    """Delete this and the test above can pass by never finding anything: a reading that answered
    False for every pair would hold the registry to nothing."""
    assert overlaps("/api/v1/agents/{agent_id}", "/api/v1/agents/templates")
    assert overlaps("/api/v1/agents/{agent_id}", "/api/v1/agents/{name}")
    assert overlaps("/files/{rest:path}", "/files/a/b/c")
    assert not overlaps("/api/v1/agents/{agent_id}", "/api/v1/agents/{agent_id}/stats")
    assert not overlaps("/api/v1/agents", "/api/v1/skills")


def test_the_application_mounts_the_build_tracker_first_and_then_every_registered_router() -> None:
    """Delete this and `create_app` could drop the loop, or mount the registry before the build
    tracker's router, whose `/` has to come after the console's entry and before anything else,
    with the two tests above still green: they read the registry, not the application."""
    assert _mounted(create_app()) == [docs_router, *routers.ROUTERS]
