"""How an agent's rungs move after it is installed, and what each move needs.

`brain.console.reach_view` decided the rules a month ago and nothing applied them: a rung is
lowered at once, raised only on evidence (`PromotionEvidence`, `may_raise`) with a second approver
across a money or irreversible boundary, and tripped to the bottom by a breaker naming the metric
(`breaker_trips`, `DEMOTED_TO`); `brain.agents.supervision` decided that a supervised agent is held
at the bottom until a review finds it eligible. The install's leash is sealed in its effective
document and only an upgrade moves it, so every one of those rules had nothing to move. This module
is the fold that turns stored moves into the leash a run is governed by, and the three decisions a
person's press becomes: a lowering, a proposal, a raise. It reuses every rule rather than restating
one, and nothing here opens a connection.

**A move replaces its own entry and no other.** A move names an agent, a target and a scope, which
is exactly a `brain.gate.leash.LeashEntry`'s key, and the newest move for a key is that entry's
rung. Entries for other keys are untouched, so `THE_STRICTEST_OF_OVERLAPPING_RULES_WINS` still
holds across them: raising one scope's entry cannot loosen a stricter entry that overlaps it. See
`A_MOVE_REPLACES_ITS_OWN_ENTRY_AND_NEVER_A_NEIGHBOUR`. Rejected: appending a move as another entry,
which is how a lowering would work and how a raise never could, because the strictest entry wins.

**The evidence is counted, never typed.** A raise's clean runs and agreement are counted from the
actions the agent took on that target since the key last moved and the verdicts people gave them,
so a rung cannot rise on a figure somebody chose. Clean runs are the unbroken run of accepted
verdicts back from the newest, which is what `MINIMUM_CLEAN_RUNS` says it counts. See
`A_PROMOTION_IS_EARNED_ON_THE_KEY_SINCE_IT_LAST_MOVED`.

**Across a money or irreversible boundary a rise is two presses by two people.** The first is a
proposal that moves nothing; the second, by somebody else, is the raise, and names both.
`PromotionEvidence` refuses one person twice and the table refuses it again.

**The breaker watches what people said since the rung was last set.** A person's verdict on an
action is recorded and, when the target's rung is above the bottom and the share accepted
unchanged falls below `MINIMUM_AGREEMENT_RATE`, the rung falls to `DEMOTED_TO` with the metric,
its figure and the threshold. The breaker is asked every time a verdict is recorded, so it needs no
schedule to run on.

**A supervised agent is held down until its latest review found it eligible.** The stored outcome
decides, not a review recomputed on every read: an agent whose review has come due and nobody has
pressed stays held, which is the direction `brain.agents.supervision` says a fail-safe errs in.
Rising out of supervision is then an ordinary raise, on the same evidence and with the same second
person across a boundary, which is how that module says supervision ends: a person decides.

**A moved rung and a takeover demotion are both shown, and the lower one binds.** The autonomy
breaker in `brain.gate.abstain` steps a target down while people keep taking the agent's work over
there, computed from the takeover instants rather than stored. It steps down from whatever rung
the moves left, so it composes with them rather than competing, and the history shows both. See
`A_MOVED_RUNG_AND_A_TAKEOVER_DEMOTION_BOTH_SHOW_AND_THE_LOWER_ONE_BINDS`; rejected: storing the
demotion as a move, which would need a writer on the takeover path and would outlive the week.

Task ids: M39.3.2.1, M39.3.2.2, M39.3.2.3, M39.3.2.4, M39.3.2.5, M39.8.2
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from brain.agents.supervision import (
    HELD_AT_WHILE_SUPERVISED,
    VERDICTS_THAT_SHOW_UNDERSTANDING,
    ShadowReview,
)
from brain.console.reach_view import (
    DEMOTED_TO,
    IRREVERSIBLE,
    MINIMUM_AGREEMENT_RATE,
    CircuitBreak,
    PromotionEvidence,
    Watch,
    breaker_trips,
    may_raise,
)
from brain.core.envelope import SideEffect
from brain.core.scope import Scope
from brain.gate.abstain import TAKEOVER_DEMOTION_THRESHOLD, TAKEOVER_WINDOW, AutonomyBreaker
from brain.gate.injection import AutonomyTier
from brain.gate.leash import MISSING_ENTRY_RUNG, ActionRecord, Leash, LeashEntry
from brain.tables.leash import MoveKind, PinOutcome

# ------------------------------------------------------------------ written-down reasons
#: Why a move replaces the entry it names and nothing else.
A_MOVE_REPLACES_ITS_OWN_ENTRY_AND_NEVER_A_NEIGHBOUR: Final = (
    "A move names an agent, a target and a scope, which is one leash entry's key, and the newest "
    "move for that key is that entry's rung. Every other entry keeps its own rung, so the "
    "strictest of overlapping entries still wins: raising one scope cannot loosen a stricter "
    "entry that overlaps it."
)

#: Why a promotion's evidence is counted from the key's own history.
A_PROMOTION_IS_EARNED_ON_THE_KEY_SINCE_IT_LAST_MOVED: Final = (
    "A rise is judged on what the agent did on that target since the rung was last set, as the "
    "people who reviewed it judged it: the unbroken run of actions accepted unchanged, and the "
    "share accepted unchanged. Counted from the stored actions and verdicts, never typed, so a "
    "rung cannot rise on a figure somebody chose."
)

# ------------------------------------------------------------ what a refusal says
LOWERING_MUST_LOWER: Final = "That setting is not lower than the one it has now."
RAISING_MUST_RAISE: Final = "That setting is not higher than the one it has now."
THE_EVIDENCE_DOES_NOT_MEET_THE_BAR: Final = (
    "Its record on this action does not yet meet the bar for more autonomy: ten actions in a row "
    "accepted unchanged, and nine in ten accepted unchanged overall."
)
A_SECOND_PERSON_MUST_CONFIRM: Final = (
    "This action touches money or cannot be undone, so a second person has to confirm the rise. "
    "It is proposed and waits for them."
)
THE_PROPOSER_CANNOT_CONFIRM: Final = (
    "The rise has to be confirmed by somebody other than the person who proposed it."
)
RAISING_WAITS_FOR_THE_REVIEW: Final = (
    "It is under supervision and its review has not found it ready, so no setting can rise yet."
)

#: The metric a tripped breaker names.
BREAKER_METRIC: Final = "share of its actions a person accepted unchanged"

#: Why a moved rung and a rung people's takeovers lowered are both shown, and which binds.
A_MOVED_RUNG_AND_A_TAKEOVER_DEMOTION_BOTH_SHOW_AND_THE_LOWER_ONE_BINDS: Final = (
    "Two things lower an agent's rung on a target and neither replaces the other. A person moves "
    "it on the agent's page, which is a stored row, and the autonomy breaker steps it down while "
    "people have taken the agent's work over there three times inside a week, which is computed "
    "from the takeover instants at the moment of asking. The breaker steps down from whatever rung "
    "the moves left, so a run is held to the lower of the two, which is the strictest-wins rule "
    "every other overlap on a leash keeps: a raise made while the breaker is open is kept, and "
    "binds once the takeovers have aged out of the week. Both are shown in the history, the move "
    "as its row and the demotion as a row of its own saying when the takeovers still inside the "
    "week first held the rung down and how many there are, because a history of moves alone tells "
    "whoever sets the leash that a raise took effect while the breaker is still holding it down."
)

#: The kind a takeover demotion is shown under in the history, beside `MoveKind`'s four.
TAKEN_OVER: Final = "taken_over"


class LeashMoveError(Exception):
    """A move that cannot be made. Its text is one of the sentences above, and names nothing."""


# ------------------------------------------------------------------------- the moves
@dataclass(frozen=True)
class LeashMove:
    """One stored move of one rung, with its evidence (M39.3.2.5).

    Each kind carries exactly its own evidence, refused otherwise, so a history cannot read as a
    rise on a breaker's metric or a fall on somebody's approval.
    """

    agent_id: str
    target: str
    scope: Scope
    was: AutonomyTier
    became: AutonomyTier
    kind: MoveKind
    at: datetime
    changed_by: str
    irreversible: bool = False
    promotion: PromotionEvidence | None = None
    trip: CircuitBreak | None = None

    def __post_init__(self) -> None:
        rises = self.kind in (MoveKind.PROPOSED, MoveKind.RAISED)
        if rises != (self.became > self.was) or self.became == self.was:
            msg = f"a {self.kind.value} move from {self.was.name} to {self.became.name} is not one"
            raise LeashMoveError(msg)
        if rises != (self.promotion is not None):
            msg = "a rise carries promotion evidence and a fall carries none"
            raise LeashMoveError(msg)
        if (self.kind is MoveKind.TRIPPED) != (self.trip is not None):
            msg = "a tripped move names its metric and no other move does"
            raise LeashMoveError(msg)
        if (
            self.kind is MoveKind.RAISED
            and self.irreversible
            and (self.promotion is None or not self.promotion.second_approver_id)
        ):
            msg = "a rise across an irreversible boundary names a second approver"
            raise LeashMoveError(msg)
        if self.at.tzinfo is None:
            msg = "a naive move time compares wrongly against an aware one"
            raise LeashMoveError(msg)

    @property
    def key(self) -> tuple[str, str, Scope]:
        return (self.agent_id, self.target, self.scope)

    @property
    def moves_the_rung(self) -> bool:
        """Whether the leash is different after this row. A proposal is a question, not a move."""
        return self.kind is not MoveKind.PROPOSED


def history(moves: Iterable[LeashMove]) -> tuple[LeashMove, ...]:
    """Every move, proposals included, oldest first, ties broken by target (M39.3.2.5).

    Oldest first for `brain.console.reach_view.rung_history`'s reason: a fall is read against the
    rise before it.
    """
    return tuple(sorted(moves, key=lambda one: (one.at, one.target, one.kind.value)))


def newest_by_key(moves: Iterable[LeashMove]) -> dict[tuple[str, str, Scope], LeashMove]:
    """The newest move per key, proposals included."""
    found: dict[tuple[str, str, Scope], LeashMove] = {}
    for one in history(moves):
        found[one.key] = one
    return found


def effective_leash(leash: Leash, moves: Sequence[LeashMove]) -> Leash:
    """The install's leash with every key's newest real move applied (M39.3.2.1).

    See `A_MOVE_REPLACES_ITS_OWN_ENTRY_AND_NEVER_A_NEIGHBOUR`. A key a move names and the install
    does not is added as an entry of its own. Built through the constructor so every entry is
    validated again, which is `brain.agents.install.pinned_leash`'s argument.
    """
    moved = newest_by_key(one for one in moves if one.moves_the_rung)
    entries: list[LeashEntry] = []
    seen: set[tuple[str, str, Scope]] = set()
    for entry in leash.entries:
        key = (entry.agent_id, entry.target, entry.scope)
        move = moved.get(key)
        seen.add(key)
        entries.append(
            entry
            if move is None
            else LeashEntry(
                agent_id=entry.agent_id, target=entry.target, scope=entry.scope, rung=move.became
            )
        )
    for key, move in sorted(moved.items(), key=lambda item: (item[0][1], item[1].at)):
        if key not in seen:
            entries.append(
                LeashEntry(agent_id=key[0], target=key[1], scope=key[2], rung=move.became)
            )
    return Leash(entries=tuple(entries))


def rung_of(leash: Leash, agent_id: str, target: str, scope: Scope) -> AutonomyTier:
    """The rung of the one entry with this key, or the missing entry's rung."""
    for entry in leash.entries:
        if entry.agent_id == agent_id and entry.target == target and entry.scope == scope:
            return entry.rung
    return MISSING_ENTRY_RUNG


def held_while_supervised(leash: Leash, agent_id: str, outcome: PinOutcome | None) -> Leash:
    """The leash with this agent's rungs held at the bottom while its supervision holds it.

    Held unless there is no pin or the newest review found it eligible. A `min`, as
    `brain.agents.supervision.supervised_leash` is, so the strongest thing it can do is leave a
    rung where a person put it.
    """
    if outcome is None or outcome is PinOutcome.ELIGIBLE:
        return leash
    return Leash(
        entries=tuple(
            LeashEntry(
                agent_id=entry.agent_id,
                target=entry.target,
                scope=entry.scope,
                rung=(
                    min(entry.rung, HELD_AT_WHILE_SUPERVISED)
                    if entry.agent_id == agent_id
                    else entry.rung
                ),
            )
            for entry in leash.entries
        )
    )


# ---------------------------------------------------------------------- the evidence
@dataclass(frozen=True)
class Record:
    """What the agent did on one target since the key last moved, as its reviewers judged it."""

    clean_runs: int
    agreement_rate: float
    reviewed: int


def record_since(
    agent_id: str,
    target: str,
    *,
    actions: Sequence[ActionRecord],
    verdicts: Sequence[ShadowReview],
    since: datetime | None,
) -> Record:
    """Counted from the stored actions and verdicts (M39.3.2.2). See the reason above.

    An action is counted once whatever routes it was stored under, at its earliest, and only when
    somebody gave it a verdict.
    """
    earliest: dict[str, datetime] = {}
    for one in actions:
        if one.agent_id != agent_id or one.target != target:
            continue
        if since is not None and one.at < since:
            continue
        seen = earliest.get(one.action_digest)
        if seen is None or one.at < seen:
            earliest[one.action_digest] = one.at
    judged = sorted(
        (
            (earliest[one.action_digest], one.verdict in VERDICTS_THAT_SHOW_UNDERSTANDING)
            for one in verdicts
            if one.agent_id == agent_id and one.action_digest in earliest
        ),
        key=lambda pair: pair[0],
    )
    understood = sum(1 for _, good in judged if good)
    clean = 0
    for _, good in reversed(judged):
        if not good:
            break
        clean += 1
    rate = understood / len(judged) if judged else 0.0
    return Record(clean_runs=clean, agreement_rate=rate, reviewed=len(judged))


def breaker_for(rung: AutonomyTier, record: Record, *, at: datetime) -> CircuitBreak | None:
    """Whether what people said since the rung was set trips it to the bottom (M39.3.2.3)."""
    if rung <= DEMOTED_TO or record.reviewed == 0:
        return None
    return breaker_trips(
        watch=Watch.FALLS_BELOW,
        metric=BREAKER_METRIC,
        measured=record.agreement_rate,
        threshold=MINIMUM_AGREEMENT_RATE,
        at=at,
    )


# ---------------------------------------------------------------------- the decisions
def lowering(
    leash: Leash,
    *,
    agent_id: str,
    target: str,
    scope: Scope,
    to: AutonomyTier,
    by: str,
    at: datetime,
) -> LeashMove:
    """A rung lowered at once, with no evidence asked for (the fail-safe direction)."""
    was = rung_of(leash, agent_id, target, scope)
    if to >= was:
        raise LeashMoveError(LOWERING_MUST_LOWER)
    return LeashMove(
        agent_id=agent_id,
        target=target,
        scope=scope,
        was=was,
        became=to,
        kind=MoveKind.LOWERED,
        at=at,
        changed_by=by,
    )


def raising(
    leash: Leash,
    *,
    agent_id: str,
    target: str,
    scope: Scope,
    to: AutonomyTier,
    by: str,
    at: datetime,
    effect: SideEffect,
    record: Record,
    pending: LeashMove | None,
    supervision: PinOutcome | None,
) -> LeashMove:
    """A press to raise a rung: a proposal, a raise, or a refusal (M39.3.2.2, M39.3.2.4).

    `pending` is the newest move for this key when it is a proposal to the same rung. Across an
    irreversible boundary with no proposal pending, the press is the proposal; with one pending,
    it is the second approval, refused when it is the proposer's own. Everywhere else the press is
    the raise. `may_raise` decides each time, so the bar and the second signature are its rules.
    """
    if supervision is not None and supervision is not PinOutcome.ELIGIBLE:
        raise LeashMoveError(RAISING_WAITS_FOR_THE_REVIEW)
    was = rung_of(leash, agent_id, target, scope)
    if to <= was:
        raise LeashMoveError(RAISING_MUST_RAISE)
    irreversible = effect in IRREVERSIBLE
    confirming = (
        irreversible
        and pending is not None
        and pending.kind is MoveKind.PROPOSED
        and pending.became == to
        and pending.was == was
    )
    if confirming and pending is not None and pending.changed_by == by:
        raise LeashMoveError(THE_PROPOSER_CANNOT_CONFIRM)
    approver = pending.changed_by if confirming and pending is not None else by
    second = by if confirming else ""
    evidence = PromotionEvidence(
        clean_runs=record.clean_runs,
        agreement_rate=record.agreement_rate,
        approver_id=approver,
        second_approver_id=second,
    )
    if not evidence.meets_the_bar():
        raise LeashMoveError(THE_EVIDENCE_DOES_NOT_MEET_THE_BAR)
    if irreversible and not confirming:
        return LeashMove(
            agent_id=agent_id,
            target=target,
            scope=scope,
            was=was,
            became=to,
            kind=MoveKind.PROPOSED,
            at=at,
            changed_by=by,
            irreversible=True,
            promotion=evidence,
        )
    if not may_raise(was=was, proposed=to, evidence=evidence, effect=effect):
        raise LeashMoveError(A_SECOND_PERSON_MUST_CONFIRM)
    return LeashMove(
        agent_id=agent_id,
        target=target,
        scope=scope,
        was=was,
        became=to,
        kind=MoveKind.RAISED,
        at=at,
        changed_by=by,
        irreversible=irreversible,
        promotion=evidence,
    )


def tripping(
    leash: Leash, *, agent_id: str, target: str, scope: Scope, trip: CircuitBreak, by: str
) -> LeashMove:
    """The move a tripped breaker writes: to `DEMOTED_TO`, naming the metric."""
    return LeashMove(
        agent_id=agent_id,
        target=target,
        scope=scope,
        was=rung_of(leash, agent_id, target, scope),
        became=DEMOTED_TO,
        kind=MoveKind.TRIPPED,
        at=trip.at,
        changed_by=by,
        trip=trip,
    )


# ------------------------------------------------------------------ the takeover breaker
@dataclass(frozen=True)
class TakeoverDemotion:
    """The autonomy breaker holding one target lower than the moves left it (M8.3.5).

    `at` is the earliest instant the takeovers still inside the week show the breaker open, and
    `takeovers` how many of them there are. Instants and a count, and never who took the work over
    or what it was, by `brain.gate.takeover_store.A_TAKEOVER_INSTANT_SAYS_WHEN_AND_NAMES_NOTHING`.
    """

    target: str
    was: AutonomyTier
    became: AutonomyTier
    at: datetime
    takeovers: int


def held_by_takeovers(
    rung: AutonomyTier, standing: AutonomyBreaker | None, now: datetime
) -> AutonomyTier | None:
    """The rung the breaker holds `rung` to at `now`, or None when it holds it no lower.

    `AutonomyBreaker.rung` decides, which is the one the gate asks
    (`brain.gate.leash.effective_tier`), so the page and a run cannot disagree about it. See
    `A_MOVED_RUNG_AND_A_TAKEOVER_DEMOTION_BOTH_SHOW_AND_THE_LOWER_ONE_BINDS`.
    """
    if standing is None:
        return None
    held = standing.rung(rung, now)
    return held if held < rung else None


def takeover_demotions(
    leash: Leash, agent_id: str, standings: Mapping[str, AutonomyBreaker], now: datetime
) -> tuple[TakeoverDemotion, ...]:
    """Every target of this agent the breaker holds lower than its highest rung, by target.

    From the highest rung of the target's entries, as `brain.console.agent_profile.taken_over`
    describes a row. A standing filed under another target is refused rather than drawn, for that
    function's reason: a demotion shown on the wrong action tells somebody to fix a leash that is
    fine.
    """
    highest: dict[str, AutonomyTier] = {}
    for entry in leash.entries:
        if entry.agent_id == agent_id:
            highest[entry.target] = max(entry.rung, highest.get(entry.target, entry.rung))
    found: list[TakeoverDemotion] = []
    for target, rung in sorted(highest.items()):
        standing = standings.get(target)
        if standing is not None and standing.target != target:
            msg = f"a standing for {standing.target!r} was filed under {target!r}"
            raise ValueError(msg)
        held = held_by_takeovers(rung, standing, now)
        if standing is None or held is None:
            continue
        inside = sorted(one for one in standing.takeovers if one > now - TAKEOVER_WINDOW)
        found.append(
            TakeoverDemotion(
                target=target,
                was=rung,
                became=held,
                at=inside[TAKEOVER_DEMOTION_THRESHOLD - 1],
                takeovers=len(inside),
            )
        )
    return tuple(found)
