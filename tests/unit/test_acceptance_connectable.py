"""The connectable-source acceptance checks: registered, passing on a real schema, and able to fail.

The database half builds PostgreSQL to head and runs the nine checks as the worker would, then runs
them against the product broken where each proves something: the source's own half (its records
answering nothing on Ask, a Drive file never read, Connect Lark's save switching no Base on), the
install half (a connector the install serves read as not serving, so no agent naming it installs
ready), and the agent half (a run that ignores its agent's ceiling, so an agent bound to nothing
answers from the source). Each fails with its own sentence, and every table the checks write holds
afterwards what it held before.

Task ids: M11.9.3, M11.9.4, M11.9.6, M11.9.7, M11.9.8, M11.9.10, M11.9.11, M11.9.13, M11.9.14
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from brain.ops.acceptance import FAILED, NOT_RUN, PASSED, Check, check_modules, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_hubspot import run_checks

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_connectable"

#: Each check, in page order, and the one leaf it proves.
LEAVES = {
    "google_drive_is_ready_for_a_person_and_its_agent_once_connected": "M11.9.3",
    "lark_is_ready_for_a_person_and_its_agent_once_connected": "M11.9.4",
    "freshdesk_is_ready_for_a_person_and_its_agent_once_connected": "M11.9.6",
    "xero_is_ready_for_a_person_and_its_agent_once_connected": "M11.9.7",
    "the_crm_is_ready_for_a_person_and_its_agent_once_connected": "M11.9.8",
    "domains_are_ready_for_a_person_and_their_agent_once_connected": "M11.9.10",
    "cloudflare_is_ready_for_a_person_and_its_agent_once_connected": "M11.9.11",
    "analytics_is_ready_for_a_person_and_its_agent_once_connected": "M11.9.13",
    "search_console_is_ready_for_a_person_and_an_agent_once_connected": "M11.9.14",
}

#: Each row source's check, by the connector its records are classified under.
ROW_SOURCES = {
    "freshdesk": "freshdesk_is_ready_for_a_person_and_its_agent_once_connected",
    "xero": "xero_is_ready_for_a_person_and_its_agent_once_connected",
    "hubspot": "the_crm_is_ready_for_a_person_and_its_agent_once_connected",
    "domains": "domains_are_ready_for_a_person_and_their_agent_once_connected",
    "cloudflare": "cloudflare_is_ready_for_a_person_and_its_agent_once_connected",
    "google_analytics": "analytics_is_ready_for_a_person_and_its_agent_once_connected",
    "search_console": "search_console_is_ready_for_a_person_and_an_agent_once_connected",
}

DRIVE = "google_drive_is_ready_for_a_person_and_its_agent_once_connected"
LARK = "lark_is_ready_for_a_person_and_its_agent_once_connected"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_connectable_checks_are_registered_with_the_leaves_they_prove() -> None:
    """Delete this and a check can close a leaf it does not exercise, or name an id no task has."""
    assert {name: one.leaves for name, one in mine().items()} == {
        name: (leaf,) for name, leaf in LEAVES.items()
    }
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    leaves = {one for module in wbs["modules"] for one in module["leaf_ids"]}
    assert set(LEAVES.values()) <= leaves


def test_the_connectable_checks_are_listed_in_their_page_order() -> None:
    """Every check this module registers, in the order the Install page lists them, from a module
    the suite finds. Delete this and a check can drop out of the module, or the module out of the
    suite, with the page simply listing fewer rows."""
    assert MODULE in check_modules()
    assert checks_in(MODULE) == list(LEAVES)


@pytest.mark.needs_db
def test_on_a_real_database_each_source_is_ready_for_a_person_and_an_agent() -> None:
    """**The nine checks as the worker runs them, against PostgreSQL at head.** Each passes, and
    every table a check writes holds afterwards what it held before. Delete this and a source can
    be connected from the console and still need a server step before a person or an agent can
    use it, with nothing on the owner's install saying so."""
    with at_head("brain_acceptance_connectable") as url:
        before = counts(url)
        outcome = run_checks(url, tuple(mine().values()))
        after = counts(url)
    assert outcome == dict.fromkeys(LEAVES, (PASSED, ""))
    assert after == before


@pytest.mark.needs_db
@pytest.mark.parametrize("connector", sorted(ROW_SOURCES))
def test_a_row_source_whose_records_answer_nothing_fails_its_check(
    monkeypatch: pytest.MonkeyPatch, connector: str
) -> None:
    """The source's half of M11.9.6, M11.9.7, M11.9.8, M11.9.10, M11.9.11, M11.9.13 and M11.9.14:
    the source's records classified for nothing, which is where HubSpot stood before 2026-09-30,
    so connecting it puts no question on Ask. Its check fails saying so. Delete this and a source
    can be connected from the console and answer nobody with its check green."""
    import brain.knowledge.connector_rows as connector_rows

    kept = {k: v for k, v in connector_rows.CONNECTOR_ROW_ENTITIES.items() if k != connector}
    monkeypatch.setattr(connector_rows, "CONNECTOR_ROW_ENTITIES", kept)
    name = ROW_SOURCES[connector]
    with at_head(f"brain_acceptance_connectable_{connector}") as url:
        outcome = run_checks(url, (mine()[name],))
    assert outcome[name] == (
        FAILED,
        "a source connected from the console contributed no question to Ask",
    )


@pytest.mark.needs_db
def test_a_drive_file_never_read_fails_the_drive_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """The source's half of M11.9.3: the passage reader never reads a file's words from Drive, so
    nobody is handed them. The Drive check fails at the person's question. Delete this and Drive
    can be connected and walked with no question ever answered from it."""
    from brain.ops import drive_passages

    def never(self: Any, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        del self, args, kwargs
        return ()

    monkeypatch.setattr(drive_passages.DrivePassages, "read", never)
    with at_head("brain_acceptance_connectable_drive") as url:
        outcome = run_checks(url, (mine()[DRIVE],))
    assert outcome[DRIVE] == (
        FAILED,
        "a permitted person's question was not answered from the source",
    )


@pytest.mark.needs_db
def test_a_lark_save_that_switches_no_base_on_fails_the_lark_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The console's half of M11.9.4: Connect Lark's save keeps the uses and leaves the Base out,
    so the next question reads no Base. The Lark check fails saying so. Delete this and Lark can be
    connected from the console with a server step still needed before anybody can ask it."""
    from brain.ops import lark_connect

    original = lark_connect.settings_for

    def without_the_base(*args: Any, **kwargs: Any) -> dict[str, str]:
        made = original(*args, **kwargs)
        made.pop("INSTALL_LARK_BASE", None)
        return made

    monkeypatch.setattr(lark_connect, "settings_for", without_the_base)
    with at_head("brain_acceptance_connectable_lark") as url:
        outcome = run_checks(url, (mine()[LARK],))
    assert outcome[LARK] == (
        FAILED,
        "the Base Connect Lark saved was not switched on for the next question",
    )


@pytest.mark.needs_db
def test_a_source_the_install_reads_as_not_serving_fails_every_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The install half of all nine leaves: every connector an agent names read as not serving, as
    `connectors_of` read every source before 2026-09-30, so an agent naming a source connected
    from the console does not install ready. Every check fails saying so. Delete this and an agent
    bound to a source could need its connector registered at the server first."""
    from brain.agents import install

    def never_ready(names: tuple[str, ...], registry: Any) -> Any:
        return tuple(
            install.ConnectorReadiness(name=name, state=None, ready=False) for name in names
        )

    monkeypatch.setattr(install, "connector_readiness", never_ready)
    with at_head("brain_acceptance_connectable_unserved") as url:
        before = counts(url)
        outcome = run_checks(url, tuple(mine().values()))
        after = counts(url)
    assert outcome == dict.fromkeys(
        LEAVES, (FAILED, "an agent naming a source this install serves was not ready")
    )
    assert after == before


@pytest.mark.needs_db
def test_an_agent_whose_ceiling_drops_what_it_was_bound_to_fails_every_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The agent half of all nine leaves, the other way: an agent's ceiling built without the reads
    its template names, so the agent bound to a source reaches nothing in it. Every check fails at
    the bound agent. Delete this and a check would pass with the bound agent's own answer never
    looked at, since the person's answer is the same words."""
    from brain.console import workspace_capabilities
    from brain.core.entitlement import EntitlementSet

    def nothing(record: Any) -> EntitlementSet:
        return EntitlementSet(principal_id=f"agent:{record.agent_id}", grants=())

    monkeypatch.setattr(workspace_capabilities, "entitlement_ceiling", nothing)
    with at_head("brain_acceptance_connectable_unbound") as url:
        outcome = run_checks(url, tuple(mine().values()))
    assert outcome == dict.fromkeys(
        LEAVES, (FAILED, "an agent bound to a connected source could not use it")
    )


@pytest.mark.needs_db
def test_a_run_that_ignores_its_agent_s_ceiling_fails_every_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The agent half of all nine leaves: a run computed at the caller's reach whatever the agent,
    so an agent bound to no source answers from it. Every check fails at the unbound agent. Delete
    this and a check would pass for an agent that answers because it ignores what it is bound to,
    which proves nothing about binding."""
    from brain.core.entitlement import EntitlementSet

    def caller_only(self: EntitlementSet, ceiling: EntitlementSet, now: Any = None) -> Any:
        del ceiling, now
        return self

    monkeypatch.setattr(EntitlementSet, "intersect", caller_only)
    with at_head("brain_acceptance_connectable_ceiling") as url:
        outcome = run_checks(url, tuple(mine().values()))
    assert outcome == dict.fromkeys(
        LEAVES, (FAILED, "an agent not bound to a source was answered from it")
    )


@pytest.mark.needs_db
def test_a_source_connected_here_already_is_not_connected_again() -> None:
    """`THIS_SOURCE_IS_CONNECTED_HERE_ALREADY`: on an install with HubSpot connected, the CRM's
    check steps aside rather than connecting a second HubSpot. Delete this and a check could move
    the owner's own connection aside, or fail on an install whose source is connected."""
    from brain.ops.acceptance_checks_connectable import THIS_SOURCE_IS_CONNECTED_HERE_ALREADY
    from tests.fixtures.scratch_postgres import sql

    name = ROW_SOURCES["hubspot"]
    with at_head("brain_acceptance_connectable_connected") as url:
        sql(
            url,
            "INSERT INTO ops.connector_connection (connector, settings, digest, connected_by)"
            " VALUES ('hubspot', '{}'::jsonb, %s, 'u_admin')",
            "0" * 64,
        )
        outcome = run_checks(url, (mine()[name],))
    assert outcome[name] == (NOT_RUN, THIS_SOURCE_IS_CONNECTED_HERE_ALREADY)
