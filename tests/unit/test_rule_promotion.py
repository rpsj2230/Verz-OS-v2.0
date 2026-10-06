"""A learned fast-lane rule promoted by people once conversations agree (M39.4.2.3): the rules,
without a database.

The database's half, the policies, the checks and the copy into the live rules, is
`brain.ops.acceptance_checks_promotion`, which `tests/unit/test_acceptance_promotion.py` runs on
PostgreSQL and breaks.

Task ids: M39.4.2.3
"""

from __future__ import annotations

import ast
import asyncio
import inspect
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.field_policy import Classification
from brain.core.scope import Scope
from brain.gate.fast_lane import FastPathRule
from brain.knowledge.columns import OPEN_SENSITIVITY, RESTRICTED_SENSITIVITY
from brain.memory.promotion import (
    A_RULE_THAT_ANSWERS_WITH_MONEY_NEEDS_TWO_PEOPLE,
    A_SHADOW_OCCURRENCE_NEVER_SLOWS_OR_FAILS_AN_ANSWER,
    ALREADY_PROMOTED,
    NOBODY_PROMOTES_WHAT_THEY_PROPOSED,
    NOT_READY,
    PROPOSED_IT,
    SAME_PERSON,
    LearnedRule,
    PromotionRefusedError,
    PromotionState,
    needs_two,
    press,
)

#: Pinned far from any wall clock: nothing here is about the present.
AT = datetime(2999, 6, 1, 9, 0, tzinfo=UTC)

RULE = FastPathRule(
    rule_id="sales__rate_of",
    template="what is the rate for {name}",
    slot="name",
    source="tables",
    entity="price_list",
    match_field="name",
    answer_field="sell_price",
)


def held(**changed: Any) -> LearnedRule:
    values: dict[str, Any] = {
        "memory_id": "lr_one",
        "rule": RULE,
        "department": "sales",
        "proposed_by": "u_proposer",
    }
    return LearnedRule(**(values | changed))


# ------------------------------------------------------------------------------ two people
def test_a_rule_over_a_price_lists_cost_takes_two_people_and_its_sell_price_one() -> None:
    """**`A_RULE_THAT_ANSWERS_WITH_MONEY_NEEDS_TWO_PEOPLE`, on the price list's own levels.** A
    column the tables mark restricted or derived (a price list's cost) is classified as
    `RESTRICTED_SENSITIVITY` and takes two people; an open column (its sell price) takes one; an
    entity whose connector declares money takes two whatever its column.

    Delete this and a rule saying the cost of every service to a whole department can be put into
    effect by one person."""
    assert needs_two(carries_money=False, answering=RESTRICTED_SENSITIVITY)
    assert not needs_two(carries_money=False, answering=OPEN_SENSITIVITY)
    assert needs_two(carries_money=True, answering=OPEN_SENSITIVITY)
    assert needs_two(carries_money=False, answering=Classification.RESTRICTED)
    assert not needs_two(carries_money=False, answering=None)
    assert "price list's cost" in A_RULE_THAT_ANSWERS_WITH_MONEY_NEEDS_TWO_PEOPLE


# ------------------------------------------------------------------------------ the press
def test_one_person_promotes_a_ready_rule_that_needs_one_and_names_themselves_twice() -> None:
    """The positive case: a ready rule needing one person is promoted by the first press, which
    names the presser as both. Delete this and every refusal below passes for a press that never
    promotes anything."""
    pressed = press(held(), by="u_admin", ready=True, two=False)
    assert pressed.state is PromotionState.PROMOTED
    assert (pressed.first_by, pressed.promoted_by, pressed.needs_two) == (
        "u_admin",
        "u_admin",
        False,
    )


def test_a_rule_needing_two_waits_after_one_and_is_promoted_by_a_different_second() -> None:
    """The first press holds it for a second person; the same person pressing again is refused,
    and a different person's press promotes it naming both. Delete this and one person can press
    twice and promote a rule that needs two."""
    first = press(held(), by="u_admin", ready=True, two=True)
    assert first.state is PromotionState.AWAITING_SECOND
    waiting = held(state=PromotionState.AWAITING_SECOND, needs_two=True, first_by="u_admin")
    with pytest.raises(PromotionRefusedError, match=SAME_PERSON):
        press(waiting, by="u_admin", ready=True, two=True)
    second = press(waiting, by="u_second", ready=True, two=True)
    assert second.state is PromotionState.PROMOTED
    assert (second.first_by, second.promoted_by) == ("u_admin", "u_second")


def test_a_rule_is_not_promoted_unready_by_its_proposer_or_twice() -> None:
    """**`NOBODY_PROMOTES_WHAT_THEY_PROPOSED`, and agreement first.** A press before enough
    conversations agree, a press by the proposer at either step, and a press on a promoted rule
    are each refused in their own words.

    Delete this and a rule can be promoted on no agreement, or by the person who proposed it."""
    with pytest.raises(PromotionRefusedError, match=NOT_READY):
        press(held(), by="u_admin", ready=False, two=False)
    with pytest.raises(PromotionRefusedError, match=PROPOSED_IT):
        press(held(), by="u_proposer", ready=True, two=False)
    waiting = held(state=PromotionState.AWAITING_SECOND, needs_two=True, first_by="u_admin")
    with pytest.raises(PromotionRefusedError, match=PROPOSED_IT):
        press(waiting, by="u_proposer", ready=True, two=True)
    with pytest.raises(PromotionRefusedError, match=ALREADY_PROMOTED):
        press(held(state=PromotionState.PROMOTED), by="u_admin", ready=True, two=False)
    assert "somebody else" in NOBODY_PROMOTES_WHAT_THEY_PROPOSED


def test_a_system_proposed_rule_is_promoted_by_anybody_who_may() -> None:
    """A rule with no proposer is not refused for want of one. Delete this and a rule the system
    proposed, which is every rule a learning forms, could never be promoted."""
    assert press(held(proposed_by=None), by="u_admin", ready=True, two=False).state is (
        PromotionState.PROMOTED
    )


# ------------------------------------------------------------------------------ who presses
def reach(*grants: tuple[str, Scope]) -> EntitlementSet:
    return EntitlementSet(
        principal_id="u_reader",
        grants=tuple(
            Grant(capability=Capability(value=capability), scope=scope)
            for capability, scope in grants
        ),
    )


def test_a_department_learning_admin_presses_its_own_rules_and_nobody_elses() -> None:
    """The press is `admin:learning` at the rule's place: a department's grant admits its own
    department's rule and not another's or the install's; a grant over everything admits all.

    Delete this and an administrator of one department can promote another's rule."""
    from brain.promotion_routes import may_promote_where

    sales = reach(("admin:learning", Scope.department("sales")))
    everything = reach(("admin:learning", Scope.unrestricted()))
    assert may_promote_where(sales, "sales", AT)
    assert not may_promote_where(sales, "finance", AT)
    assert not may_promote_where(sales, None, AT)
    assert may_promote_where(everything, None, AT)
    assert not may_promote_where(reach(("read:learning", Scope.unrestricted())), "sales", AT)


# ------------------------------------------------------------------------------ the count
def test_counting_never_raises_and_counts_nothing_without_a_conversation() -> None:
    """**`A_SHADOW_OCCURRENCE_NEVER_SLOWS_OR_FAILS_AN_ANSWER`.** A store that cannot be read is
    nothing counted rather than a raise, and a question with no thread, or a process with no
    database, counts nothing.

    Delete this and an answer can fail because a learning could not be counted."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from brain.memory.promotion_store import StoredLearnedRules, counted_after_answering

    class Broken:
        def __call__(self) -> Any:
            raise RuntimeError("no database")

    broken: Any = Broken()
    counted = asyncio.run(
        StoredLearnedRules(broken).count_occurrence(
            "what is the rate for acme",
            principal_id="u_asker",
            department="sales",
            thread_id="00000000-0000-0000-0000-000000000001",
            now=AT,
        )
    )
    assert counted == ()
    state: Any = type("State", (), {"db_sessions": async_sessionmaker()})()
    assert (
        asyncio.run(
            counted_after_answering(
                state, "q", principal_id="u", department=None, thread_id=None, now=AT
            )
        )
        == ()
    )
    assert "never slower" in A_SHADOW_OCCURRENCE_NEVER_SLOWS_OR_FAILS_AN_ANSWER


def test_the_answer_route_counts_after_its_response_as_a_background_task() -> None:
    """The web answer route hands `counted_after_answering` to the response as its background
    task, read from its source rather than its docstring. Delete this and the count can move in
    front of the answer, where a slow database would slow every question."""
    from brain import api_routes

    tree = ast.parse(inspect.getsource(api_routes.answer))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    tasks = [
        one
        for one in calls
        if ast.unparse(one.func) == "BackgroundTask"
        and one.args
        and ast.unparse(one.args[0]) == "counted_after_answering"
    ]
    assert len(tasks) == 1
    streamed = [one for one in calls if ast.unparse(one.func) == "StreamingResponse"]
    assert any(word.arg == "background" for one in streamed for word in one.keywords)


# ------------------------------------------------------------------------------ the tab
def test_the_memory_tab_offers_promote_and_the_count_only_to_whoever_may_press() -> None:
    """A tier-two row offers Promote and says how many conversations agree to a reader who may
    press it there, and to nobody else; a promoted rule offers nothing.

    Delete this and the tab can show every reader how often another department's questions would
    have used a rule, or offer a press the route refuses."""
    from brain.agent_memory_routes import tier_two_view
    from brain.console.reach_view import TierTwoRow
    from brain.memory.tiers import Change, Occurrence

    row = TierTwoRow(
        memory_id="lr_one",
        change=Change.FAST_PATH_RULE,
        evidence=(),
        promote_ready=True,
        learned_at=AT,
    )
    seen = [Occurrence(conversation_id=f"c{n}", on=AT - timedelta(days=1)) for n in range(3)]
    sales = reach(("admin:learning", Scope.department("sales")))
    finance = reach(("admin:learning", Scope.department("finance")))

    offered = tier_two_view(row, held(), seen, sales, AT)
    assert (offered.promote_offered, offered.agreeing, offered.state) == (True, 3, "held")
    hidden = tier_two_view(row, held(), seen, finance, AT)
    assert (hidden.promote_offered, hidden.agreeing) == (False, None)
    done = tier_two_view(row, held(state=PromotionState.PROMOTED), seen, sales, AT)
    assert (done.promote_offered, done.agreeing, done.state) == (False, None, "promoted")
    assert tier_two_view(row, None, seen, sales, AT).state is None


def test_a_rule_over_an_entity_its_connector_declares_carries_money_is_read_as_money() -> None:
    """`carries_money` reads the connector's own declaration: Laravel's client view and Xero's
    contact carry money, HubSpot's company does not, and an uploaded table declares nothing.

    Delete this and the money half of `needs_two` can read a constant False with every other test
    green, so a rule over contract values is promoted by one person."""
    from brain.promotion_routes import carries_money

    def over(source: str, entity: str) -> LearnedRule:
        return held(rule=RULE.model_copy(update={"source": source, "entity": entity}))

    assert carries_money(over("laravel", "laravel_client"))
    assert carries_money(over("xero", "xero_contact"))
    assert not carries_money(over("hubspot", "hubspot_company"))
    assert not carries_money(over("tables", "price_list"))
