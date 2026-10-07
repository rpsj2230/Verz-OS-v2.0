"""The wave-three milestone check, passing on PostgreSQL at head and failing with the product broken
the way it would plausibly break.

The database half runs the module as the worker would, against a database at head: the check
passes and leaves nothing. Then it is shown failing: the installed agent absent from the roster the
answer route selects from, an agent whose ceiling reaches no document, an answer route that hands
the model no memory, and an agent answering somebody outside its audience.

Skipped halves: the database tests skip when `DATABASE_URL` is unset, as every `needs_db` test does.

Task ids: M38.2.2.4
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from brain.ops import acceptance_run
from brain.ops.acceptance import FAILED, PASSED, registered
from brain.settings import settings_from
from tests.unit.test_acceptance import at_head, checks_in, counts

MODULE = "brain.ops.acceptance_checks_w3"
WAVE_THREE = "a_template_agent_answers_with_knowledge_and_memory"


# ------------------------------------------------------------------------ the figures
def test_the_module_declares_the_one_check_for_the_milestone() -> None:
    """One check closing M38.2.2.4. Delete this and the check can lose the leaf with the page
    showing the same row, and the milestone closes on a check that never looked."""
    assert [(one.name, one.leaves) for one in registered((MODULE,))] == [
        (WAVE_THREE, ("M38.2.2.4",))
    ]
    assert checks_in(MODULE) == [WAVE_THREE]


def test_the_module_sits_in_the_range_this_package_was_given() -> None:
    """The coordinator gave this package the keys 600 to 699, so two packages cannot share one.
    Delete this and a key outside the range is not noticed until two modules collide."""
    from brain.ops import acceptance_checks_w3 as module

    assert 600 <= module.CHECK_ORDER <= 699


def test_the_agent_the_check_installs_is_one_the_catalogue_ships_and_reads_knowledge() -> None:
    """The milestone's agent is the catalogue's knowledge agent, named here as the id the owner's
    catalogue ships and held against the catalogue itself, so a rename fails this and not the
    check's database half. Delete this and the check can go on installing a template the
    catalogue no longer has, which the database half reports only as a missing agent."""
    from brain.agents.catalogue import CATALOGUE
    from brain.ops.acceptance_checks_w3 import KNOWLEDGE_AGENT

    assert KNOWLEDGE_AGENT == "internal_helpdesk"
    assert KNOWLEDGE_AGENT in {one.identity.template_id for one in CATALOGUE}


# --------------------------------------------------------------------- on an install
@pytest.fixture(scope="module")
def install() -> Iterator[str]:
    with at_head("brain_acceptance_w3") as url:
        yield url


def run_w3(url: str) -> dict[str, tuple[str, str]]:
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


#: What this check writes beyond the suite's list.
ALSO_WRITTEN = (
    "agent.agent",
    "agent.template_version",
    "agent.template_instance",
    "mem.persistent",
    "obs.request_telemetry",
)


def _counts(url: str) -> dict[str, int]:
    from tests.fixtures.scratch_postgres import sql

    both = counts(url)
    # The names are this module's constants, never input.
    both.update(
        {one: int(sql(url, f"SELECT count(*) FROM {one}")[0][0]) for one in ALSO_WRITTEN}  # noqa: S608
    )
    return both


@pytest.mark.needs_db
def test_the_milestone_check_passes_on_an_install_and_leaves_nothing(install: str) -> None:
    """**The module as the worker runs it.** The check passes and nothing it wrote is left: no
    agent, template, memory or request row. Delete this and a check that can never pass on a real
    schema, or one that leaves an agent answering on the owner's install, reaches it first."""
    before = _counts(install)
    assert run_w3(install) == {WAVE_THREE: (PASSED, "")}
    assert _counts(install) == before


def _failed(url: str) -> str:
    [(outcome, reason)] = run_w3(url).values()
    assert outcome == FAILED, reason
    return reason


@pytest.mark.needs_db
def test_an_agent_the_roster_does_not_offer_fails_the_milestone_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The install's agent roster reading none of the stored agents, as an agent that was never
    enabled would be. Delete this and the milestone closes on a question the default agent
    answered, with no agent installed from a template anywhere in it."""
    from brain.gate.roster import StoredAgents
    from brain.ops import acceptance_checks_w3

    def nothing(h: Any) -> Any:
        async def read() -> StoredAgents:
            return StoredAgents(records=())

        return read

    monkeypatch.setattr(acceptance_checks_w3, "roster_over", nothing)
    assert "not answered by the agent installed" in _failed(install)


@pytest.mark.needs_db
def test_an_agent_whose_ceiling_reaches_no_document_fails_the_milestone_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ceiling an installed agent's run is narrowed by implying no row read from the column
    reads it names, which is the defect the wave-three milestone found in every catalogue agent on
    2026-09-14. Delete this and the milestone closes on an agent that answers from no document."""
    from brain.agents import model

    monkeypatch.setattr(model, "records_implied_by", lambda declared: ())
    # With no document to read the run abstains, so the first thing the check sees is no answer.
    assert "through the installed agent was not answered" in _failed(install)


@pytest.mark.needs_db
def test_an_answer_route_that_hands_a_model_no_memory_fails_the_milestone_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The route binding no hints to the lane, so a model answering through an agent is told
    nothing of the asker. Delete this and the milestone closes on an agent that answers with
    knowledge and forgets the person it is answering."""
    from brain import api_routes

    monkeypatch.setattr(api_routes, "with_hints", lambda state, lane, **kwargs: lane)
    assert "not shown the asker's memory" in _failed(install)


@pytest.mark.needs_db
def test_an_agent_answering_somebody_outside_its_audience_fails_the_milestone_check(
    install: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The roster treating every enabled agent as runnable by everybody. Delete this and the
    milestone closes on an agent lending another department a lens it was never offered."""
    from brain.gate import roster

    monkeypatch.setattr(
        roster, "runnable_agent_ids", lambda kept, viewer: {one.agent_id for one in kept}
    )
    assert "outside the agent's audience" in _failed(install)
