"""A shadow pin that is reviewed rather than one that expires, and the measure that reviews it.

`brain.agents.catalogue` declares SHADOW on every target of every template and says, in
`A_PIN_WITH_NO_END_IS_NOT_A_PIN_FOR_THIRTY_DAYS`, that the one template it could not write is
the chaser the work breakdown describes as shadow-pinned for thirty days. Nothing in the leash
carries a time bound, so the two ways to write it were a permanent pin wearing the name of a
temporary one, or an expiry. This module is the third thing, and it is the owner's decision
rather than a design chosen here: the agent stays supervised, the question is asked at thirty
days, a measurement answers it, and **below the threshold the period extends instead of the
pin lapsing**. Only at or above the threshold does a promotion become possible.

**A pin never expires on a timer, and the guarantee is structural rather than careful.**
`ShadowPin` has no expiry field, no `until`, no `ends_at`, and `ShadowOutcome` has no member
meaning supervision ended. A date on this record is a date a review is *due*, and reaching it
produces one of two answers: extended, or eligible. There is no third, and there is nowhere
for a fourth to be stored. See `A_PIN_THAT_EXPIRES_IS_SUPERVISION_ENDING_BECAUSE_A_TIMER_RAN_OUT`.

**Where the number comes from, which is the question that decides whether any of this is
worth anything.** A confidence computed from nothing is a figure somebody chose, and a figure
somebody chose is exactly what the decision was written against. So both halves of the
fraction are read off records the system already produces:

- The denominator is `brain.gate.leash.ActionRecord`, filtered to this agent, to
  `Route.SIMULATE`, and to this pin's own window. That record is written by `govern` for every
  call it routes, it carries an `action_digest`, and it is the only evidence that the agent
  did anything at all.
- The numerator is `brain.audit.record.ApprovalVerdict`, which is a closed vocabulary of what
  a person did with an action an agent proposed, and it already distinguishes the four things
  that have to be distinguished: approved unchanged, amended, taken over, rejected. Only the
  first is understanding. See `THE_VERDICT_VOCABULARY_IS_THE_LEDGERS_AND_NOT_A_FIFTH_ONE`.

**And the honest part: nothing in this repository writes the pairing today.** `route_for`
sends SHADOW to `Route.SIMULATE`, and `govern` raises a `SuspendedAction` only on
`Route.SUSPEND`, so a shadow-pinned agent produces action records and no verdicts at all. A
verdict on a simulated action needs a person looking at the shadow record and saying what they
would have done, and there is no console control, no route and no table for that. What is
built here is the decision half, which is the half that can be argued and mutated before a
surface exists, and the absence is a refusal rather than a default: an agent with no reviews
is `UNMEASURED`, which extends the pin. See
`AN_UNMEASURED_AGENT_IS_NOT_AT_ZERO_AND_NOT_AT_ONE_HUNDRED`.

**Ninety percent of what.** Of the actions somebody actually reviewed, counted once each, in
this pin's window, and never fewer than `MINIMUM_REVIEWED_ACTIONS` of them. A share over three
runs is not a confidence, and the floor is not a taste: it is the smallest denominator at which
an agent can be wrong once and still clear the bar. Nine of ten is nine tenths; eight of nine
is not. See `A_CONFIDENCE_OVER_THREE_RUNS_IS_NOT_A_CONFIDENCE`.

**Does it go down. Yes, and there is no state in which it cannot.** Nothing here stores a
share, a high-water mark or a "qualified" flag. `measure` recomputes over the whole window
every time it is asked, so an agent that cleared the bar in March and spent April being amended
is below the bar in April, and the review that finds it there extends the pin. After a
promotion this module is no longer the thing watching: a fall is
`brain.console.reach_view.breaker_trips`, which demotes to `DEMOTED_TO`, the bottom rung, and
an agent that lands back there is pinned again with a new `pinned_at`. That new window is what
stops the history that preceded the failure carrying the agent straight back out of it. See
`A_REVIEW_FROM_BEFORE_THIS_PIN_IS_NOT_EVIDENCE_ABOUT_IT`.

**Who ends supervision, and the safe answer is not the convenient one.** Not this module. A
confidence at or above the threshold makes a promotion *possible* and performs none: raising a
rung is `Change.LEASH_INCREASE`, which `brain.memory.tiers` puts at `Tier.GATED`, and
`brain.console.reach_view.may_raise` requires a named approver and a second, distinct one for
an irreversible effect. Chasing money is `SideEffect.MONEY`, which is in that set, so the agent
this whole item is about needs two people. `supervised_leash` is written as a `min` against the
bottom rung, exactly as `brain.agents.install.pinned_leash` is, so the strongest thing an
eligible verdict can do is stop holding a rung down. It cannot raise one, and an agent whose
leash still says SHADOW, which is what every template in the catalogue says, goes on simulating
until a person edits it. See `NOTHING_HERE_ENDS_SUPERVISION_AND_ELIGIBLE_IS_NOT_PROMOTED`.

Six designs were rejected.

*An `expires_at` on the pin, with a console warning when it passes.* This is reading two of the
item, and the warning is what makes it sound safe. A field that names the day supervision ends
is read by the next person as the day supervision ends, whatever a banner beside it says, and
the failure arrives as an agent acting unwatched on a date nobody diarised.

*Defaulting an unmeasured agent to zero.* It reads as the fail-closed choice and it is a number
just as invented as a hundred. Zero says the agent was measured and was wrong every time, which
is a claim about an agent nobody watched, and it puts a figure on a screen that a reviewer can
argue with. Unmeasured is a different fact and it is the true one.

*A stored confidence, recomputed nightly.* One more thing that can be stale exactly when it
matters, and a promotion decided on Tuesday's figure after Monday's incident.

*Counting every simulated action as the denominator, with unreviewed ones counted as not
understood.* It closes the cherry-picking hole below and opens a worse one: an agent's
confidence would fall because nobody looked at it, so supervision would be extended for the
reviewer's absence and the agent could never earn its way out of a busy month. The reviewed set
is the denominator because nobody can judge what nobody looked at. The cost is real and is
stated where it is paid: `Confidence.simulated` carries how many actions there were to choose
from, so a screen can show ten reviewed of four hundred rather than hiding the ratio. Nothing
here can tell a representative sample from a flattering one, and it does not pretend to. See
`A_REVIEWED_SAMPLE_IS_NOT_A_RANDOM_SAMPLE_AND_NOTHING_HERE_CAN_MAKE_IT_ONE`.

*A verdict vocabulary of this module's own, with "understood" and "not understood".* Two
vocabularies for one act, and the second one loses the distinction the first paid for: taking
the work over is not rejecting it, and an estate where half the reviews are take-overs is
configured wrongly in a way that is invisible once both collapse to "not understood".

*Resolving two conflicting verdicts on one action by taking the later one.* It is the obvious
rule and it hands whoever reviews last the power to move the share. Two people disagreeing
about one action is a contradiction in the record, and picking a winner is this module deciding
which of them was right. It refuses instead.

Scope: nothing here opens a connection, reads a clock or writes anything. `now` is a parameter
throughout, for the reason `brain.agents.lifecycle` gives about a rule on dates that reads the
clock itself being untestable at its own boundary.

What this implements is `docs/needs-rupash.md` item 33, which is a decision rather than a work
breakdown leaf, so it claims none. The leaf it unblocks is the chaser template the catalogue
still does not carry, and that template is deliberately not written here: this makes the pin
expressible, and writing the twenty-third template is that leaf's own work, with its own
persona, ceiling and golden set to argue about.

Task ids: none
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

from brain.audit.record import ApprovalVerdict
from brain.gate.injection import AutonomyTier
from brain.gate.leash import DIGEST, IDENTIFIER, ActionRecord, Leash, LeashEntry, Route

# ------------------------------------------------------------------ written-down reasons

#: Why the record has no expiry field and the outcome has no member meaning supervision ended.
A_PIN_THAT_EXPIRES_IS_SUPERVISION_ENDING_BECAUSE_A_TIMER_RAN_OUT: Final = (
    "A pin with an expiry is an agent that starts acting unwatched on the day after the "
    "expiry, because a timer ran out and not because anybody decided. Thirty days is when "
    "the question is asked and never when the answer is assumed, so reaching the review date "
    "produces one of two answers, extended or eligible, and neither of them is supervision "
    "ending. The guarantee is that there is no field to store an expiry in and no outcome to "
    "spell one with, rather than a rule somebody keeps: a date named for the day supervision "
    "ends is read as the day supervision ends, whatever is written beside it."
)

#: Why an agent nobody has reviewed is neither trusted nor distrusted.
AN_UNMEASURED_AGENT_IS_NOT_AT_ZERO_AND_NOT_AT_ONE_HUNDRED: Final = (
    "An agent with no reviewed actions has no confidence, and both of the obvious defaults "
    "are a number somebody chose. A hundred promotes an agent nobody watched. Zero looks "
    "fail-closed and is a claim that the agent was measured and was wrong every time, which "
    "puts a figure on a screen that a reviewer can argue with and a threshold can be moved "
    "against. Unmeasured is the third state, it is the true one, and it extends the pin."
)

#: Why the denominator has a floor and what the floor is derived from.
A_CONFIDENCE_OVER_THREE_RUNS_IS_NOT_A_CONFIDENCE: Final = (
    "A share is only a confidence if the denominator is large enough for one mistake to "
    "matter. Three of three is a hundred percent and says nothing at all. The floor here is "
    "not a taste: it is the smallest number of reviewed actions at which an agent can be "
    "wrong once and still clear the threshold, which at nine tenths is ten, because nine of "
    "ten is nine tenths and eight of nine is not. A floor derived from the threshold moves "
    "with it if the threshold ever moves, and the property is asserted rather than the number."
)

#: Why the window starts at the pin and not at the agent's first ever run.
A_REVIEW_FROM_BEFORE_THIS_PIN_IS_NOT_EVIDENCE_ABOUT_IT: Final = (
    "An agent that was promoted, went wrong and was demoted to the bottom rung is pinned "
    "again, and the reviews that carried it out the first time are still in the record. "
    "Counting them would let the history that preceded a failure carry the agent straight "
    "back past the review that failure caused, which is the one review that has to be "
    "answered on new evidence. So a pin has its own window and evidence older than it is not "
    "evidence about it."
)

#: Why an eligible verdict changes nothing on its own.
NOTHING_HERE_ENDS_SUPERVISION_AND_ELIGIBLE_IS_NOT_PROMOTED: Final = (
    "Confidence at or above the threshold makes a promotion possible and performs none. A "
    "rung rise is a gated change that brain.console.reach_view.may_raise decides, on evidence "
    "a named person looked at, with a second distinct approver where the effect is "
    "irreversible, and chasing money is irreversible. So the strongest thing an eligible "
    "verdict does here is stop holding a rung down: supervised_leash is a min against the "
    "bottom rung and cannot raise one, and an agent whose own leash still says SHADOW, which "
    "is what every catalogue template says, goes on simulating until a person edits it."
)

#: Why the verdicts are the audit ledger's own four and not a pair invented here.
THE_VERDICT_VOCABULARY_IS_THE_LEDGERS_AND_NOT_A_FIFTH_ONE: Final = (
    "brain.audit.record.ApprovalVerdict is closed and already argues why taking the work over "
    "is not a rejection with a nicer name: an estate where half the reviews are take-overs is "
    "an estate whose agents are configured wrongly, and that is invisible if both land as one "
    "value. A second vocabulary here would lose that distinction on the surface that decides "
    "whether supervision continues, which is the surface that most needs it. Only APPROVED "
    "counts as understanding, and it is written out rather than derived from the others, so a "
    "fifth member of the enum has to be dispositioned by somebody rather than defaulted."
)

#: What the measurement cannot see, stated where it is paid for.
A_REVIEWED_SAMPLE_IS_NOT_A_RANDOM_SAMPLE_AND_NOTHING_HERE_CAN_MAKE_IT_ONE: Final = (
    "The denominator is the actions somebody reviewed, because nobody can judge what nobody "
    "looked at. That leaves a reviewer free to look at the ten easy ones, and no rule in this "
    "module can tell a representative sample from a flattering one. What it does instead of "
    "pretending is carry the number of simulated actions beside the number reviewed, so ten "
    "of four hundred is visible on any screen that shows the share, rather than being a "
    "ratio nobody was shown."
)

#: Why a review dated before the action is refused rather than counted.
A_REVIEW_DATED_BEFORE_ITS_ACTION_IS_NOT_A_RECORD_OF_ANYBODY_LOOKING: Final = (
    "A verdict recorded before the action it judges is not a person looking at what the agent "
    "did; it is a row assembled by something, and counting it would put evidence in the "
    "numerator that nobody produced. Refused rather than dropped, because a dropped row moves "
    "the denominator silently and the same defect then reads as an agent with fewer runs."
)

# --------------------------------------------------------------------------- the figures

#: The share of reviewed actions a person accepted unchanged, at or above which a promotion
#: becomes possible.
#:
#: **Ninety percent is the owner's figure, decided on 2026-09-09 against item 33.** His words:
#: below ninety percent confidence the shadow period extends so the agent can raise it, and
#: only at ninety or above does supervision end. It is written here as a share rather than as
#: a percentage so it can be compared with a fraction without anybody dividing by a hundred at
#: the point of use.
#:
#: It is the same bar `brain.console.reach_view.MINIMUM_AGREEMENT_RATE` already puts on a rung
#: rise, and that is deliberate: the two would otherwise be two different ninety percents,
#: one deciding whether a promotion may be proposed and one deciding whether it may be
#: approved, and the day they drifted the console would show an agent that qualified for a
#: review it cannot pass. It is not imported from there, because a console module is above
#: this one and the import would put the agent package under the surface that renders it. The
#: test asserts the two against each other, which is what catches a drift.
#:
#: The comparison is `>=` on a float share. For any denominator this system could reach, the
#: nearest double to `u / r` is on the same side of the nearest double to nine tenths as the
#: exact fraction is, because `9 * r - 10 * u` is a non-zero integer whenever the share is not
#: exactly nine tenths, and the rounding error is far below one part in a million.
SHADOW_EXIT_CONFIDENCE: Final = 0.9

#: How long a shadow period runs before the question is asked, and how much longer it runs
#: each time the answer is short.
#:
#: Thirty days is the owner's figure, from the work breakdown's own wording for the chaser.
#: One constant serves both the first review and every extension, because two would be a
#: second number nobody decided: he said the period extends so the agent can raise its
#: confidence, and the period is this.
SHADOW_REVIEW_PERIOD: Final = timedelta(days=30)

#: The smallest number of reviewed actions that can be a confidence at all.
#:
#: Derived rather than chosen, and the derivation is the property a test asserts: it is the
#: smallest denominator at which an agent can be wrong once and still reach
#: `SHADOW_EXIT_CONFIDENCE`. Nine of ten clears nine tenths and eight of nine does not, so at
#: nine a single mistake is disqualifying and the figure stops measuring an agent and starts
#: measuring its luck. It agrees with `brain.console.reach_view.MINIMUM_CLEAN_RUNS`, which was
#: chosen separately and for a different reason, and the test pins the two together so that
#: moving either one is a decision somebody makes rather than a drift.
MINIMUM_REVIEWED_ACTIONS: Final = 10

#: The verdicts that count as the agent having understood.
#:
#: One member, written out. Amended means a person had to change it, taken over means a person
#: did it instead, and rejected means it should not have happened; none of the three is an
#: agent that understood, and collapsing them is what
#: `THE_VERDICT_VOCABULARY_IS_THE_LEDGERS_AND_NOT_A_FIFTH_ONE` refuses. Written out rather
#: than expressed as the complement of the other three, so that a fifth verdict added to the
#: ledger's vocabulary is outside this set until somebody decides otherwise, and the test that
#: names the other three goes red rather than silently admitting it.
VERDICTS_THAT_SHOW_UNDERSTANDING: Final[frozenset[ApprovalVerdict]] = frozenset(
    {ApprovalVerdict.APPROVED}
)

#: The rung a supervised agent is held at, which is the bottom one.
#:
#: `brain.agents.install.PIN_WHEN_UNBOUND` holds the same value for a different reason, and
#: the two are separate constants because they are separate decisions: one lifts when a
#: connector comes back, this one when a person raises a rung. Asserted against
#: `min(AutonomyTier)` rather than against a literal zero, so a rung added below SHADOW moves
#: this with it.
HELD_AT_WHILE_SUPERVISED: Final = AutonomyTier.SHADOW


class SupervisionError(Exception):
    """Evidence that cannot be believed, or a pin that cannot mean what it says.

    Its own type rather than `brain.agents.model.AgentError`, which is a refusal to write or
    move an agent record. These refusals are about a measurement: a console showing a
    confidence panel has a reason to catch one of these and no reason to catch the other, and
    one exception type for both would make that impossible to write.
    """


# ---------------------------------------------------------------------- what was observed


class ShadowReview(BaseModel):
    """One person's verdict on one action an agent simulated.

    The digest is `brain.gate.leash.ActionRecord.action_digest`, so a review names the exact
    action rather than a run or a day: two reviews of one agent's morning are two opinions
    about an unknown number of things, and no fraction can be made of them.

    Frozen. A verdict that can be edited after a confidence was computed from it is a
    confidence nobody can reproduce.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str = Field(pattern=IDENTIFIER)
    #: The simulated action this verdict is about.
    action_digest: str = Field(pattern=DIGEST)
    verdict: ApprovalVerdict
    #: Who looked. Kept because a share with no reviewers behind it is a number again, and
    #: because a screen showing the figure has to be able to say who produced it.
    reviewer_id: str = Field(pattern=IDENTIFIER)
    at: datetime

    @field_validator("at")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        """A naive review time compares wrongly against a pin's window boundary.

        The comparison decides whether this counts at all, so an hour's drift is the
        difference between evidence and no evidence, in whichever direction the host sits.
        """
        if v.tzinfo is None:
            msg = "a review time must be timezone-aware; a naive one is a silent bug"
            raise ValueError(msg)
        return v

    @property
    def shows_understanding(self) -> bool:
        """Whether this verdict counts towards the numerator."""
        return self.verdict in VERDICTS_THAT_SHOW_UNDERSTANDING


# ------------------------------------------------------------------------------- the pin


class ShadowPin(BaseModel):
    """One agent's current supervision period: when it started and when it is next reviewed.

    **Two dates and neither is an expiry.** `pinned_at` is where the evidence window opens and
    it never moves, so an extension does not throw away what the agent has already earned.
    `review_due_at` is when somebody is asked the question, and it moves forward every time the
    answer is short. There is no third date, and
    `A_PIN_THAT_EXPIRES_IS_SUPERVISION_ENDING_BECAUSE_A_TIMER_RAN_OUT` is why there is nowhere
    for one to go.

    Per agent rather than per target. The decision is about whether an agent is trusted to work
    unwatched, which is a question about the agent; the leash goes on being per target, and
    `supervised_leash` holds every one of this agent's targets down without flattening them
    into a single rung.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str = Field(pattern=IDENTIFIER)
    #: The start of the evidence window. Never moves; a later pin is a new record.
    pinned_at: datetime
    #: When the review is next due. Moves forward on an extension and on nothing else.
    review_due_at: datetime

    @field_validator("pinned_at", "review_due_at")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            msg = "a pin timestamp must be timezone-aware; a naive one is a silent bug"
            raise ValueError(msg)
        return v

    def model_post_init(self, _context: object, /) -> None:
        """Refuse a review that is due before the period it reviews began.

        A pin whose review date is at or before its start is one that is due the moment it is
        written, so the first `review` call answers on an empty window and extends, which
        looks like the system working and has silently thrown the thirty days away.
        """
        if self.review_due_at <= self.pinned_at:
            msg = (
                f"{self.agent_id!r} is pinned at {self.pinned_at.isoformat()} with a review "
                f"due at {self.review_due_at.isoformat()}, which is not after it; a review "
                "due before the period it reviews began asks the question of an empty window"
            )
            raise ValueError(msg)

    def is_due(self, now: datetime) -> bool:
        """Whether the question may be asked yet.

        Inclusive at the boundary, because the due date is the day the review happens rather
        than the day after it, and a strict comparison would make a review scheduled for
        exactly the instant it is run report as not due.
        """
        return now >= self.review_due_at


def pin(agent_id: str, *, now: datetime) -> ShadowPin:
    """Start a supervision period, with its first review one period out.

    Called when an agent is installed, and again whenever one falls back to the bottom rung:
    a new pin is a new `pinned_at`, which is what starts the evidence window over. See
    `A_REVIEW_FROM_BEFORE_THIS_PIN_IS_NOT_EVIDENCE_ABOUT_IT`.
    """
    return ShadowPin(
        agent_id=agent_id,
        pinned_at=now,
        review_due_at=now + SHADOW_REVIEW_PERIOD,
    )


def extended(current: ShadowPin, *, now: datetime) -> ShadowPin:
    """The same period, running another `SHADOW_REVIEW_PERIOD` from this review.

    From `now` rather than from the old due date, and the difference matters when a review
    happens late. Measured from the old date, a review run forty days after it was due would
    produce a pin that is already due again, so the next call would review the same evidence
    and extend again, and an agent could be carried through a whole series of reviews in an
    afternoon by whoever was clearing a backlog. Measured from the review, a late review
    delays the next one, which keeps the agent supervised for longer and is the direction a
    fail-safe has to err in.

    `pinned_at` is carried through unchanged, so an extension adds time and takes away no
    evidence.
    """
    return ShadowPin(
        agent_id=current.agent_id,
        pinned_at=current.pinned_at,
        review_due_at=now + SHADOW_REVIEW_PERIOD,
    )


# ------------------------------------------------------------------------ the measurement


@dataclass(frozen=True)
class Confidence:
    """How much of what the agent did, somebody accepted unchanged.

    Three counts and no share stored. `share` is computed on every read, so there is no field
    holding a figure that was true once. `simulated` is carried beside `reviewed` for
    `A_REVIEWED_SAMPLE_IS_NOT_A_RANDOM_SAMPLE_AND_NOTHING_HERE_CAN_MAKE_IT_ONE`.
    """

    #: Reviewed actions whose verdict is in `VERDICTS_THAT_SHOW_UNDERSTANDING`.
    understood: int
    #: Distinct simulated actions somebody gave a verdict on. The denominator.
    reviewed: int
    #: Distinct actions the agent simulated in this window, reviewed or not.
    simulated: int

    def __post_init__(self) -> None:
        if self.understood < 0 or self.reviewed < 0 or self.simulated < 0:
            msg = "a negative count of actions is not a measurement of anything"
            raise SupervisionError(msg)
        if self.understood > self.reviewed:
            msg = (
                f"{self.understood} understood of {self.reviewed} reviewed is a share above "
                "one, so the numerator counts something the denominator does not"
            )
            raise SupervisionError(msg)
        if self.reviewed > self.simulated:
            msg = (
                f"{self.reviewed} reviewed of {self.simulated} simulated means verdicts were "
                "counted against actions the agent never took, and the denominator is then "
                "whatever somebody filed"
            )
            raise SupervisionError(msg)

    @property
    def is_measured(self) -> bool:
        """Whether there is enough here to be a confidence at all."""
        return self.reviewed >= MINIMUM_REVIEWED_ACTIONS

    @property
    def share(self) -> float:
        """The fraction understood, and a refusal when there is no fraction.

        Raising rather than returning zero or one is
        `AN_UNMEASURED_AGENT_IS_NOT_AT_ZERO_AND_NOT_AT_ONE_HUNDRED` made unavoidable: a
        property that answered would be read by a caller who never asked `is_measured`, and
        whichever number it answered with would be the one on the screen.
        """
        if self.reviewed == 0:
            msg = (
                "no action has been reviewed, so there is no share to report. "
                f"{AN_UNMEASURED_AGENT_IS_NOT_AT_ZERO_AND_NOT_AT_ONE_HUNDRED}"
            )
            raise SupervisionError(msg)
        return self.understood / self.reviewed

    def meets_the_bar(self) -> bool:
        """Whether this clears the threshold over a denominator large enough to mean it.

        Both halves, and the order matters only for the reader: an unmeasured agent has no
        share, so asking for one first would raise where the answer is simply no.
        """
        return self.is_measured and self.share >= SHADOW_EXIT_CONFIDENCE


def _simulated_in_window(
    records: Iterable[ActionRecord], *, current: ShadowPin
) -> dict[str, datetime]:
    """Every distinct action this agent simulated in this window, and when.

    Keyed by digest, so an agent that retried one action ten times has simulated one action.
    Without that, the population and every share drawn from it would move with how often a
    loop happened to run.

    Filtered on `Route.SIMULATE` rather than on the tier, because the route is what actually
    happened to the call: a tier says what was decided and the route says what was done, and
    an executed action is not evidence about a shadow period whatever rung it was decided at.
    """
    earliest: dict[str, datetime] = {}
    for record in records:
        if record.agent_id != current.agent_id:
            continue
        if record.route is not Route.SIMULATE:
            continue
        if record.at < current.pinned_at:
            continue
        seen = earliest.get(record.action_digest)
        if seen is None or record.at < seen:
            earliest[record.action_digest] = record.at
    return earliest


def _verdict_per_action(
    reviews: Iterable[ShadowReview], *, current: ShadowPin, simulated: dict[str, datetime]
) -> dict[str, ApprovalVerdict]:
    """One verdict per action, refusing the two ways a fraction stops meaning anything.

    Reviews for another agent, and reviews from before this window, are dropped rather than
    refused: a caller handing over everything the ledger holds is the normal case, and
    refusing it would push callers into filtering the evidence themselves, which is the one
    step that must not be theirs.

    Two refusals, and both are about the denominator rather than about tidiness. A review
    naming an action this agent never simulated in this window would add to the denominator
    something nobody watched happen. A second, different verdict on one action is two people
    disagreeing, and resolving it here would be this module deciding which of them was right.
    """
    verdicts: dict[str, ApprovalVerdict] = {}
    for review_ in reviews:
        if review_.agent_id != current.agent_id:
            continue
        if review_.at < current.pinned_at:
            continue
        acted_at = simulated.get(review_.action_digest)
        if acted_at is None:
            msg = (
                f"a review by {review_.reviewer_id!r} names an action "
                f"{current.agent_id!r} did not simulate in this period, so counting it would "
                "put an action nobody watched into the denominator"
            )
            raise SupervisionError(msg)
        if review_.at < acted_at:
            msg = (
                f"a review by {review_.reviewer_id!r} is dated before the action it judges. "
                f"{A_REVIEW_DATED_BEFORE_ITS_ACTION_IS_NOT_A_RECORD_OF_ANYBODY_LOOKING}"
            )
            raise SupervisionError(msg)
        already = verdicts.get(review_.action_digest)
        if already is not None and already is not review_.verdict:
            msg = (
                f"one action of {current.agent_id!r} carries both a {already.value} and a "
                f"{review_.verdict.value} verdict; two people disagreeing about one action is "
                "a contradiction in the record, and picking one of them is this module "
                "deciding which reviewer was right"
            )
            raise SupervisionError(msg)
        verdicts[review_.action_digest] = review_.verdict
    return verdicts


def measure(
    current: ShadowPin,
    *,
    simulated: Sequence[ActionRecord],
    reviews: Sequence[ShadowReview],
) -> Confidence:
    """Count the window, from records the gate and the ledger already produce.

    Takes the records rather than a `Confidence`, so there is no parameter through which a
    figure somebody else worked out could arrive. That is the same argument
    `brain.console.reach_view.readable` makes about refusing a `Recollection`: a signature
    that accepts a verdict is a signature that can be handed the wrong one, and the caller
    who reaches it wrongly is the surface, every time.

    Nothing is stored and nothing is cached. Call it twice with more amendments in between and
    it answers lower the second time, which is what
    `A_REVIEW_FROM_BEFORE_THIS_PIN_IS_NOT_EVIDENCE_ABOUT_IT` and the whole shape of this
    module rest on.
    """
    population = _simulated_in_window(simulated, current=current)
    verdicts = _verdict_per_action(reviews, current=current, simulated=population)
    return Confidence(
        understood=sum(
            1 for verdict in verdicts.values() if verdict in VERDICTS_THAT_SHOW_UNDERSTANDING
        ),
        reviewed=len(verdicts),
        simulated=len(population),
    )


# ---------------------------------------------------------------------------- the review


class ShadowOutcome(enum.StrEnum):
    """What a review found. Three members, and none of them is supervision ending.

    There is deliberately no `PROMOTED`, no `RELEASED` and no `SUPERVISION_ENDED`. The widest
    thing a review can say is that a promotion has become possible, which is `ELIGIBLE`, and
    the act itself belongs to a person through `brain.console.reach_view.may_raise`. A member
    meaning the pin was lifted would be the timer expiry arriving under a different name, one
    assignment away from being written by whatever loop calls this. See
    `NOTHING_HERE_ENDS_SUPERVISION_AND_ELIGIBLE_IS_NOT_PROMOTED`.
    """

    #: The period has not run yet. Nothing is decided, however good the figure looks.
    NOT_YET_DUE = "not_yet_due"
    #: The question was asked and the answer was short, or there was no answer. More time.
    EXTENDED = "extended"
    #: The question was asked and answered. A person may now propose a rung rise.
    ELIGIBLE = "eligible"


@dataclass(frozen=True)
class ShadowDecision:
    """One review: what was found, on what evidence, and the pin as it now stands.

    Carries the confidence whatever the outcome, including before the review is due, because a
    screen showing an agent's progress needs the figure on every day of the period and not
    only on the day it decides something. What the figure cannot do on those days is decide:
    `outcome` is `NOT_YET_DUE` and there is no branch that reads the share before the date.
    """

    outcome: ShadowOutcome
    confidence: Confidence
    #: The pin after this review. The same object when nothing moved, a later review date when
    #: the period was extended, and never one with a lifted supervision state, because there
    #: is no such state to put in it.
    pin: ShadowPin
    asked_at: datetime

    @property
    def stays_supervised(self) -> bool:
        """Whether the agent is still simulating after this review.

        True for everything but `ELIGIBLE`, and true for `ELIGIBLE` too in practice until a
        person raises a rung: this reports what the review decided, and `supervised_leash`
        reports what the leash now says.
        """
        return self.outcome is not ShadowOutcome.ELIGIBLE


def review(
    current: ShadowPin,
    *,
    simulated: Sequence[ActionRecord],
    reviews: Sequence[ShadowReview],
    now: datetime,
) -> ShadowDecision:
    """Ask the thirty-day question, and answer it from the evidence rather than from the date.

    Three outcomes and the date decides only the first of them.

    **Before the review is due, nothing is decided.** An agent at a hundred percent on day
    three is not eligible on day three: the period is the owner's, and a share that could end
    it early would make thirty days a suggestion. The confidence is computed anyway and
    carried, because that is what a progress screen shows.

    **Due, and unmeasured or short, extends the period.** This is the whole item. The date
    passing is not an event that ends supervision; it is an event that asks a question, and an
    agent nobody reviewed has not answered it. See
    `A_PIN_THAT_EXPIRES_IS_SUPERVISION_ENDING_BECAUSE_A_TIMER_RAN_OUT` and
    `AN_UNMEASURED_AGENT_IS_NOT_AT_ZERO_AND_NOT_AT_ONE_HUNDRED`.

    **Due, measured, and at or above the threshold makes a promotion possible.** It does not
    perform one and this function returns no rung. See
    `NOTHING_HERE_ENDS_SUPERVISION_AND_ELIGIBLE_IS_NOT_PROMOTED`.
    """
    confidence = measure(current, simulated=simulated, reviews=reviews)
    if not current.is_due(now):
        return ShadowDecision(
            outcome=ShadowOutcome.NOT_YET_DUE,
            confidence=confidence,
            pin=current,
            asked_at=now,
        )
    if not confidence.meets_the_bar():
        return ShadowDecision(
            outcome=ShadowOutcome.EXTENDED,
            confidence=confidence,
            pin=extended(current, now=now),
            asked_at=now,
        )
    return ShadowDecision(
        outcome=ShadowOutcome.ELIGIBLE,
        confidence=confidence,
        pin=current,
        asked_at=now,
    )


def supervised_leash(leash: Leash, decision: ShadowDecision) -> Leash:
    """Hold this agent's every rung at the bottom while its review has not been answered.

    Written as a `min` against `HELD_AT_WHILE_SUPERVISED`, exactly as
    `brain.agents.install.pinned_leash` is written against `PIN_WHEN_UNBOUND`, and for a
    reason that is stronger here: an assignment would be one edit away from being able to
    raise a rung, and the whole content of the owner's decision is that nothing automatic ever
    raises one. A `min` can only narrow, so the strongest outcome available to this function
    is to leave the leash exactly as a person configured it.

    Only this agent's entries are touched. Another agent's rung has nothing to do with this
    agent's review, and holding the whole table down would make one unanswered review stop an
    estate, which is the kind of blast radius that gets a control switched off.

    Entries are rebuilt through the constructor rather than copied with an update, because
    `model_copy` skips validation and the path that rewrites a rung must not be the path that
    can store an invalid one. That is `pinned_leash`'s argument, reused rather than restated.
    """
    if decision.outcome is ShadowOutcome.ELIGIBLE:
        return leash
    return Leash(
        entries=tuple(
            LeashEntry(
                agent_id=entry.agent_id,
                target=entry.target,
                scope=entry.scope,
                rung=(
                    min(entry.rung, HELD_AT_WHILE_SUPERVISED)
                    if entry.agent_id == decision.pin.agent_id
                    else entry.rung
                ),
            )
            for entry in leash.entries
        )
    )
