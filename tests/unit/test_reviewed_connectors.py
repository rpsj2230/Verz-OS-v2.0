"""The reviewed connectors are read where a declaration is served, and nowhere before a refusal.

`brain.reviewed_connectors.current` is the web process's one read of the approved definitions. The
first half holds where it is called from, read out of the source: the paths that serve a
declaration call it, and the application has no per-request reader, which put a statement in front
of every route's refusal. The second half drives it against a database at head: an approved
definition is served and the registry rebuilt, the same set read again costs the revision check and
rebuilds nothing, and a definition changed after approval is dropped by the next read, which is the
property the per-request reader used to hold.

Task ids: M11.7.8
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, Final

import pytest
from sqlalchemy import event

from brain.ops import connector_catalogue
from brain.ops.custom_connector_store import StoredCustomConnectors
from brain.reviewed_connectors import current
from brain.session import make_session_factory
from tests.fixtures.scratch_postgres import run
from tests.unit.test_acceptance import at_head
from tests.unit.test_automation_owner_store import app_engine
from tests.unit.test_custom_connector import definition

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LONG_AGO: Final = datetime(2019, 3, 4, 9, 0, tzinfo=UTC)
AT: Final = {"ent_hash": "0" * 32, "trace_id": "t-current"}


def _calls_in(function: Any) -> set[str]:
    """The names every call in `function`'s own source is made to."""
    tree = ast.parse(inspect.getsource(function).lstrip())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = node.func
            names.add(target.id if isinstance(target, ast.Name) else getattr(target, "attr", ""))
    return names


@pytest.fixture(autouse=True)
def _nothing_installed() -> Iterator[None]:
    connector_catalogue.install({})
    yield
    connector_catalogue.install({})


def test_every_path_that_serves_a_declaration_reads_the_approved_set_first() -> None:
    """Connect, the Connectors list, the answer route, the records route, the review route and
    the worker's two cycles. Delete this and a path can serve a definition changed after its
    approval, because nothing on it reads the change."""
    from brain import api_routes, connector_routes, custom_connector_routes
    from brain.ops import connector_probe_run, connector_sync_run

    for function in (
        connector_routes.connect,
        connector_routes.connectors,
        connector_routes.edit,
        connector_routes.accept_declaration,
        api_routes.answered_for,
        api_routes.records,
        custom_connector_routes.definitions,
    ):
        assert "reviewed_now" in _calls_in(function), function.__name__
    for cycle in (connector_sync_run.sync_on, connector_probe_run.probe_on):
        assert "refresh" in _calls_in(cycle), cycle.__name__


def test_the_application_reads_the_approved_set_at_start_and_on_no_request_of_its_own() -> None:
    """The per-request reader is gone: `brain.app` reads the approved set in its lifespan and
    nowhere else. Delete this and a middleware can come back that reads the catalogue before
    every route's refusal, so a refused caller causes a statement a screen never needed."""
    import brain.app as app

    tree = ast.parse(inspect.getsource(app))
    callers = {
        outer.name
        for outer in ast.walk(tree)
        if isinstance(outer, ast.AsyncFunctionDef | ast.FunctionDef)
        for node in ast.walk(outer)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"refresh_catalogue", "current", "reviewed_now"}
    }
    assert callers == {"lifespan"}


def test_a_process_with_no_database_reads_nothing_and_changes_nothing() -> None:
    """Delete this and a lite install with no database fails every Connectors request."""
    built: list[int] = []
    state = SimpleNamespace(db_sessions=None, build_tools=lambda: built.append(1))
    assert run(lambda: current(state)) is False
    assert built == []


# ------------------------------------------------------------------ against a database
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_reviewed_connectors") as url:
        yield url


@pytest.mark.needs_db
def test_an_approval_is_served_once_and_a_change_is_dropped_by_the_next_read(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The property, measured: approved, the next read serves it and rebuilds the registry once;
    read again with nothing changed, one statement (the revision check) and no rebuild; changed
    after approval, the next read drops it and rebuilds. Delete this and a definition changed after
    approval can stay served, or every serving path can pay a full read and a rebuild."""
    from brain import reviewed_connectors

    async def recorded(state: Any, registry: Any) -> None:
        # The builder below records the call; a real registry is `build_registry`'s to test.
        del state, registry

    monkeypatch.setattr(reviewed_connectors, "install_tools", recorded)
    name = "widgets_api_current"
    built: list[str] = []
    statements: list[str] = []

    async def work() -> Any:
        engine = app_engine(install)
        event.listen(
            engine.sync_engine,
            "before_cursor_execute",
            lambda *args: statements.append(str(args[2])),
        )
        try:
            sessions = make_session_factory(engine)
            state = SimpleNamespace(db_sessions=sessions, build_tools=lambda: built.append("x"))
            store = StoredCustomConnectors(sessions)
            await store.submit(definition(name=name), by="u_definer", **AT)
            waiting = await _served(state)
            await store.decide(name, approve=True, revision=1, by="u_rev", at=LONG_AGO, **AT)
            approved = await _served(state)
            statements.clear()
            again = await _served(state)
            unchanged = list(statements)
            await store.change(definition(name=name, label="Changed"), by="u_definer", **AT)
            changed = await _served(state)
            return waiting, approved, again, unchanged, changed
        finally:
            await engine.dispose()

    async def _served(state: Any) -> tuple[bool, bool]:
        did = await current(state)
        return did, name in connector_catalogue.reviewed()

    waiting, approved, again, unchanged, changed = run(work)
    assert waiting == (False, False)
    assert approved == (True, True)
    assert again == (False, True)
    reads = [one for one in unchanged if "custom_connector" in one]
    assert len(reads) == 1
    assert "document" not in reads[0]
    assert changed == (True, False)
    assert built == ["x", "x"]
