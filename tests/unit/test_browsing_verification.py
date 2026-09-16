"""Two passes and a read-back, each able to take a pass away and none able to grant one.

The two properties that carry M19.5.2 and M19.5.5 are enumerated rather than sampled: every
combination of what the actions, the pictures and the system of record said, for one required
criterion. The rest are the conditions a picture must meet before a judge sees it, and the
conditions a declared read-back must meet before it counts as out of band.

Task ids: M19.5.2, M19.5.5
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime

import pytest

from brain.browsing.enforcer import Action, ActionRecord
from brain.browsing.grading import (
    Criterion,
    Outcome,
    Rubric,
    Trajectory,
    build_rubric,
    landed_criterion,
    verification_gaps,
)
from brain.browsing.observation import Frame
from brain.browsing.planning import Goal, PlanRequest
from brain.browsing.sessions import READ_SURFACE, SurfaceReading
from brain.browsing.targets import Surface, Target, TargetError, Verb
from brain.browsing.verification import (
    CREDENTIAL_TYPED_HERE,
    NOT_MASKED,
    NOT_REGISTERED,
    NOTHING_DECLARED,
    SECRET_IN_THE_TREE,
    THROUGH_THE_BROWSER,
    WRITES,
    AdmittedFrames,
    ReadBackCheck,
    ReadBackRequest,
    VerificationError,
    admit_frames,
    agree,
    outcome_of,
    read_back,
    read_back_plan,
    verify_run,
)
from brain.core.entitlement import Capability
from brain.core.envelope import Entity, IdentityMode, SideEffect, ToolDefinition, TypedResult
from brain.ops.idempotency import Verification
from brain.tools.registry import ToolRegistry

ORIGIN = "https://books.example"
NOW = datetime(2999, 1, 1, tzinfo=UTC)
WRITE = Capability(value="write:browser_surface")
DIGEST = "a" * 64


def target(read_back: str = "books.find_filing") -> Target:
    return Target(
        name="books",
        origins=frozenset({ORIGIN}),
        surfaces=(
            Surface(
                name="filing",
                origin=ORIGIN,
                path="/filing",
                verbs=frozenset({Verb.OPEN, Verb.SUBMIT}),
                capability=WRITE,
                read_back=read_back,
            ),
        ),
    )


def request() -> PlanRequest:
    return PlanRequest(
        goal=Goal(text="File the return", asked_by="alex"), target="books", surfaces=("filing",)
    )


def trajectory(*records: ActionRecord) -> Trajectory:
    return Trajectory(run_id="run-1", records=records)


def record(sequence: int, *, placeholder: str = "") -> ActionRecord:
    return ActionRecord(
        action=Action(
            run_id="run-1",
            surface="filing",
            verb=Verb.TYPE if placeholder else Verb.SUBMIT,
            origin=ORIGIN,
            ref="n1",
            sequence=sequence,
            placeholder=placeholder,
        ),
        claimed_allowed=True,
    )


def opened(sequence: int) -> ActionRecord:
    return ActionRecord(
        action=Action(
            run_id="run-1", surface="filing", verb=Verb.OPEN, origin=ORIGIN, sequence=sequence
        ),
        claimed_allowed=True,
    )


def frame(sequence: int, *, masked: bool = True, run_id: str = "run-1") -> Frame:
    return Frame(
        run_id=run_id, sequence=sequence, origin=ORIGIN, digest=DIGEST, inputs_masked=masked
    )


def one_criterion() -> Rubric:
    return Rubric(
        goal="abc", built_at=NOW, criteria=(Criterion(name="landed_filing", text="it landed"),)
    )


CHECK = ReadBackCheck(surface="filing", criterion="landed_filing", tool="books.find_filing")


def _handler() -> TypedResult[SurfaceReading]:
    return TypedResult[SurfaceReading](records=())


def registry(*, side_effect: SideEffect = SideEffect.NONE, source: str = "books") -> ToolRegistry:
    """A registry holding one read-back candidate, registered through the real refusals."""
    built = ToolRegistry()
    built.register(
        ToolDefinition(
            name=f"{source}.find_filing",
            description="Find a filing in the books by the run that made it.",
            entity="browser_surface",
            required_capability=(
                "read:browser_surface" if side_effect is SideEffect.NONE else WRITE.value
            ),
            side_effect=side_effect,
            identity_mode=IdentityMode.DELEGATED,
            source=source,
        ),
        _handler,
    )
    return built


# ------------------------------------------------------------------ the enumerations
def test_a_run_passes_only_when_the_actions_the_pictures_and_the_system_of_record_all_agree() -> (
    None
):
    """**M19.5.2 and M19.5.5 in one table.** One required criterion, every outcome of the first
    pass, every outcome of the second, every answer of the read-back: 27 combinations, and the
    run passes in exactly one of them.

    Delete this and any one witness can be made sufficient, which is the edit somebody makes when
    the read-back is slow or the pictures are expensive, and every run it lets through is a write
    reported as done on the word of the page."""
    passes = []
    for first, second, looked in itertools.product(Outcome, Outcome, Verification):
        admitted = AdmittedFrames(run_id="run-1", frames=(frame(1),))
        first_passed = first is Outcome.MET
        verdict = verify_run(
            one_criterion(),
            trajectory(),
            actions_only={"landed_filing": first},
            with_frames={"landed_filing": second} if first_passed else None,
            admitted=admitted,
            checks=(CHECK,),
            read_backs={"landed_filing": looked},
        )
        if verdict.passed:
            passes.append((first, second, looked))

    assert passes == [(Outcome.MET, Outcome.MET, Verification.FOUND)]


def test_the_second_pass_can_take_a_pass_away_and_never_grant_one() -> None:
    """The asymmetry stated directly, over every pair of pass outcomes with no read-back.

    Delete this and the second pass can be allowed to resolve what the first left unknown, which
    reads as the pictures adding information and is the pictures overruling the actions."""
    for first, second in itertools.product(Outcome, Outcome):
        verdict = verify_run(
            one_criterion(),
            trajectory(),
            actions_only={"landed_filing": first},
            with_frames={"landed_filing": second} if first is Outcome.MET else None,
            admitted=AdmittedFrames(run_id="run-1", frames=(frame(1),)),
            checks=(),
            read_backs={},
        )
        if verdict.passed:
            assert verdict.first.passed
        assert verdict.passed is (first is Outcome.MET and second is Outcome.MET)


def test_agreement_is_met_only_when_every_witness_says_met() -> None:
    """The combining rule, against every sequence of up to three outcomes.

    Delete this and `agree` can be written as "any met" or "the last witness wins", each of which
    passes the tables above only for the witnesses they happen to order."""
    for size in (1, 2, 3):
        for outcomes in itertools.product(Outcome, repeat=size):
            expected = (
                Outcome.NOT_MET
                if Outcome.NOT_MET in outcomes
                else Outcome.MET
                if all(one is Outcome.MET for one in outcomes)
                else Outcome.UNKNOWN
            )
            assert agree(outcomes) is expected, outcomes
    assert agree(()) is Outcome.UNKNOWN


def test_an_inconclusive_read_back_is_unknown_and_never_met_or_absent() -> None:
    """The platform's third answer kept apart here as it is in `brain.ops.idempotency`.

    Delete this and INCONCLUSIVE can be mapped to MET because the record is probably there, and a
    read-back that timed out becomes a confirmation."""
    assert outcome_of(Verification.FOUND) is Outcome.MET
    assert outcome_of(Verification.ABSENT) is Outcome.NOT_MET
    assert outcome_of(Verification.INCONCLUSIVE) is Outcome.UNKNOWN


# ------------------------------------------------------------------ the second pass
def test_pictures_judged_for_a_run_the_actions_already_failed_are_refused() -> None:
    """The order M19.5.2 names, and the smallest number of pictures that leave for a judge.

    Delete this and every run can be sent for picture judgement, including the ones whose verdict
    no picture could change."""
    with pytest.raises(VerificationError, match="pictures were sent"):
        verify_run(
            one_criterion(),
            trajectory(),
            actions_only={"landed_filing": Outcome.NOT_MET},
            with_frames={"landed_filing": Outcome.MET},
            admitted=AdmittedFrames(run_id="run-1", frames=(frame(1),)),
            checks=(),
            read_backs={},
        )


def test_a_first_pass_with_no_admitted_frame_to_confirm_it_does_not_pass() -> None:
    """A second pass over no pictures looked at nothing, so what it said is not evidence.

    Delete this and a runner that never masks, so that every frame is withheld, passes every run
    on the actions alone with the second pass reporting met."""
    verdict = verify_run(
        one_criterion(),
        trajectory(),
        actions_only={"landed_filing": Outcome.MET},
        with_frames={"landed_filing": Outcome.MET},
        admitted=AdmittedFrames(run_id="run-1", frames=(), withheld=((1, NOT_MASKED),)),
        checks=(),
        read_backs={},
    )

    assert not verdict.passed
    assert verdict.second is not None and verdict.second.unresolved == ("landed_filing",)
    assert verdict.frames_withheld == 1


def test_a_run_judged_on_both_passes_with_admitted_frames_passes() -> None:
    """The positive case, with no read-back declared, so the write is listed as unconfirmed.

    Delete this and a verifier that fails everything satisfies every refusal in this file."""
    verdict = verify_run(
        one_criterion(),
        trajectory(),
        actions_only={"landed_filing": Outcome.MET},
        with_frames={"landed_filing": Outcome.MET},
        admitted=AdmittedFrames(run_id="run-1", frames=(frame(1),)),
        checks=(
            ReadBackCheck(surface="filing", criterion="landed_filing", why_not=NOTHING_DECLARED),
        ),
        read_backs={},
    )

    assert verdict.passed
    assert verdict.frames_admitted == 1
    assert verdict.unconfirmed == (("landed_filing", NOTHING_DECLARED),)
    assert verdict.confirmed == ()


def test_a_frame_whose_form_controls_were_not_painted_over_is_withheld() -> None:
    """M19.4.5's own condition, carried into the picture.

    Delete this and a frame of a login form with the password field unmasked is handed to a judge,
    which is the credential in a picture."""
    admitted = admit_frames(trajectory(), [frame(1, masked=False)], secret_sequences=frozenset())

    assert admitted.frames == ()
    assert admitted.withheld == ((1, NOT_MASKED),)


def test_frames_after_a_credential_is_typed_are_withheld_until_a_declared_surface_is_opened() -> (
    None
):
    """A page can copy a value out of its own input and draw it, and the page a login form leads to
    is the form's own reply. So pictures from the typing onwards are withheld, masked or not, until
    the run opens a surface it chose.

    Delete this and masking the inputs is the only condition, which a page defeats with one line
    of script that renders the password where no text node holds it."""
    admitted = admit_frames(
        trajectory(record(2, placeholder="{{secret:books_password}}"), opened(5)),
        [frame(2), frame(3), frame(4), frame(5), frame(6)],
        secret_sequences=frozenset(),
    )

    assert [one.sequence for one in admitted.frames] == [2, 5, 6]
    assert admitted.withheld == ((3, CREDENTIAL_TYPED_HERE), (4, CREDENTIAL_TYPED_HERE))


def test_a_second_typing_after_an_opening_withholds_again() -> None:
    """Delete this and one `OPEN` anywhere in a run clears every later typing too."""
    admitted = admit_frames(
        trajectory(
            record(1, placeholder="{{secret:books_password}}"),
            opened(3),
            record(4, placeholder="{{secret:books_code}}"),
        ),
        [frame(2), frame(3), frame(5)],
        secret_sequences=frozenset(),
    )

    assert [one.sequence for one in admitted.frames] == [3]


def test_a_frame_beside_a_tree_that_held_a_bound_secret_is_withheld() -> None:
    """The tree is the witness for the picture, because text can be scrubbed and pixels cannot.

    Delete this and a page that echoes the password on the next page, not the one it was typed on,
    reaches a judge in a picture."""
    admitted = admit_frames(trajectory(), [frame(3)], secret_sequences=frozenset({3}))

    assert admitted.frames == ()
    assert admitted.withheld == ((3, SECRET_IN_THE_TREE),)


def test_a_clean_frame_is_admitted_beside_withheld_ones() -> None:
    """The positive case for admission, and the proof it is per frame rather than per run.

    Delete this and `admit_frames` can withhold everything, which satisfies the three tests above
    and turns every second pass into a failure."""
    admitted = admit_frames(
        trajectory(record(1, placeholder="{{secret:books_password}}")),
        [frame(1), frame(2), frame(3, masked=False)],
        secret_sequences=frozenset(),
    )

    assert [one.sequence for one in admitted.frames] == [1]
    assert len(admitted.withheld) == 2


def test_a_frame_from_another_run_is_refused_rather_than_withheld() -> None:
    """A wiring fault, not a condition. Delete this and a judge can be handed another run's page."""
    with pytest.raises(VerificationError, match="offered as evidence"):
        admit_frames(trajectory(), [frame(1, run_id="run-2")], secret_sequences=frozenset())


def test_admitted_frames_for_another_run_are_refused_by_the_verdict() -> None:
    """Delete this and frames admitted for one run can confirm another's verdict."""
    with pytest.raises(VerificationError, match="were offered for"):
        verify_run(
            one_criterion(),
            trajectory(),
            actions_only={},
            with_frames=None,
            admitted=AdmittedFrames(run_id="run-2"),
            checks=(),
            read_backs={},
        )


# ------------------------------------------------------------------ the read-back
def test_a_registered_read_only_tool_that_is_not_the_browser_is_a_possible_read_back() -> None:
    """The positive case for M19.5.5's "where possible".

    Delete this and `read_back_plan` can refuse every declaration, which satisfies every refusal
    below and confirms no write ever."""
    checks = read_back_plan(request(), target(), registry())

    assert checks == (
        ReadBackCheck(surface="filing", criterion="landed_filing", tool="books.find_filing"),
    )
    assert checks[0].criterion == landed_criterion("filing")


@pytest.mark.parametrize(
    ("declared", "tools", "why"),
    [
        ("", registry(), NOTHING_DECLARED),
        ("books.find_filing", ToolRegistry(), NOT_REGISTERED),
        ("books.find_filing", registry(side_effect=SideEffect.WRITE), WRITES),
        ("browser.find_filing", registry(source=READ_SURFACE.source), THROUGH_THE_BROWSER),
    ],
    ids=["nothing declared", "not registered", "writes", "through the browser"],
)
def test_a_read_back_that_is_not_out_of_band_says_why_and_is_not_asked(
    declared: str, tools: ToolRegistry, why: str
) -> None:
    """Four ways a declaration is not a look at the system of record, each named.

    Delete this and a browser tool can be declared as the read-back, which asks the page whether
    the page was right."""
    checks = read_back_plan(request(), target(declared), tools)

    assert checks == (ReadBackCheck(surface="filing", criterion="landed_filing", why_not=why),)


def test_a_surface_that_writes_nothing_gets_no_read_back_check() -> None:
    """Delete this and a read-only surface gets a check that can only ever be unconfirmed."""
    reading = Target(
        name="books",
        origins=frozenset({ORIGIN}),
        surfaces=(
            Surface(
                name="invoices",
                origin=ORIGIN,
                path="/invoices",
                verbs=frozenset({Verb.OPEN, Verb.READ}),
                capability=WRITE,
                reads=("total",),
            ),
        ),
    )
    asked = PlanRequest(
        goal=Goal(text="Read totals", asked_by="alex"), target="books", surfaces=("invoices",)
    )

    assert read_back_plan(asked, reading, registry()) == ()


class _Port:
    def __init__(self, answer: Verification) -> None:
        self.answer = answer
        self.asked: list[ReadBackRequest] = []

    def look(self, request: ReadBackRequest) -> Verification:
        self.asked.append(request)
        return self.answer


def test_only_possible_checks_are_asked_and_they_are_asked_as_the_person_who_asked() -> None:
    """The read runs under the asker's reach, and an impossible check is never quietly routed to
    some other tool.

    Delete this and the port can be called with a service identity, which reads the system of
    record under a reach nobody granted the asker."""
    port = _Port(Verification.FOUND)
    checks = (
        CHECK,
        ReadBackCheck(surface="login", criterion="landed_login", why_not=NOTHING_DECLARED),
    )

    found = read_back(checks, port, run_id="run-1", target="books", principal_id="alex")

    assert found == {"landed_filing": Verification.FOUND}
    assert port.asked == [
        ReadBackRequest(
            run_id="run-1",
            target="books",
            surface="filing",
            tool="books.find_filing",
            principal_id="alex",
        )
    ]


def test_a_read_back_with_nobody_to_read_as_is_refused() -> None:
    """Delete this and an empty principal reaches the gate, which is a request made as nobody."""
    with pytest.raises(VerificationError, match="nobody to read as"):
        read_back(
            (CHECK,), _Port(Verification.FOUND), run_id="run-1", target="books", principal_id=" "
        )


def test_a_write_the_system_of_record_does_not_have_fails_a_run_both_passes_met() -> None:
    """The case M19.5.5 exists for: the page said done and the return is not there.

    Delete this and the read-back can be advisory, reported beside a passing verdict."""
    for looked in (Verification.ABSENT, Verification.INCONCLUSIVE):
        verdict = verify_run(
            one_criterion(),
            trajectory(),
            actions_only={"landed_filing": Outcome.MET},
            with_frames={"landed_filing": Outcome.MET},
            admitted=AdmittedFrames(run_id="run-1", frames=(frame(1),)),
            checks=(CHECK,),
            read_backs={"landed_filing": looked},
        )
        assert not verdict.passed
        assert verdict.confirmed == ()


def test_a_possible_read_back_that_was_never_asked_fails_the_criterion() -> None:
    """A missing answer is not a found record. Delete this and skipping the call confirms it."""
    verdict = verify_run(
        one_criterion(),
        trajectory(),
        actions_only={"landed_filing": Outcome.MET},
        with_frames={"landed_filing": Outcome.MET},
        admitted=AdmittedFrames(run_id="run-1", frames=(frame(1),)),
        checks=(CHECK,),
        read_backs={},
    )

    assert not verdict.passed


def test_a_read_back_answer_for_a_check_that_was_not_possible_is_refused() -> None:
    """Delete this and a caller can confirm a write through a tool the declaration did not name."""
    with pytest.raises(VerificationError, match="no possible check"):
        verify_run(
            one_criterion(),
            trajectory(),
            actions_only={"landed_filing": Outcome.MET},
            with_frames={"landed_filing": Outcome.MET},
            admitted=AdmittedFrames(run_id="run-1", frames=(frame(1),)),
            checks=(
                ReadBackCheck(
                    surface="filing", criterion="landed_filing", why_not=NOTHING_DECLARED
                ),
            ),
            read_backs={"landed_filing": Verification.FOUND},
        )


def test_a_confirmed_write_is_listed_as_confirmed() -> None:
    """Delete this and `confirmed` can stay empty for ever while every run passes."""
    verdict = verify_run(
        one_criterion(),
        trajectory(),
        actions_only={"landed_filing": Outcome.MET},
        with_frames={"landed_filing": Outcome.MET},
        admitted=AdmittedFrames(run_id="run-1", frames=(frame(1),)),
        checks=(CHECK,),
        read_backs={"landed_filing": Verification.FOUND},
    )

    assert verdict.passed
    assert verdict.confirmed == ("landed_filing",)
    assert verdict.unconfirmed == ()


def test_a_check_naming_both_a_tool_and_a_reason_or_neither_is_refused() -> None:
    """Delete this and a check can be possible and impossible at once, and read as either."""
    with pytest.raises(VerificationError):
        ReadBackCheck(surface="filing", criterion="landed_filing")
    with pytest.raises(VerificationError):
        ReadBackCheck(surface="filing", criterion="landed_filing", tool="x.y", why_not="no")


# ------------------------------------------------------------------ the declaration and the rubric
def test_a_write_surface_gets_a_landed_criterion_written_from_the_declaration() -> None:
    """The criterion a read-back confirms exists before the run, like every other criterion.

    Delete this and a rubric for a filing has nothing a read-back could confirm, so every write
    passes on the page's word."""
    rubric = build_rubric(request(), target(), now=NOW)

    assert landed_criterion("filing") in {one.name for one in rubric.required()}


def test_a_read_back_declared_on_a_surface_that_writes_nothing_is_refused() -> None:
    """Delete this and a read-only surface can declare a read-back that reads as a confirmation."""
    with pytest.raises(TargetError, match="no write"):
        Surface(
            name="invoices",
            origin=ORIGIN,
            path="/invoices",
            verbs=frozenset({Verb.OPEN, Verb.READ}),
            capability=WRITE,
            reads=("total",),
            read_back="books.find_invoice",
        )


def test_a_read_back_tool_name_with_spaces_is_refused() -> None:
    """Delete this and ` books.find_filing` is never registered and is refused as not registered,
    which sends somebody to install a connector that is already there."""
    with pytest.raises(TargetError, match="with spaces"):
        target(" books.find_filing")


def test_the_grading_module_no_longer_reports_the_two_leaves_as_unbuilt() -> None:
    """Delete this and the old sentence can come back, telling the next reader that M19.5.2 is in
    conflict with M19.4.5 after the conflict was resolved and built."""
    gaps = verification_gaps()

    assert not any("M19.5.2" in one for one in gaps)
    assert any("no judge is built" in one for one in gaps)


def test_a_frame_names_a_stored_picture_by_digest() -> None:
    """Delete this and a frame with an empty digest reaches the judge, who is then shown whatever
    the recording returns for an empty key."""
    from brain.browsing.observation import ObservationError

    with pytest.raises(ObservationError, match="names no stored picture"):
        Frame(run_id="run-1", sequence=1, origin=ORIGIN, digest="", inputs_masked=True)


def test_the_entity_used_for_the_fixture_is_a_real_entity() -> None:
    """Guards the fixture rather than the module: `SurfaceReading` must stay an `Entity`, or the
    registry above refuses and every read-back test fails for a reason unrelated to read-backs."""
    assert issubclass(SurfaceReading, Entity)
