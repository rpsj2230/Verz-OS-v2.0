"""A tier row's numbers are what the classifier compares against, and nothing else about it.

Task ids: M5.2.2
"""

from __future__ import annotations

import pytest

from brain.core.lane import Lane
from brain.models.routing import (
    ESCALATION_HEADROOM,
    TIER_CONTEXT_WINDOW,
    RoutingRequest,
    Tier,
    classify_tier,
)
from brain.models.tier_rules import (
    HEADROOM_KEY,
    MIN_HEADROOM,
    RULE_KEYS,
    TierRule,
    TierRuleError,
    rule_of,
    table_of,
)


def test_a_row_with_no_headroom_takes_its_window_and_the_compiled_headroom() -> None:
    """The positive case. Delete this and a row setting only a window could be refused or read
    with a headroom nobody wrote."""
    rule = rule_of("main", 50_000, {})

    assert rule == TierRule(tier=Tier.MAIN, context_window=50_000)
    table = table_of([rule])
    assert table.windows[Tier.MAIN] == 50_000
    assert table.headroom[Tier.MAIN] == ESCALATION_HEADROOM
    assert table.configured == frozenset({Tier.MAIN})


def test_a_tier_with_no_row_runs_at_the_compiled_numbers_and_is_not_marked_configured() -> None:
    """Delete this and the screen could draw a product default as a setting somebody made, or an
    empty table could route every tier against a window of zero."""
    table = table_of([])

    assert dict(table.windows) == dict(TIER_CONTEXT_WINDOW)
    assert set(table.headroom.values()) == {ESCALATION_HEADROOM}
    assert table.configured == frozenset()


@pytest.mark.parametrize(
    ("rules", "said"),
    [
        ({"predicate": "question mentions payroll"}, "does not read"),
        ({HEADROOM_KEY: "0.5"}, "must be a number"),
        ({HEADROOM_KEY: True}, "must be a number"),
        ({HEADROOM_KEY: float("nan")}, "finite"),
        ({HEADROOM_KEY: MIN_HEADROOM / 2}, "outside"),
        ({HEADROOM_KEY: 1.5}, "outside"),
    ],
)
def test_a_rule_set_holding_anything_but_a_valid_headroom_is_refused_whole(
    rules: dict[str, object], said: str
) -> None:
    """`A_TIER_ROW_CHANGES_THE_NUMBERS_AND_NEVER_THE_LOGIC`. Delete this and a key the router
    never reads is a rule somebody believes is in force, or a headroom above the window routes a
    prompt no rung can hold."""
    with pytest.raises(TierRuleError, match=said):
        rule_of("main", 50_000, rules)


def test_the_rule_set_names_only_the_headroom() -> None:
    """Asserted against the key's own name rather than the constant compared with itself.

    Delete this and a second key could be admitted by widening the set with no test noticing."""
    assert frozenset({"escalation_headroom"}) == RULE_KEYS


@pytest.mark.parametrize("window", [0, -1, 10_000_001])
def test_a_window_outside_one_token_to_ten_million_is_refused(window: int) -> None:
    """Delete this and a zero window escalates every request, or a stray digit admits a prompt no
    rung can hold."""
    with pytest.raises(TierRuleError, match="outside"):
        TierRule(tier=Tier.SMALL, context_window=window)


def test_tier_none_takes_no_row_and_an_unknown_tier_is_refused() -> None:
    """Delete this and a row could widen the fast lane's window, which is zero because it uses no
    model, or a typo could govern nothing while reading as saved."""
    with pytest.raises(TierRuleError, match="no model"):
        rule_of("none", 1_000, {})
    with pytest.raises(TierRuleError, match="not a tier"):
        rule_of("mian", 1_000, {})


def test_two_rows_for_one_tier_are_refused_rather_than_the_last_winning() -> None:
    """Delete this and the tier's numbers would depend on which row a read returned first."""
    with pytest.raises(TierRuleError, match="two rows"):
        table_of([TierRule(Tier.MAIN, 1_000), TierRule(Tier.MAIN, 2_000)])


def test_a_narrower_window_from_the_table_escalates_a_request_the_compiled_one_keeps() -> None:
    """**The leaf.** A request of 60,000 tokens stays on main at the compiled 200,000 window and
    goes to heavy when the table says main holds 50,000; a table headroom does the same at the
    compiled window.

    Delete this and the classifier could ignore the numbers it is handed, which is the state the
    live path was in before the table was read."""
    asked = RoutingRequest(lane=Lane.ANSWER, estimated_context_tokens=60_000)
    narrow = table_of([TierRule(Tier.MAIN, 50_000)])
    tight = table_of([TierRule(Tier.MAIN, 200_000, headroom=0.25)])

    assert classify_tier(asked).tier is Tier.MAIN
    assert classify_tier(asked, windows=narrow.windows, headroom=narrow.headroom).tier is Tier.HEAVY
    assert classify_tier(asked, windows=tight.windows, headroom=tight.headroom).tier is Tier.HEAVY
