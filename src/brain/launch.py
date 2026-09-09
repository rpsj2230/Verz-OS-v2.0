"""The pack a client is handed at launch, rendered from the registers rather than typed.

Six documents change hands on the day an install goes live: a service level statement, a
subprocessor list, a runbook per console screen, an incident playbook per failure mode, a
named owner for each thing the client now runs, and a booked date to look at all of it
again. Four of those already exist in this repository as registers, and this module renders
them. It declares none of them a second time.

**A handover document that restates a register is a second register**, and the second one is
the one that goes stale, because it is the one nothing imports. That is not a general worry:
the subprocessor list is a schedule to a data processing agreement, so the day a fourth model
provider is added to `brain.ops.provider_keys.PROVIDER_SLOTS`, a signed legal document
becomes false and nothing in the estate notices. Every section here is therefore derived, and
what the pack owns is the completeness claim rather than the content. See
`A_HANDOVER_DOCUMENT_THAT_RESTATES_A_REGISTER_IS_A_SECOND_REGISTER`.

**A service level statement is the one document in the pack that can be refused by
arithmetic, and it is refused four ways.** `brain.ops.reliability.RECOVERY_OBJECTIVES` holds
a recovery point and a recovery time per profile, and its own comment says the figures exist
and the document does not; this is the document. It will not state a recovery point the
backup schedule cannot deliver, it will not state one the copies that actually exist cannot
deliver, it will not state a recovery time no drill has measured, and it will not state one
the last drill took longer than. Each of those is a promise the client signs. See
`A_PROMISE_THE_SCHEDULE_CANNOT_MEET_IS_STILL_A_PROMISE_THE_CLIENT_SIGNS`.

**The second of those four is new on 2026-09-10 and the statement was signable without it.**
Until then the recovery point was checked against `SCHEDULE` alone, which is a declaration of
what ought to be copied and which nothing had ever executed: measured that day,
`worst_scheduled_exposure_seconds()` returned 3600 against `lite`'s promise of 86400, so the
refusal passed comfortably on an estate holding no copies whatsoever. A schedule is an
intention and a copy is a fact, and a document a client signs may only rest on the second.
`brain.ops.backup_manifest` reads real copies back for the first time, which is what makes the
measured answer available at all. See `A_SCHEDULE_IS_AN_INTENTION_AND_A_COPY_IS_A_FACT`.

**The subprocessor list names who may process and not who has.** Deriving it from observed
traffic gives a list that is correct on the day it is written and wrong the first time a
fallback fires, which is the one case nobody is watching. So it is derived from the providers
this install holds a key for: a provider with no key cannot receive anything and is not a
subprocessor, and a key for a provider that is not a declared slot is a finding rather than a
row, because it is a credential nobody argued about. See
`A_SUBPROCESSOR_LIST_NAMES_WHO_MAY_PROCESS_AND_NOT_WHO_HAS`.

**A pack with a missing section is not a shorter pack.** `assemble` raises with every finding
at once rather than returning what it could build, because a pack that renders five of six
sections is handed over, and the missing one is discovered by the person who needed it during
the incident it was written for. `pack_gaps` is the same answer without the exception, for a
console screen that wants to show what is outstanding before launch day.

What was rejected. A `Pack` that carries rendered markdown was the obvious shape and is
wrong: the pack would then be a string, and a test could only assert on substrings of it,
which is the failure `CLAUDE.md` records twice about tests satisfied by their own docstrings.
The sections are objects, and rendering is somebody else's problem.

Nothing here reaches anything, in the same split as `brain.ops.handover` and for the same
reason: the interesting case is the register that has a gap, and a module holding a session
could not be made to fail that way in a test.

Task ids: M30.5.4, M37.4.2.2, M37.4.2.4, M37.4.3.1, M37.4.3.2, M37.4.3.3, M37.4.3.5
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final

from brain.console.screens import SCREENS, Screen
from brain.ops.provider_keys import PROVIDER_SLOTS, ProviderSlot
from brain.ops.recovery import (
    SCHEDULE,
    Backup,
    Coverage,
    Scheduled,
    Verification,
    exposure_seconds,
    last_verified_restore,
    scheduled_exposure_seconds,
    worst_scheduled_exposure_seconds,
)
from brain.ops.reliability import (
    MATRIX,
    FailureMode,
    RecoveryObjective,
    matrix_gaps,
    recovery_objective,
)


class LaunchError(Exception):
    """Raised when a handover pack would state something the estate does not support."""


# ------------------------------------------------------------------ written-down reasons
#: Why every section here is derived and none is written out again.
A_HANDOVER_DOCUMENT_THAT_RESTATES_A_REGISTER_IS_A_SECOND_REGISTER: Final = (
    "A handover document that copies a register out into prose is a second register, and it "
    "is the one that goes stale, because nothing imports it. The subprocessor list is the "
    "case that shows the cost: it is a schedule to a signed agreement, so a provider added "
    "to PROVIDER_SLOTS makes a legal document false with no test anywhere going red. Every "
    "section of this pack is therefore rendered from the register it describes, and what "
    "this module owns is whether the pack is complete rather than what it says."
)

#: Why a service level statement is refused rather than rendered when the figures disagree.
A_PROMISE_THE_SCHEDULE_CANNOT_MEET_IS_STILL_A_PROMISE_THE_CLIENT_SIGNS: Final = (
    "A recovery point objective is a promise about the slowest copy, so a stated recovery "
    "point tighter than the interval the backup schedule actually runs at is a promise the "
    "estate is already failing on the day it is signed. A recovery time is worse, because "
    "nothing measures it except a drill: an unmeasured recovery time is a guess in a "
    "contract, and a measured one the last drill exceeded is a figure somebody has watched "
    "the system miss. All three are refused here rather than rendered with a caveat."
)

#: Why the schedule is not enough on its own to state a recovery point.
A_SCHEDULE_IS_AN_INTENTION_AND_A_COPY_IS_A_FACT: Final = (
    "`SCHEDULE` says how often each thing ought to be copied. It is a declaration, and for "
    "as long as nothing executed it the recovery-point refusal was comparing a promise "
    "against another promise. An estate with no copies at all passed it. What a client signs "
    "has to rest on copies that exist, so the exposure is measured from the newest copy of "
    "each coverage and a coverage with no copy is an unbounded exposure rather than a slow "
    "one, which is a different finding and a worse one."
)

#: Why the subprocessor list is not derived from what has actually been called.
A_SUBPROCESSOR_LIST_NAMES_WHO_MAY_PROCESS_AND_NOT_WHO_HAS: Final = (
    "A subprocessor list built from observed traffic is correct on the day it is written "
    "and wrong the first time a fallback provider is reached, which is the one call nobody "
    "is watching. It therefore names every provider this install holds a key for. A "
    "provider with no key cannot receive anything and is not a subprocessor; a key for a "
    "provider that is not a declared slot is a credential nobody argued about, and it is a "
    "finding rather than a row."
)

#: Why an incomplete pack raises rather than returning the sections it could build.
A_PACK_WITH_A_MISSING_SECTION_IS_NOT_A_SHORTER_PACK: Final = (
    "A pack that renders five of six sections gets handed over, and the sixth is discovered "
    "by whoever needed it, during the incident it was written for. So assembly raises with "
    "every finding at once rather than returning what it could build, and the caller that "
    "wants to show what is outstanding before launch day calls pack_gaps instead."
)

#: Why one responsibility may not have two owners.
A_RESPONSIBILITY_TWO_PEOPLE_OWN_IS_A_RESPONSIBILITY_NEITHER_OWNS: Final = (
    "Two names against knowledge means each of them believes the other is reviewing the "
    "queue. One person owning all three is fine and is what a small client looks like; two "
    "people owning one thing is the arrangement that produces an unattended review queue "
    "with two people able to say they were not asked."
)


# --------------------------------------------------------- who runs it after we walk away
class Responsibility(enum.StrEnum):
    """The three things a client owns from launch day.

    Read against the M37.4.3.3 leaf sentence rather than against a list here, so the
    vocabulary and the leaf cannot drift apart silently.
    """

    KNOWLEDGE = "knowledge"
    GRANTS = "grants"
    CONNECTORS = "connectors"


@dataclass(frozen=True)
class Owner:
    """One named person against one responsibility.

    A contact as well as a name, because "the finance team" is not a person and the point of
    the section is that there is somebody to ask. Both are required and both are checked for
    whitespace, which is what a form posts when a field was left alone.
    """

    responsibility: Responsibility
    name: str
    contact: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            msg = f"{self.responsibility.value} is owned by nobody named"
            raise LaunchError(msg)
        if not self.contact.strip():
            msg = f"{self.name!r} owns {self.responsibility.value} and there is no way to ask them"
            raise LaunchError(msg)


def owner_gaps(owners: Sequence[Owner]) -> tuple[str, ...]:
    """Responsibilities with no owner, and responsibilities with more than one (M37.4.3.3).

    One person owning all three is not a finding. See
    `A_RESPONSIBILITY_TWO_PEOPLE_OWN_IS_A_RESPONSIBILITY_NEITHER_OWNS` for the asymmetry.
    """
    counted: dict[Responsibility, int] = {}
    for one in owners:
        counted[one.responsibility] = counted.get(one.responsibility, 0) + 1
    findings = [
        f"{one.value}: nobody at the client is named as the owner"
        for one in Responsibility
        if one not in counted
    ]
    findings.extend(
        f"{one.value}: {count} owners, and each of them can say they were not asked"
        for one, count in sorted(counted.items())
        if count > 1
    )
    return tuple(findings)


# ---------------------------------------------------- what we promise (M30.5.4, M37.4.2.2)
@dataclass(frozen=True)
class ServiceLevel:
    """The recovery figures for one profile, with what the estate has actually measured.

    Obtainable only from `service_level`, in the same way `brain.ops.recovery.Verification`
    is obtainable only from `verification_of`: every combination that would let a client
    believe more than the estate can do is refused there rather than left to a renderer.

    `measured_rto_seconds` is on the statement deliberately. A service level that states a
    target and hides the last measurement lets a client read the target as an observation,
    and the gap between the two is the whole of what a drill is for.
    """

    profile: str
    rpo_seconds: int
    rto_seconds: int
    scheduled_exposure_seconds: int
    measured_rto_seconds: float
    measured_at: datetime
    because: str


def service_level(
    profile: str,
    *,
    verifications: Sequence[Verification],
    backups: Sequence[Backup],
    now: datetime,
    schedule: Sequence[Scheduled] = SCHEDULE,
    objectives: Sequence[RecoveryObjective] | None = None,
) -> ServiceLevel:
    """The service level statement for a profile, or a refusal naming what does not add up.

    Four refusals, and each is a promise the client would otherwise sign. The schedule must be
    able to deliver the stated recovery point; **the copies that actually exist must be able
    to deliver it too**; a drill must have verified, because an unmeasured recovery time is a
    guess in a contract; and the measured time must be inside the stated one, because a figure
    the last drill exceeded is a figure somebody has watched the system miss. See
    `A_PROMISE_THE_SCHEDULE_CANNOT_MEET_IS_STILL_A_PROMISE_THE_CLIENT_SIGNS` and
    `A_SCHEDULE_IS_AN_INTENTION_AND_A_COPY_IS_A_FACT`.

    `backups` and `now` are required rather than defaulted to nothing and to the clock. A
    default of no copies would make the new refusal fire on every caller that had not been
    updated, which is a check that is red on arrival; a default of an empty sequence that
    passed would be worse, because it would mean the absence of copies reads as compliance.
    Requiring both makes every caller say what it observed and when, which is the same shape
    every other function in `brain.ops.recovery` takes.

    The profile itself is checked by `brain.ops.reliability.recovery_objective`, which
    refuses a profile nothing declares rather than returning a `None` a renderer prints as a
    dash. Its exception is allowed to propagate rather than being caught and re-raised, so
    the caller sees the module that owns the vocabulary.
    """
    objective = recovery_objective(profile, objectives)
    exposure = worst_scheduled_exposure_seconds(schedule)
    if exposure is None:
        msg = (
            f"the {profile} profile promises a recovery point of {objective.rpo_seconds}s "
            "and nothing is scheduled to be copied at all"
        )
        raise LaunchError(msg)
    if exposure > objective.rpo_seconds:
        msg = (
            f"the {profile} profile promises a recovery point of {objective.rpo_seconds}s "
            f"and the slowest copy on the schedule runs every {exposure}s. "
            f"{A_PROMISE_THE_SCHEDULE_CANNOT_MEET_IS_STILL_A_PROMISE_THE_CLIENT_SIGNS}"
        )
        raise LaunchError(msg)
    for coverage in Coverage:
        if scheduled_exposure_seconds(coverage, schedule) is None:
            continue
        measured_exposure = exposure_seconds(backups, coverage, now=now)
        if measured_exposure is None:
            msg = (
                f"the {profile} profile promises a recovery point of {objective.rpo_seconds}s "
                f"and nothing has ever copied {coverage.value}, so the exposure on it is not "
                f"a slow number, it is unbounded. {A_SCHEDULE_IS_AN_INTENTION_AND_A_COPY_IS_A_FACT}"
            )
            raise LaunchError(msg)
        if measured_exposure > objective.rpo_seconds:
            msg = (
                f"the {profile} profile promises a recovery point of {objective.rpo_seconds}s "
                f"and the newest copy of {coverage.value} restores to "
                f"{measured_exposure:.0f}s ago. "
                f"{A_SCHEDULE_IS_AN_INTENTION_AND_A_COPY_IS_A_FACT}"
            )
            raise LaunchError(msg)
    verified = last_verified_restore(verifications)
    if verified is None:
        msg = (
            f"the {profile} profile promises to be back in {objective.rto_seconds}s and no "
            "restore has ever verified, so that figure is a guess in a contract"
        )
        raise LaunchError(msg)
    # `Verification` refuses a verified result with no recovery time, so this is not None
    # here. Asserted rather than assumed, because the alternative is a comparison against
    # None that mypy would accept under a cast and that would render as a passing statement.
    measured = verified.rto_seconds
    if measured is None:  # pragma: no cover - refused by Verification.__post_init__
        msg = f"restore {verified.backup_id!r} verified and recorded no recovery time"
        raise LaunchError(msg)
    if measured > objective.rto_seconds:
        msg = (
            f"the {profile} profile promises to be back in {objective.rto_seconds}s and the "
            f"last verified restore took {measured}s"
        )
        raise LaunchError(msg)
    return ServiceLevel(
        profile=profile,
        rpo_seconds=objective.rpo_seconds,
        rto_seconds=objective.rto_seconds,
        scheduled_exposure_seconds=exposure,
        measured_rto_seconds=measured,
        measured_at=verified.attempted_at,
        because=objective.because,
    )


# ------------------------------------------------------- who else sees it all (M37.4.2.4)
@dataclass(frozen=True)
class Subprocessor:
    """One model provider named on the agreement, with what it is for.

    The purpose is required. A name on a schedule to a data processing agreement with
    nothing next to it is a name the client's lawyer asks about and nobody here can answer,
    and `brain.ops.provider_keys.ProviderSlot` allows an empty description because a slot is
    a key location and does not know it will end up in a contract.
    """

    slug: str
    purpose: str


def subprocessors(
    configured: Iterable[str], *, slots: Sequence[ProviderSlot] = PROVIDER_SLOTS
) -> tuple[Subprocessor, ...]:
    """Every model provider this install can send a question to, in declaration order.

    Derived from the keys the install holds rather than from what has been called, for the
    reason in `A_SUBPROCESSOR_LIST_NAMES_WHO_MAY_PROCESS_AND_NOT_WHO_HAS`.

    Refuses an install configured with no provider at all, because that is an install that
    cannot answer a question and a list stating it processes nothing would be true only
    until somebody set a key.
    """
    held = set(configured)
    if not held:
        msg = (
            "no model provider is configured, so this install cannot answer a question and "
            "an empty subprocessor list would say the opposite"
        )
        raise LaunchError(msg)
    declared = {one.slug: one for one in slots}
    unknown = sorted(held - set(declared))
    if unknown:
        msg = (
            f"a key is configured for {unknown}, which no provider slot declares. "
            f"{A_SUBPROCESSOR_LIST_NAMES_WHO_MAY_PROCESS_AND_NOT_WHO_HAS}"
        )
        raise LaunchError(msg)
    rows: list[Subprocessor] = []
    for slot in slots:
        if slot.slug not in held:
            continue
        if not slot.description.strip():
            msg = (
                f"provider {slot.slug!r} would be named on the agreement with no purpose "
                "beside it, and a schedule to a processing agreement is read by a lawyer"
            )
            raise LaunchError(msg)
        rows.append(Subprocessor(slug=slot.slug, purpose=slot.description))
    return tuple(rows)


# ------------------------------------------------------ a runbook per screen (M37.4.3.1)
def screen_runbook_gaps(
    runbooks: Mapping[str, str], *, screens: Sequence[Screen] = SCREENS
) -> tuple[str, ...]:
    """Console screens with no runbook, and runbooks for screens that do not exist.

    Named for its subject rather than `runbook_gaps`, because `brain.ops.alerting` has a
    function of that name about a different runbook: one is how to work a screen, the other
    is what to do when an alert fires. Two identical names in one handover pack is a reader
    assuming one of them is a duplicate.

    Read off `brain.console.screens.SCREENS` rather than from a list of names here, so the
    thirty-fifth screen arrives as a gap in the pack rather than as a screen the client was
    handed no instructions for. Both directions, because a runbook naming a screen that was
    renamed is worse than a missing one: it reads as coverage.

    A blank runbook is a finding too. An entry present with nothing in it is how a
    completeness check gets satisfied by somebody working through a list.
    """
    known = {one.key for one in screens}
    findings = [
        f"{key}: no runbook, and the client was handed a screen with no instructions"
        for key in sorted(known - set(runbooks))
    ]
    findings.extend(
        f"{key}: a runbook for a screen that does not exist, which reads as coverage"
        for key in sorted(set(runbooks) - known)
    )
    findings.extend(
        f"{key}: the runbook is empty"
        for key in sorted(set(runbooks) & known)
        if not runbooks[key].strip()
    )
    return tuple(findings)


# --------------------------------------------- a playbook per failure mode (M37.4.3.2)
def playbook_gaps(
    rows: Sequence[FailureMode] | None = None, components: Sequence[str] | None = None
) -> tuple[str, ...]:
    """Failure modes the pack cannot hand over, which is `matrix_gaps` under another name.

    Deliberately a call and not a check. `brain.ops.reliability.MATRIX` is the incident
    playbook: it carries what fails, what it presents as, what it blocks, whether the work
    can be retried and what to do. A second completeness check here would be the second
    register `A_HANDOVER_DOCUMENT_THAT_RESTATES_A_REGISTER_IS_A_SECOND_REGISTER` names, and
    the two would disagree the first time a component was added.

    It exists as a function rather than as a bare import so that the pack's own tests can
    pass a matrix in, and so the pack has one name for every section.
    """
    return matrix_gaps(rows, components)


def playbooks(rows: Sequence[FailureMode] | None = None) -> tuple[FailureMode, ...]:
    """The incident playbook handed over, in declaration order."""
    return MATRIX if rows is None else tuple(rows)


# ----------------------------------------------- the date it is looked at again (M37.4.3.5)
#: How long after launch the review happens. Thirty days, which is the leaf's own figure and
#: is asserted against the leaf sentence rather than against itself.
#:
#: The window matters more than the number. A review booked for day ninety is a review nobody
#: has, because by then the questions that came up in week one have been worked around and
#: the workarounds are the process.
REVIEW_AFTER_DAYS: Final[int] = 30


def review_gaps(*, launched_on: date, review_booked_for: date) -> tuple[str, ...]:
    """Whether the post-launch review is booked, and booked inside the window (M37.4.3.5).

    Booked at handover rather than promised at handover, which is why the date is a field on
    the pack and not a task somewhere: a date that has to be agreed later is agreed later,
    and later is after the month it was meant to cover.

    On the day itself is allowed. Earlier than launch is not, and neither is a review on
    launch day, which is a review of nothing.
    """
    if review_booked_for <= launched_on:
        return (
            f"the post-launch review is booked for {review_booked_for.isoformat()} and the "
            f"install goes live on {launched_on.isoformat()}, so it reviews nothing",
        )
    days = (review_booked_for - launched_on).days
    if days > REVIEW_AFTER_DAYS:
        return (
            f"the post-launch review is booked {days} days after launch, and by then the "
            "workarounds people invented in week one are the process",
        )
    return ()


# ------------------------------------------------------------------------ the pack itself
@dataclass(frozen=True)
class Pack:
    """Everything that changes hands on launch day. Obtainable only from `assemble`."""

    profile: str
    launched_on: date
    review_booked_for: date
    service_level: ServiceLevel
    subprocessors: tuple[Subprocessor, ...]
    owners: tuple[Owner, ...]
    screen_runbooks: Mapping[str, str]
    playbooks: tuple[FailureMode, ...]


#: The sections a pack has to carry, in the order they are handed over. Named so a caller
#: showing progress before launch has something to iterate rather than a count.
SECTIONS: Final[tuple[str, ...]] = (
    "service_level",
    "subprocessors",
    "screen_runbooks",
    "playbooks",
    "owners",
    "review",
)


def pack_gaps(
    *,
    owners: Sequence[Owner],
    screen_runbooks: Mapping[str, str],
    launched_on: date,
    review_booked_for: date,
    screens: Sequence[Screen] = SCREENS,
    rows: Sequence[FailureMode] | None = None,
    components: Sequence[str] | None = None,
) -> tuple[str, ...]:
    """Everything outstanding on the pack, without raising.

    The service level and the subprocessor list are absent from this list on purpose: both
    refuse in their own constructors, with a message naming the arithmetic that failed, and
    reducing either to a finding string here would throw away the figures. `assemble` calls
    them and lets those exceptions through.
    """
    findings = list(owner_gaps(owners))
    findings.extend(screen_runbook_gaps(screen_runbooks, screens=screens))
    findings.extend(playbook_gaps(rows, components))
    findings.extend(review_gaps(launched_on=launched_on, review_booked_for=review_booked_for))
    return tuple(findings)


def assemble(
    profile: str,
    *,
    configured_providers: Iterable[str],
    verifications: Sequence[Verification],
    backups: Sequence[Backup],
    now: datetime,
    owners: Sequence[Owner],
    screen_runbooks: Mapping[str, str],
    launched_on: date,
    review_booked_for: date,
    schedule: Sequence[Scheduled] = SCHEDULE,
    objectives: Sequence[RecoveryObjective] | None = None,
    screens: Sequence[Screen] = SCREENS,
    rows: Sequence[FailureMode] | None = None,
    components: Sequence[str] | None = None,
) -> Pack:
    """The pack, or a refusal listing everything that is not ready.

    Order matters and it is not the order of the sections. The two sections that refuse by
    arithmetic run first, so a client whose backup schedule cannot meet their own recovery
    point hears that rather than hearing about a missing runbook. Then every remaining gap is
    collected and raised together, for the reason in
    `A_PACK_WITH_A_MISSING_SECTION_IS_NOT_A_SHORTER_PACK`.

    `backups` and `now` are passed straight through to `service_level` and are required here
    for the same reason they are required there: a pack assembled without observing the
    copies would state a recovery point on an estate that holds none.
    """
    level = service_level(
        profile,
        verifications=verifications,
        backups=backups,
        now=now,
        schedule=schedule,
        objectives=objectives,
    )
    named = subprocessors(configured_providers)
    findings = pack_gaps(
        owners=owners,
        screen_runbooks=screen_runbooks,
        launched_on=launched_on,
        review_booked_for=review_booked_for,
        screens=screens,
        rows=rows,
        components=components,
    )
    if findings:
        msg = "this pack is not ready to hand over:\n" + "\n".join(f"  {one}" for one in findings)
        raise LaunchError(msg)
    return Pack(
        profile=profile,
        launched_on=launched_on,
        review_booked_for=review_booked_for,
        service_level=level,
        subprocessors=named,
        owners=tuple(owners),
        screen_runbooks=dict(screen_runbooks),
        playbooks=playbooks(rows),
    )
