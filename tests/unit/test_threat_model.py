"""The threat model, held to the surfaces an install actually exposes.

`docs/install/threat-model.md` promises two directions: every first path segment the application
serves has a row and every path row is served, and every service reachable from outside the
compose network has a row. The registers are read here, as in `test_install_docs.py`, so what is
checked is the application and the compose files rather than a copy of them.

Each refusal is produced against a page built to fail as well as passed against the real one,
so `threat_model_gaps` cannot be replaced with `return ()` with this file green.

Task ids: M38.5.2
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from brain.app import create_app
from brain.ops.install_docs import (
    PORTS_MARKER,
    SURFACES_MARKER,
    first_segment,
    table_after,
    threat_model_gaps,
)

REPO = Path(__file__).resolve().parents[2]
GUIDES = REPO / "docs" / "install"


def served() -> set[str]:
    """Every path the application routes: the schema's paths and the unlisted top-level ones.

    The default settings are not production, so `/docs`, `/redoc` and `/openapi.json` are among
    them; the page gives them a row that says production switches them off.
    """
    app = create_app()
    paths = set(app.openapi()["paths"])
    paths.update(path for route in app.routes if (path := getattr(route, "path", None)))
    return paths


def published() -> set[str]:
    """Services any compose file publishes a host port for."""
    found: set[str] = set()
    for path in sorted(REPO.glob("docker-compose*.yml")):
        document: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for name, body in (document.get("services") or {}).items():
            if isinstance(body, dict) and body.get("ports"):
                found.add(str(name))
    return found


def proxied() -> set[str]:
    """Services the network guide says a browser reaches through the proxy."""
    network = (GUIDES / "network.md").read_text(encoding="utf-8")
    return {
        cells[0].strip("` ")
        for cells in table_after(network, PORTS_MARKER)
        if len(cells) >= 3 and "through your proxy" in cells[2]
    }


def page(*rows: str) -> str:
    body = "\n".join(f"| {one} | x | y | z |" for one in rows)
    header = "| Surface | Who | Wants | Stops |\n| --- | --- | --- | --- |"
    return f"{SURFACES_MARKER}\n\n{header}\n{body}\n"


def test_the_registers_read_something() -> None:
    """An empty register makes every direction pass, so each is asserted to hold what it must."""
    assert {"/api", "/health", "/"} <= {first_segment(one) for one in served()}
    assert {"pgbouncer", "seaweedfs"} <= published()
    assert {"keycloak", "activepieces", "langfuse-web"} <= proxied()


def test_the_threat_model_covers_every_surface_the_install_exposes() -> None:
    guide = (GUIDES / "threat-model.md").read_text(encoding="utf-8")
    assert threat_model_gaps(guide, served=served(), reachable=published() | proxied()) == ()


def test_a_served_path_with_no_row_is_a_finding() -> None:
    found = threat_model_gaps(page("`/`"), served={"/", "/api/status.json"}, reachable=())
    assert found == ("/api: the application serves it and the threat model has no row for it",)


def test_a_row_for_a_path_nobody_serves_is_a_finding() -> None:
    found = threat_model_gaps(page("`/`", "`/gone`"), served={"/"}, reachable=())
    assert len(found) == 1 and found[0].startswith("/gone: a row for a path")


def test_a_reachable_service_with_no_row_is_a_finding_and_prose_rows_are_not() -> None:
    found = threat_model_gaps(
        page("`/`", "`keycloak`", "`ssh`"), served={"/"}, reachable={"keycloak", "pgbouncer"}
    )
    assert len(found) == 1 and found[0].startswith("pgbouncer: reachable from outside")


def test_several_paths_in_one_cell_are_each_a_row() -> None:
    guide = page("`/`", "`/docs`, `/redoc`, `/openapi.json`")
    assert (
        threat_model_gaps(guide, served={"/", "/docs", "/redoc", "/openapi.json"}, reachable=())
        == ()
    )


def test_the_root_and_a_nested_path_have_the_segments_the_page_uses() -> None:
    assert first_segment("/") == "/"
    assert first_segment("/api/status.json") == "/api"
    assert first_segment("/openapi.json") == "/openapi.json"
