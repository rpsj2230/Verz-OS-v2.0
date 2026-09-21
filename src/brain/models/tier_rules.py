"""What `ops.routing_tier` tells the router, read on every call rather than compiled in.

`brain.models.routing.classify_tier` has always taken its windows as a parameter, and nothing on
the live path passed one: the answer lane classified against `TIER_CONTEXT_WINDOW`, and
`ops.routing_tier` had no reader under `src` at all (`brain.ops.starter_store` said so). So a tier's
window and its escalation fraction were constants a company could only change by a release, which
is the failure `RoutingChain`'s own docstring names: a change that needs an engineer stops
happening. This module turns the rows into the two mappings `classify_tier` takes, and the executor
(`brain.models.calls.ModelCalls.complete`) reads them in the same read as the ladder, so the tier a
request lands in is decided by what the table says at that moment.

**The rule set holds numbers and never a program.** `RoutingTierRow`'s docstring is exact about
this and it is kept: the classifier reads five scalars and makes no model call, and what it
consults from a row is the window and the headroom. `RULE_KEYS` is closed, and a row carrying any
other key is refused as a whole rather than half applied, because a key the router does not know is
a rule somebody believes is in force. See `A_TIER_ROW_CHANGES_THE_NUMBERS_AND_NEVER_THE_LOGIC`.

**A tier with no row, or a row the router cannot read, runs at the compiled numbers, and says so.**
`TierTable.configured` names the tiers a row governs, so the Models screen draws a tier running at
the product's default as that and not as a setting somebody made. Refusing to route because a row
was unreadable was rejected: every question would fail over a typing mistake in one number, and the
compiled figures are the ones the product shipped and tested.

**`Tier.NONE` takes no row's numbers.** Its window is zero by definition, because the fast lane uses
no model, and a row that widened it would describe a lane that does not exist.

Scope: pure. The rows are a parameter.

Task ids: M5.2.2
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

from brain.models.routing import ESCALATION_HEADROOM, TIER_CONTEXT_WINDOW, TIER_LADDER, Tier

#: Why a row may change a number and nothing else.
A_TIER_ROW_CHANGES_THE_NUMBERS_AND_NEVER_THE_LOGIC: Final = (
    "The classifier is a pure function of five scalars so the same request always lands in the "
    "same tier and nothing a document says can move it. A tier row supplies the numbers that "
    "function compares against, the window and the escalation fraction, and a key the router "
    "does not know is refused with the whole row, because a rule somebody wrote and nothing reads "
    "is a rule they believe is in force."
)

#: The one key a tier's rule set may carry: the fraction of the window past which a request
#: escalates to the next tier up. `ESCALATION_HEADROOM` is the compiled figure.
HEADROOM_KEY: Final = "escalation_headroom"

#: Every key `rules` may hold. Closed; see the reason constant.
RULE_KEYS: Final[frozenset[str]] = frozenset({HEADROOM_KEY})

#: The lowest headroom a row may set. Below a tenth of the window a tier would escalate almost
#: every request, which is a row mistyped rather than a policy anybody holds.
MIN_HEADROOM: Final = 0.1

#: The widest window a row may declare, in tokens. Far above any model shipped today, and a bound
#: so a stray digit cannot make a tier accept a prompt no rung can hold.
MAX_CONTEXT_WINDOW: Final = 10_000_000


class TierRuleError(ValueError):
    """Raised for a tier row the router must not act on."""


@dataclass(frozen=True)
class TierRule:
    """One tier's row, checked: its window, and its headroom when the row sets one."""

    tier: Tier
    context_window: int
    headroom: float | None = None

    def __post_init__(self) -> None:
        if self.tier is Tier.NONE:
            msg = "tier none uses no model, so no row sets its window or headroom"
            raise TierRuleError(msg)
        if isinstance(self.context_window, bool) or not isinstance(self.context_window, int):
            msg = f"{self.tier}'s window must be a whole number of tokens"
            raise TierRuleError(msg)
        if not 0 < self.context_window <= MAX_CONTEXT_WINDOW:
            msg = (
                f"{self.tier}'s window of {self.context_window} tokens is outside 1 to "
                f"{MAX_CONTEXT_WINDOW}"
            )
            raise TierRuleError(msg)
        if self.headroom is not None and not MIN_HEADROOM <= self.headroom <= 1.0:
            msg = f"{self.tier}'s headroom of {self.headroom} is outside {MIN_HEADROOM} to 1"
            raise TierRuleError(msg)

    def rules(self) -> dict[str, object]:
        """The rule set as the row stores it: only the keys this rule sets."""
        return {} if self.headroom is None else {HEADROOM_KEY: self.headroom}


def rule_of(tier: str, context_window: int, rules: Mapping[str, object]) -> TierRule:
    """One stored row as a rule, or a `TierRuleError` saying why the router will not use it."""
    try:
        named = Tier(tier)
    except ValueError as exc:
        msg = f"{tier!r} is not a tier"
        raise TierRuleError(msg) from exc
    unknown = sorted(set(rules) - RULE_KEYS)
    if unknown:
        msg = f"{named}'s rules carry {unknown}, which the router does not read"
        raise TierRuleError(msg)
    headroom = rules.get(HEADROOM_KEY)
    if headroom is None:
        return TierRule(tier=named, context_window=context_window)
    if isinstance(headroom, bool) or not isinstance(headroom, int | float):
        msg = f"{named}'s {HEADROOM_KEY} must be a number"
        raise TierRuleError(msg)
    if not math.isfinite(float(headroom)):
        msg = f"{named}'s {HEADROOM_KEY} must be a finite number"
        raise TierRuleError(msg)
    return TierRule(tier=named, context_window=context_window, headroom=float(headroom))


@dataclass(frozen=True)
class TierTable:
    """The windows and headroom the classifier is handed, and which tiers a row governs."""

    windows: Mapping[Tier, int] = field(default_factory=lambda: TIER_CONTEXT_WINDOW)
    headroom: Mapping[Tier, float] = field(
        default_factory=lambda: MappingProxyType(dict.fromkeys(TIER_LADDER, ESCALATION_HEADROOM))
    )
    configured: frozenset[Tier] = frozenset()


def table_of(rules: Iterable[TierRule]) -> TierTable:
    """The compiled numbers, with every row's numbers laid over its own tier.

    Two rules for one tier are refused: the table's partial unique index already makes that
    impossible among live rows, and a caller handing two would otherwise get whichever came last.
    """
    windows = dict(TIER_CONTEXT_WINDOW)
    headroom = dict.fromkeys(TIER_LADDER, ESCALATION_HEADROOM)
    seen: set[Tier] = set()
    for one in rules:
        if one.tier in seen:
            msg = f"two rows govern tier {one.tier}"
            raise TierRuleError(msg)
        seen.add(one.tier)
        windows[one.tier] = one.context_window
        if one.headroom is not None:
            headroom[one.tier] = one.headroom
    return TierTable(
        windows=MappingProxyType(windows),
        headroom=MappingProxyType(headroom),
        configured=frozenset(seen),
    )
