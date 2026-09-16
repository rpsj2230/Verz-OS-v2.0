"""Two passes and a look at the system of record, and why the second pass may see a picture.

`brain.browsing.grading` applies a rubric to outcomes. This module decides which outcomes a
verdict may rest on: the actions alone, then pictures of the page, then the system of record
asked out of band. Each source can only take a pass away, never grant one the others refused.

**Vision is refused to the hands and not to the judge.** `grading` used to record M19.5.2 and
M19.4.5 as two leaves asking for opposite things, and read that way they are. Read by who sees
what, they are not. M19.4.5 exists because a model deciding the next action while a password
sits in a form would carry that password into a prompt, a trace and every turn built from it.
The second pass is a judge of a run that has ended: it decides nothing a browser does. So the
actor still has no field a picture could arrive in (`brain.browsing.observation.Snapshot`), and
the judge sees only frames `admit_frames` lets through. See
`VISION_IS_REFUSED_TO_THE_HANDS_AND_NOT_TO_THE_JUDGE`.

**A frame is admitted on three conditions, and each is a way a credential reaches a picture.**
The runner painted over every form control before capture, so a typed value is not in the
pixels. No credential has been typed since the run last opened a declared surface, because a
page can copy a value out of its own input and draw it anywhere, and the page after a login is
usually the login's own reply: a frame from the typing onwards is withheld until an `OPEN` loads a
page the run chose rather than one the form led to. And the accessibility
tree taken beside the frame held no bound secret value: `brain.browsing.credentials.
scrub_outbound` finds a value in text exactly, a picture cannot be scrubbed at all, so the tree
is the witness for the picture. What this does not catch is a page drawing a value to a canvas
with no text node behind it, and that is said here rather than implied.

**The second pass runs only on a run the first pass passed.** Pictures leave for a judge only
when the cheaper, picture-free judgement could not already fail the run, which is both the
order M19.5.2 names and the smallest number of pictures that go anywhere. `verify_run` refuses
second-pass outcomes for a run the first pass failed, rather than ignoring them, because their
existence means pictures were sent for nothing. And a first pass that passed with no admitted
frame to confirm it does not pass: the tie-break is M19.5.4's, towards failure.

**Out of band means not through the browser, and where possible means where it can be asked
today.** A target declares, per write surface, the tool that reads its system of record
(`brain.browsing.targets.Surface.read_back`). That read is possible when the tool is registered
on this install, declares no side effect and is not a browser tool. A read-back through the
browser is the page marking its own work, and a look that writes is not a look. A declaration
that cannot be asked is not an error: the check says why it could not, and the verdict lists the
write as not confirmed rather than letting the list of confirmed writes stay quietly short.

**The read runs under the person who asked, through the gate.** `ReadBackPort.look` carries the
asker's principal, because a verifier that read the system of record under a service reach
would be a second way to read it, and the verdict would disclose what the asker could not see.

**A read-back's answer is `brain.ops.idempotency.Verification`, not a new vocabulary.** FOUND,
ABSENT and INCONCLUSIVE are already the platform's words for "did our write land", and
`brain.connectors.write_verification` already turns a connector's reply into one of them.
INCONCLUSIVE is UNKNOWN here, and UNKNOWN fails a run.

Rejected: letting a read-back that found the record override a pass that saw an error. The
system of record is the stronger witness about whether the record exists, and the page is the
stronger witness about whether it is the record that was asked for. Both have to agree, and a
disagreement is a false negative somebody reads, which is the cheap error.

Task ids: M19.5.2, M19.5.5
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Protocol, assert_never

from brain.browsing.grading import Outcome, Rubric, Score, Trajectory, landed_criterion, score
from brain.browsing.observation import Frame
from brain.browsing.planning import PlanRequest
from brain.browsing.sessions import READ_SURFACE
from brain.browsing.targets import Target, Verb
from brain.core.envelope import SideEffect
from brain.ops.idempotency import Verification
from brain.tools.registry import ToolRegistry

#: Why a picture may reach the judge and never the actor.
VISION_IS_REFUSED_TO_THE_HANDS_AND_NOT_TO_THE_JUDGE: Final = (
    "M19.4.5 keeps a picture away from whatever decides the next action, because a model "
    "choosing where to click while a password sits in a form carries the password into its "
    "prompt, its trace and every turn after. A judge of a finished run chooses nothing a browser "
    "does. It may see a frame whose form controls were painted over, from a page no credential "
    "was typed into, beside a tree that held no bound secret, and it sees nothing else."
)

#: Why the later sources can only remove a pass.
EVERY_WITNESS_MUST_AGREE: Final = (
    "A criterion is met when every source that could judge it says met. One source saying not "
    "met fails it, and one that could not say leaves it unknown, which fails it too. So adding "
    "the picture pass or the read-back can turn a pass into a failure and never the reverse, "
    "which is the direction M19.5.4 accepts errors in."
)

#: Why a read-back through the browser is refused.
A_READ_BACK_THROUGH_THE_BROWSER_IS_THE_PAGE_MARKING_ITS_OWN_WORK: Final = (
    "The page is the witness whose account is in question. Asking it again, through the same "
    "session, on the same site, checks nothing a hostile or broken page could not repeat, so a "
    "browser tool is never a read-back, whatever the target declares."
)


class VerificationError(Exception):
    """Evidence was offered in a shape that would let a verdict rest on something it must not."""


@dataclass(frozen=True)
class AdmittedFrames:
    """The frames a second-pass judge may be handed, and how many were held back and why.

    The only value a judge's input should be built from. `withheld` carries a sequence and a
    reason and never the frame, so a report about withholding cannot become a way round it.
    """

    run_id: str
    frames: tuple[Frame, ...] = ()
    withheld: tuple[tuple[int, str], ...] = ()


#: The three reasons a frame is withheld, as the report states them.
NOT_MASKED: Final = "the form controls were not painted over"
CREDENTIAL_TYPED_HERE: Final = (
    "a credential was typed and no declared surface has been opened since"
)
SECRET_IN_THE_TREE: Final = "the tree beside this frame held a bound credential value"  # noqa: S105


def admit_frames(
    trajectory: Trajectory,
    frames: Sequence[Frame],
    *,
    secret_sequences: frozenset[int],
) -> AdmittedFrames:
    """Which frames the second pass may see (M19.5.2), under the three conditions above.

    `secret_sequences` are the snapshots in which scrubbing the tree's text found a bound value,
    as the recording reports them. A frame from another run raises: that is a wiring fault, and
    a judge handed it would be judging a different run.
    """
    typed = sorted(
        record.action.sequence + 1 for record in trajectory.records if record.action.placeholder
    )
    opened = sorted(
        record.action.sequence for record in trajectory.records if record.action.verb is Verb.OPEN
    )
    admitted: list[Frame] = []
    withheld: list[tuple[int, str]] = []
    for frame in frames:
        if frame.run_id != trajectory.run_id:
            msg = (
                f"a frame from run {frame.run_id!r} was offered as evidence about run "
                f"{trajectory.run_id!r}"
            )
            raise VerificationError(msg)
        if not frame.inputs_masked:
            withheld.append((frame.sequence, NOT_MASKED))
        elif _typed_before(frame.sequence, typed, opened):
            withheld.append((frame.sequence, CREDENTIAL_TYPED_HERE))
        elif frame.sequence in secret_sequences:
            withheld.append((frame.sequence, SECRET_IN_THE_TREE))
        else:
            admitted.append(frame)
    return AdmittedFrames(
        run_id=trajectory.run_id, frames=tuple(admitted), withheld=tuple(withheld)
    )


def _typed_before(sequence: int, typed: Sequence[int], opened: Sequence[int]) -> bool:
    """Whether a credential was typed at or before this picture with no `OPEN` in between.

    `typed` holds the first snapshot after each typing, and `opened` the snapshot each `OPEN`
    loaded, so a picture is clean again from the first `OPEN` after the last typing before it.
    """
    return any(
        first <= sequence and not any(first < loaded <= sequence for loaded in opened)
        for first in typed
    )


def needs_second_pass(first: Score) -> bool:
    """Whether any picture should be sent to a judge. Only for a run the actions passed."""
    return first.passed


@dataclass(frozen=True)
class ReadBackCheck:
    """How one write criterion will be confirmed out of band, or why it cannot be.

    `tool` and `why_not` are exclusive, and exactly one is set. A check with neither would read
    as a confirmation nobody asked for; a check with both would be possible and impossible.
    """

    surface: str
    criterion: str
    tool: str = ""
    why_not: str = ""

    def __post_init__(self) -> None:
        if bool(self.tool) == bool(self.why_not):
            msg = (
                f"the read-back check for {self.surface!r} must name a tool or say why there is "
                "none, and not both"
            )
            raise VerificationError(msg)

    @property
    def possible(self) -> bool:
        return bool(self.tool)


#: Why a declared read-back could not be asked, one sentence per reason.
NOTHING_DECLARED: Final = "the target declares no read of the system of record for this surface"
NOT_REGISTERED: Final = "the declared read-back tool is not registered on this install"
WRITES: Final = (
    "the declared read-back tool declares a side effect, and a look that writes is not a look"
)
THROUGH_THE_BROWSER: Final = (
    "the declared read-back tool is a browser tool, which asks the page again"
)


def read_back_plan(
    request: PlanRequest, target: Target, registry: ToolRegistry
) -> tuple[ReadBackCheck, ...]:
    """One check per write surface the request names, decided before the run (M19.5.5).

    From the declaration and the registry alone, like the rubric, so the list of writes that
    will be confirmed cannot be shaped by what the run went on to do.
    """
    checks: list[ReadBackCheck] = []
    for name in request.surfaces:
        surface = target.surface(name)
        if surface is None or not surface.writes():
            continue
        criterion = landed_criterion(name)
        tool = surface.read_back
        if not tool:
            checks.append(ReadBackCheck(name, criterion, why_not=NOTHING_DECLARED))
            continue
        if not registry.has(tool):
            checks.append(ReadBackCheck(name, criterion, why_not=NOT_REGISTERED))
            continue
        definition = registry.get(tool).definition
        if definition.side_effect is not SideEffect.NONE:
            checks.append(ReadBackCheck(name, criterion, why_not=WRITES))
        elif definition.source == READ_SURFACE.source:
            checks.append(ReadBackCheck(name, criterion, why_not=THROUGH_THE_BROWSER))
        else:
            checks.append(ReadBackCheck(name, criterion, tool=tool))
    return tuple(checks)


@dataclass(frozen=True)
class ReadBackRequest:
    """One look at a system of record, made as the person who asked for the run."""

    run_id: str
    target: str
    surface: str
    tool: str
    #: Whose reach the look runs under. Never a service identity: see the module docstring.
    principal_id: str


class ReadBackPort(Protocol):
    """What asking a system of record looks like from here: one read, through the gate."""

    def look(self, request: ReadBackRequest) -> Verification:
        """Call the read-back tool under the asker's reach and say whether the write is there."""
        ...


def read_back(
    checks: Sequence[ReadBackCheck],
    port: ReadBackPort,
    *,
    run_id: str,
    target: str,
    principal_id: str,
) -> dict[str, Verification]:
    """Ask every possible check, and only those, keyed by criterion.

    A check that is not possible is not asked. Asking anyway would mean choosing some other tool
    to ask, which is the declaration being overridden by whoever wrote the caller.
    """
    if not principal_id.strip():
        msg = f"the read-back for run {run_id!r} names nobody to read as"
        raise VerificationError(msg)
    found: dict[str, Verification] = {}
    for check in checks:
        if not check.possible:
            continue
        found[check.criterion] = port.look(
            ReadBackRequest(
                run_id=run_id,
                target=target,
                surface=check.surface,
                tool=check.tool,
                principal_id=principal_id,
            )
        )
    return found


def outcome_of(verification: Verification) -> Outcome:
    """A read-back's answer in the rubric's words. INCONCLUSIVE is UNKNOWN, and fails a run."""
    match verification:
        case Verification.FOUND:
            return Outcome.MET
        case Verification.ABSENT:
            return Outcome.NOT_MET
        case Verification.INCONCLUSIVE:
            return Outcome.UNKNOWN
        case _:  # pragma: no cover - exhaustive, and the type checker proves it
            assert_never(verification)


def agree(outcomes: Sequence[Outcome]) -> Outcome:
    """Every witness's outcome for one criterion, combined. See `EVERY_WITNESS_MUST_AGREE`."""
    if Outcome.NOT_MET in outcomes:
        return Outcome.NOT_MET
    if outcomes and all(one is Outcome.MET for one in outcomes):
        return Outcome.MET
    return Outcome.UNKNOWN


@dataclass(frozen=True)
class Verdict:
    """The verdict on one run, and every witness it rests on.

    `second` is None when the second pass did not run, which happens exactly when the first
    failed. `unconfirmed` names each write criterion that could not be read back, with why.
    """

    passed: bool
    first: Score
    second: Score | None
    outcomes: tuple[tuple[str, Outcome], ...]
    frames_admitted: int
    frames_withheld: int
    confirmed: tuple[str, ...] = ()
    unconfirmed: tuple[tuple[str, str], ...] = ()


def verify_run(
    rubric: Rubric,
    trajectory: Trajectory,
    *,
    actions_only: Mapping[str, Outcome],
    with_frames: Mapping[str, Outcome] | None,
    admitted: AdmittedFrames,
    checks: Sequence[ReadBackCheck],
    read_backs: Mapping[str, Verification],
) -> Verdict:
    """Two passes, then the system of record, and a pass only where every witness agrees.

    `actions_only` is the first pass's judgement, made from the trajectory with no picture.
    `with_frames` is the second pass's, made with the admitted frames, and must be None for a
    run the first pass failed. `read_backs` are what `read_back` returned for `checks`.
    """
    if admitted.run_id != trajectory.run_id:
        msg = f"frames admitted for run {admitted.run_id!r} were offered for {trajectory.run_id!r}"
        raise VerificationError(msg)
    first = score(rubric, trajectory, actions_only)
    if not needs_second_pass(first) and with_frames is not None:
        msg = (
            f"run {trajectory.run_id!r} failed on its actions and was judged on pictures anyway, "
            "so pictures were sent to a judge for a verdict that was already decided"
        )
        raise VerificationError(msg)
    possible = {check.criterion for check in checks if check.possible}
    stray = sorted(set(read_backs) - possible)
    if stray:
        msg = (
            f"read-backs were offered for {stray}, which no possible check names, so they came "
            "from a tool the declaration did not choose"
        )
        raise VerificationError(msg)
    second: Score | None = None
    if needs_second_pass(first):
        # No admitted frame means nothing for the second pass to have looked at, so whatever it
        # said is discarded and every criterion is unresolved on that pass.
        judged = with_frames if with_frames is not None and admitted.frames else {}
        second = score(rubric, trajectory, judged)
    outcomes: list[tuple[str, Outcome]] = []
    for criterion in rubric.criteria:
        witnesses = [actions_only.get(criterion.name, Outcome.UNKNOWN)]
        if second is not None:
            witnesses.append(_outcome_in(second, criterion.name))
        if criterion.name in possible:
            witnesses.append(outcome_of(read_backs.get(criterion.name, Verification.INCONCLUSIVE)))
        outcomes.append((criterion.name, agree(witnesses)))
    final = dict(outcomes)
    required = [one.name for one in rubric.required()]
    passed = bool(required) and all(final[name] is Outcome.MET for name in required)
    return Verdict(
        passed=passed,
        first=first,
        second=second,
        outcomes=tuple(outcomes),
        frames_admitted=len(admitted.frames),
        frames_withheld=len(admitted.withheld),
        confirmed=tuple(
            check.criterion
            for check in checks
            if check.possible and read_backs.get(check.criterion) is Verification.FOUND
        ),
        unconfirmed=tuple(
            (check.criterion, check.why_not) for check in checks if not check.possible
        ),
    )


def _outcome_in(verdict: Score, name: str) -> Outcome:
    """What one scoring pass concluded about one criterion, read back off its score."""
    if name in verdict.met:
        return Outcome.MET
    if name in verdict.failed:
        return Outcome.NOT_MET
    return Outcome.UNKNOWN
