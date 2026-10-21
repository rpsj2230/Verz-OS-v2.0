"""A task started with no agent named is matched to what each agent is for (M40.7.5).

Pure: the selector and the profile builder, with the switch stood in. The route that carries
the profiles to the selector is exercised by the Ask page tests and the install check.

Task ids: M40.7.5
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from brain import api_routes
from brain.gate.context import Channel
from brain.gate.select import (
    MIN_SHARED_WORDS,
    AgentBinding,
    SelectionStage,
    purpose_match,
    select_agent,
)

DESK = "Renewals desk Answers questions about domain renewal dates and hosting expiry"
BOOKS = "Invoice desk Answers questions about overdue invoices and payment reminders"
PROFILES = {"renewals": DESK, "invoicing": BOOKS}
VISIBLE = frozenset({"renewals", "invoicing"})


def choose(question: str, **kwargs: object) -> object:
    return select_agent(
        question,
        Channel.CONSOLE,
        visible_agents=kwargs.pop("visible", VISIBLE),  # type: ignore[arg-type]
        default_agent="brain",
        profiles=kwargs.pop("profiles", PROFILES),  # type: ignore[arg-type]
        **kwargs,  # type: ignore[arg-type]
    )


def test_a_question_sharing_two_words_with_one_agent_goes_to_that_agent() -> None:
    """The positive case for everything below. Delete this and a matcher that matched nothing
    would pass every refusal here."""
    chosen = choose("When is the domain renewal and the hosting expiry due?")
    assert (chosen.agent_id, chosen.stage) == ("renewals", SelectionStage.CLASSIFIER)  # type: ignore[attr-defined]


def test_one_shared_word_is_not_enough() -> None:
    """A single word is how a question mentioning invoices once lands on the wrong desk. Delete
    this and the floor can drop to one."""
    assert MIN_SHARED_WORDS == 2
    chosen = choose("Please find the overdue thing")
    assert chosen.agent_id == "brain"  # type: ignore[attr-defined]


def test_two_agents_that_fit_equally_leave_the_question_with_the_default() -> None:
    """A tie is nobody deciding, so no agent is picked by its id. Delete this and one agent wins
    every question two fit, for no reason anybody can see."""
    both = {
        "renewals": "Desk domain renewal hosting",
        "invoicing": "Desk domain renewal hosting",
    }
    assert choose("domain renewal hosting", profiles=both).agent_id == "brain"  # type: ignore[attr-defined]


def test_an_agent_the_person_may_not_call_is_never_chosen_however_well_it_fits() -> None:
    """Only visible agents are read. Delete this and a question could be routed to an agent the
    person has no right to, and the routing would tell them it exists."""
    chosen = choose("domain renewal hosting expiry", visible=frozenset({"invoicing"}))
    assert chosen.agent_id == "brain"  # type: ignore[attr-defined]
    assert (
        purpose_match("domain renewal hosting expiry", PROFILES, frozenset({"invoicing"})) is None
    )


def test_a_named_agent_and_a_binding_both_outrank_the_match() -> None:
    """The person's own choice and a configured binding decide before anything is guessed. Delete
    this and the guess could overrule both."""
    named = choose("domain renewal hosting expiry", addressed="invoicing")
    assert (named.agent_id, named.stage) == ("invoicing", SelectionStage.ADDRESSED)  # type: ignore[attr-defined]
    bound = choose(
        "domain renewal hosting expiry",
        bindings=(AgentBinding(channel=Channel.CONSOLE, agent_id="invoicing"),),
    )
    assert (bound.agent_id, bound.stage) == ("invoicing", SelectionStage.BINDING)  # type: ignore[attr-defined]


def test_with_no_profiles_selection_is_what_it_was() -> None:
    """The matcher costs nothing when it is switched off. Delete this and a switch that is off can
    still change who answers."""
    assert choose("domain renewal hosting expiry", profiles={}).agent_id == "brain"  # type: ignore[attr-defined]


def test_the_reason_names_the_agent_and_a_count_of_words_and_not_the_words() -> None:
    """The trace says which agent and how many words, never the words, which are the question's.
    Delete this and the reason could repeat what was asked into a log."""
    reason = choose("domain renewal hosting expiry").reason  # type: ignore[attr-defined]
    assert "renewals" in reason and "domain" not in reason


@pytest.fixture
def switch(monkeypatch: pytest.MonkeyPatch) -> dict[str, bool]:
    held = {"on": True}

    async def is_on(state: object) -> bool:
        return held["on"]

    monkeypatch.setattr(api_routes, "task_routing_is_on", is_on)
    return held


def _records() -> dict[str, SimpleNamespace]:
    return {
        "renewals": SimpleNamespace(
            agent_id="renewals", display_name="Renewals desk", persona="Domain renewals"
        ),
    }


def test_profiles_are_each_agents_name_and_instruction_when_the_switch_is_on(
    switch: dict[str, bool],
) -> None:
    """The words an agent is matched on are its own name and instruction. Delete this and the
    matcher could read some other field of the agent."""
    roster = SimpleNamespace(records=_records())
    found = asyncio.run(api_routes.task_profiles(object(), roster, named=False))  # type: ignore[arg-type]
    assert found == {"renewals": "Renewals desk Domain renewals"}


def test_no_profiles_are_built_when_an_agent_is_named_or_the_switch_is_off(
    switch: dict[str, bool],
) -> None:
    """A named agent is the person's decision, and an off switch changes nothing. Delete this and
    either reads the roster, and the common question pays for it."""
    roster = SimpleNamespace(records=_records())
    assert asyncio.run(api_routes.task_profiles(object(), roster, named=True)) == {}  # type: ignore[arg-type]
    switch["on"] = False
    assert asyncio.run(api_routes.task_profiles(object(), roster, named=False)) == {}  # type: ignore[arg-type]
    switch["on"] = True
    empty = SimpleNamespace(records={})
    assert asyncio.run(api_routes.task_profiles(object(), empty, named=False)) == {}  # type: ignore[arg-type]


def test_only_words_long_enough_to_say_something_are_matched() -> None:
    """Two short words in common (an id, a tax) are not what an agent is for. Delete this and the
    floor on a word's length can drop to nothing, and every small word is a match."""
    profiles = {"forms": "Tax id forms and such"}
    assert purpose_match("what is my tax id", profiles, frozenset({"forms"})) is None


def test_words_every_description_and_question_shares_are_not_a_match() -> None:
    """The common words are left out. Delete this and four words anybody writes make an agent the
    answer to every question."""
    profiles = {"desk": "What will your help give them"}
    assert purpose_match("what will your help", profiles, frozenset({"desk"})) is None
    assert (
        purpose_match("what will your help", {"desk": "invoices payments"}, frozenset({"desk"}))
        is None
    )


def test_a_code_in_both_the_question_and_the_description_counts_as_one_word() -> None:
    """A product or ticket code is a word with digits in it. Delete this and a question about
    SKU4471 cannot find the agent that was told about SKU4471."""
    profiles = {"stock": "Stock desk for SKU4471 and its reorders"}
    assert purpose_match("Where is SKU4471 and its reorders", profiles, frozenset({"stock"})) == (
        "stock",
        2,
    )
