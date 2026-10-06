"""The install check that an agent reads only the connectors it is bound to (M13.7.8, M13.8.1).

Over `brain.ops.acceptance_checks_binding`, against PostgreSQL at head where the suite has one.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest

from brain.ops import acceptance_checks_binding as module
from brain.ops.acceptance import FAILED, PASSED, Check, registered
from tests.unit.test_acceptance import at_head, checks_in, counts
from tests.unit.test_acceptance_hubspot import run_checks

ROOT = Path(__file__).resolve().parents[2]
MODULE = "brain.ops.acceptance_checks_binding"
NAME = "an_agent_reads_only_the_connectors_it_is_bound_to"


def mine() -> dict[str, Check]:
    return {one.name: one for one in registered((MODULE,))}


def test_the_check_is_registered_with_the_leaves_it_proves() -> None:
    """Delete this and the check can close a leaf it does not exercise, or name an id no task
    has."""
    assert {name: one.leaves for name, one in mine().items()} == {NAME: ("M13.7.8", "M13.8.1")}
    wbs = json.loads((ROOT / "docs" / "wbs.json").read_text(encoding="utf-8"))
    assert {"M13.7.8", "M13.8.1"} <= {one for m in wbs["modules"] for one in m["leaf_ids"]}


def test_the_check_is_listed_in_its_page_order() -> None:
    """Delete this and the check can drop out of the module with the page listing one fewer
    row."""
    assert checks_in(MODULE) == [NAME]


@pytest.mark.needs_db
def test_on_a_real_database_an_agent_reads_only_the_sources_it_is_bound_to() -> None:
    """**The check as the worker runs it, against PostgreSQL at head.** It passes, and every table
    holds afterwards what it held before. Delete this and the path from a connector list to a
    refused run can break on a real schema with nothing on the install saying so."""
    with at_head("brain_acceptance_binding") as url:
        before = counts(url)
        outcome = run_checks(url, tuple(mine().values()))
        after = counts(url)
    assert outcome == {NAME: (PASSED, "")}
    assert after == before


def _ignoring_the_list(capabilities: Iterable[Any], connectors: Iterable[str]) -> tuple[Any, ...]:
    """The binding as it was before this change: every capability kept, whatever the list."""
    del connectors
    return tuple(capabilities)


def _dropping_every_source(
    capabilities: Iterable[Any], connectors: Iterable[str]
) -> tuple[Any, ...]:
    """A binding that refuses every connector's entity, whatever the list names."""
    from brain.agents.binding import provider_of

    del connectors
    return tuple(one for one in capabilities if provider_of(one.noun) is None)


@pytest.mark.needs_db
@pytest.mark.parametrize(
    ("broken", "reason"),
    [
        ("ignoring_the_list", module.AN_UNBOUND_AGENT_HOLDING_THE_READS_WAS_ANSWERED),
        ("dropping_every_source", module.THE_BOUND_AGENT_WAS_NOT_ANSWERED),
    ],
)
def test_the_check_fails_where_the_binding_is_broken(
    monkeypatch: pytest.MonkeyPatch, broken: str, reason: str
) -> None:
    """Two breaks in the product, one each way: a ceiling that ignores the connector list, which is
    the defect this check exists for, and one that drops every connector's reads, which a check
    asserting only the refusal would pass. Each fails with its own sentence. Delete this and the
    check can pass with the binding gone, or with every agent cut off from every source."""
    import brain.agents.binding as binding

    replacement = _ignoring_the_list if broken == "ignoring_the_list" else _dropping_every_source
    monkeypatch.setattr(binding, "bound_capabilities", replacement)
    with at_head(f"brain_acceptance_binding_{broken}") as url:
        outcome = run_checks(url, (mine()[NAME],))
    assert outcome[NAME] == (FAILED, reason)
