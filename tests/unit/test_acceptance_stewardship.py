"""The install check for stewardship, passing on PostgreSQL at head and failing where it should.

The pure half holds the module to its one leaf and holds the two capabilities the check's person
grants themselves to the things each must reach and must not. The database half runs the check as
the worker would: it passes and leaves nothing. Then it is shown failing three ways, with the
product broken the way each would plausibly break: a naming that writes nothing, a steward rule
that admits anybody, and a notice list that tells nobody.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M7.7.2
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.ops.acceptance_stewardship import INVOICE_FIELD, KNOWLEDGE_FIELD
from brain.settings import settings_from
from tests.unit.test_acceptance import INSTALL, at_head, counts

MODULE = "brain.ops.acceptance_stewardship"
NAMED = "a_steward_is_named_and_told_of_access_somebody_gave_themselves"


# ------------------------------------------------------------------------ the figures
def test_the_module_declares_one_check_for_its_one_leaf() -> None:
    """One check, for M7.7.2 alone. Delete this and the check can start claiming the document
    hand-over's leaf, which the document's whole life already proves on its own."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [(NAMED, ("M7.7.2",))]


def test_each_self_granted_field_reaches_its_own_thing_and_not_the_other() -> None:
    """The invoice field touches what the source declares and not a document's capabilities, and
    the knowledge field the reverse. Delete this and the two fields can be changed so that both
    stewards are told of both grants, which the check would then report as a product failure."""
    from brain.connectors.manifest import manifest_digest
    from brain.core.entitlement import Capability
    from brain.identity.data_steward import declared_capabilities
    from brain.identity.stewardship import touches
    from brain.ops.acceptance_checks_connectors import SOURCE, _settings
    from brain.ops.connectable import manifest_for
    from brain.stewardship_routes import DOCUMENT_REACHED_BY

    manifest = manifest_for(SOURCE, _settings())
    assert manifest_digest(manifest)
    declared = tuple(Capability(value=one) for one in declared_capabilities(manifest))
    invoice, knowledge = Capability(value=INVOICE_FIELD), Capability(value=KNOWLEDGE_FIELD)
    assert any(touches(invoice, one) for one in declared)
    assert not any(touches(invoice, one) for one in DOCUMENT_REACHED_BY)
    assert any(touches(knowledge, one) for one in DOCUMENT_REACHED_BY)
    assert not any(touches(knowledge, one) for one in declared)


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_stewardship") as url:
        yield url


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in INSTALL.items():
        monkeypatch.setenv(name, value)


def run_named(url: str) -> dict[str, tuple[str, str]]:
    from brain.db import normalise_database_url

    settings = settings_from({"BRAIN_DATABASE_URL": url})
    _, results = asyncio.run(
        acceptance_run.run_acceptance(
            normalise_database_url(url),
            settings=settings,
            commit="abc1234",
            checks=list(registered((MODULE,))),
            force=True,
        )
    )
    return {one.name: (one.outcome, one.reason) for one in results}


@pytest.mark.needs_db
def test_stewardship_passes_on_an_install_and_leaves_nothing(
    install: str, configured: None
) -> None:
    """**The check as the worker runs it.** It passes, and nothing it wrote is left: the steward
    row, the self-grants and their records, the document and the connection. Delete this and a
    check that can never pass on a real schema, or one that commits a steward, reaches the owner's
    server first."""
    before = counts(install)
    assert run_named(install) == {NAMED: (PASSED, "")}
    assert counts(install) == before


def _failed(url: str) -> str:
    [(outcome, reason)] = run_named(url).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_a_naming_that_writes_nothing_fails_the_check(
    install: str, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The store answering a naming without writing its row. Delete this and M7.7.2 closes with a
    steward form that changes nothing."""
    from brain.ops import stewardship_store

    async def forgetful(self: Any, connector: str, steward_id: str, **kw: Any) -> Any:
        return None

    monkeypatch.setattr(stewardship_store.StoredStewardship, "name", forgetful)
    assert "did not name the steward it was just given" in _failed(install)


@pytest.mark.needs_db
def test_a_steward_rule_that_admits_anybody_fails_the_check(
    install: str, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`may_steward` answering yes for everybody. Delete this and M7.7.2 closes with a source
    handed to somebody who can do nothing about it."""
    from brain import connector_routes

    async def anybody(*args: Any, **kw: Any) -> bool:
        return True

    monkeypatch.setattr(connector_routes, "may_steward", anybody)
    assert "cannot reach the source could be its steward" in _failed(install)


@pytest.mark.needs_db
def test_a_notice_list_that_tells_nobody_fails_the_check(
    install: str, configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`notices_for` telling nobody. Delete this and M7.7.2 closes on a self-grant nobody hears of,
    which is the misuse the leaf exists to surface."""
    from brain.identity import stewardship

    monkeypatch.setattr(stewardship, "notices_for", lambda *args, **kw: ())
    assert "source's steward was not told" in _failed(install)
