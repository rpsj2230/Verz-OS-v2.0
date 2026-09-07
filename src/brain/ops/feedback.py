"""A department lead saying an answer was wrong, and what may travel out of that.

Two acts and one module, because the second is only safe if the first was. A lead flags an
answer from the console; one click turns that flag into a regression case that runs for ever.
The click is the feature and it is also the hazard, and everything below is arranged around
the hazard rather than around the click.

**A regression test captured from a real answer is a permanent data disclosure created by a
usability feature.** That sentence is the whole module. A captured case is committed, so it
lands in the repository, in every developer's checkout, in every CI log and in every fork of
the branch, held under permissions belonging to nobody. If the case carries what the answer
said, then whatever the asker was entitled to see is now readable by people who were never
entitled to it, for as long as the repository exists, and no revocation reaches it. So the
capture carries the question, the asker's **capability shape** and the expected **shape** of
the answer, and the rows come from the synthetic company rather than from the run. See
`A_CAPTURED_CASE_HAS_NO_MUST_CONTAIN_BECAUSE_IT_WOULD_BE_FILLED_FROM_PRODUCTION`.

**The corpus in `tests/fixtures/golden.py` has `must_contain=("14 Nov 2026", "12")` and a
captured case must not have that field at all.** The two look like the same idea and are
opposites. A person wrote those literals about a synthetic company they invented; a capture
would fill the same field from whatever production returned. A field that is safe when a
human types it and unsafe when a machine fills it is a field that does not survive being
automated, and the answer is to delete the field rather than to write a rule about who may
fill it. `CapturedCase` therefore holds field *names* and no values, and the names are
validated by constructing the capability that would be needed to read them, so the grammar
is `brain.core.entitlement.CAPABILITY_RE` and not a fourth copy of a name pattern.

**A flag is a pointer and never a second copy of the answer.** `brain.gate.compose`
argues that a `trace_ref` is quotable and grants nothing: knowing a reference identifies
which trace, and entitlement decides who may open it. So a flag carries the reference and
the question id and stops there. A flag carrying the answer text would be a second copy of
that answer sitting in a new store under the *flagger's* permissions rather than the
asker's, which is a re-grant nobody performed, and it would outlive the trace's own window.
See `A_FLAG_IS_A_POINTER_AND_NEVER_A_SECOND_COPY_OF_THE_ANSWER`.

**There is no free-text field anywhere here, and that is the load-bearing absence.** The
obvious design gives the lead a box to say what was wrong. That box is where somebody pastes
the answer, because pasting the answer is the most helpful thing they can do and nothing
tells them not to. So the reason is a closed vocabulary, `FlagReason`, whose members name
shapes of wrongness and can hold nothing. An annotator or a lead who needs to say more than
the vocabulary allows is telling us the vocabulary is short by a member, which is a decision
somebody makes in a commit. See `A_FREE_TEXT_NOTE_IS_WHERE_THE_ANSWER_GETS_PASTED`.

**Who may flag: a lead may flag an answer given in a department they already reach, and the
check is the ordinary intersection.** Flagging an answer given to somebody in another
department would tell the lead that the answer existed and roughly what it was about, which
is the existence plane of a department they hold nothing in. The check builds the grant that
flagging one department's answers requires, narrows it by what the flagger holds, and asks
whether the result still admits that department. That is `brain.ops.denial_alerts.reach`'s
shape, deliberately, and it calls `EntitlementSet.intersect` rather than comparing scopes by
hand: there are exactly two implementations of the platform's central rule and a third is
forbidden. Requirement-first, for the reason `denial_alerts` gives about `Capability.covers`
expanding only a trailing wildcard.

**Nothing here writes anything and nothing here moves a bar.** `capture` returns a case and
a caller commits it, which is `brain.ops.evaluation`'s
`A_HARNESS_THAT_RECORDS_ITS_OWN_BASELINE_RATCHETS_DOWNWARDS` applied one step earlier. It
matters more than it looks: a captured case is captured *because it failed*, so adding it
lowers the quality share, and the baseline comparison in `score` will refuse the run. That
is the ratchet working in the direction people find inconvenient, and it is correct. The
only legitimate way to record the lower figure is `accept_baseline`, which refuses a failing
run, so a red case cannot be smuggled in by a harness that re-records its own baseline. A
lead clicking a button therefore cannot turn the build red on their own: somebody has to
commit the case, and that commit has their name on it.

Rejected: storing the answer text on the flag so a reviewer can see what was complained
about. It is the single most useful field and it is the one that turns a quality workflow
into a disclosure store. A reviewer entitled to the answer can open the trace by reference;
one who is not, must not read it here.

Rejected: making the flag itself the regression case, in one step. Capture needs the
question text, which the flag deliberately does not hold, so the resolution is a separate
act by a caller who has to go and fetch it. Keeping them apart is what lets `capture` have
no parameter an answer could arrive through: the source holds nothing and the destination
has nowhere to put it, which is two independent reasons rather than one.

Rejected: carrying the asker's `EntitlementSet` on the case so the failure reproduces
exactly. A set carries the principal id and every scope value, so the case would be a
permanent committed record of what one named employee could see in which department. The
shape is capabilities only, and the price is stated where it is paid, in
`capability_shape`.

Rejected: a `read:` capability for flagging. Flagging writes a row, and a lead who may read
a department's answers is not thereby somebody who may file quality findings about them.
`FLAG_CAPABILITY` is a write, scoped like every other grant.

**Nothing calls this yet and saying so is part of claiming the leaf.** There is no route,
no console control and no store: `brain.api_routes.answer` returns a stream and does not
offer the `trace_ref` back as anything a lead can act on, and there is no flag table for
`flag_answer`'s return value to be written to. What has to exist is a route beside
`answer` that takes a trace reference, a question id, a department and a `FlagReason`,
calls `flag_answer` with the caller's own `asked.reach`, and persists the `Flag`; and a
second that calls `capture` and writes the case where a developer commits it. This module
is the decision half of both, which is the half that can be built and mutated before a
table exists. It is the repository's recurring defect, recorded rather than hidden: see
`brain.gate.answer`, which counted thirteen instances of it on the day it was written.

Scope: this module opens no connection and reads no clock. `now` is a parameter everywhere,
the same split `brain.ops.limits`, `brain.ops.canaries` and `brain.ops.evaluation` make.

Task ids: M28.3.1, M28.3.2
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, assert_never

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.gate.compose import TRACE_REF_BYTES
from brain.ops.evaluation import CaseResult, Severity
from brain.ops.tracing import TraceRecord, retention_for


class FeedbackError(Exception):
    """Raised when a flag may not be filed, or a case may not be captured from one.

    An authoring-time refusal, like `brain.core.department.DepartmentError`. It never
    reaches somebody who asked a question: by the time anything here runs, the answer has
    already been given and read.
    """


# ------------------------------------------------------------------ written-down reasons
#: Why a flag records a reference and never the text it is about.
A_FLAG_IS_A_POINTER_AND_NEVER_A_SECOND_COPY_OF_THE_ANSWER = (
    "An answer was composed at the asker's reach and redacted against it. A flag holding "
    "that text would be the same content in a new store, reachable by whoever may read "
    "flags, which is a re-grant nobody performed and which outlives the trace's own "
    "retention window. `brain.gate.compose.ComposedAnswer` says a trace reference is "
    "quotable and grants nothing, so the reference is what travels: it says which answer "
    "without saying what the answer was, and entitlement still decides who may open it."
)

#: Why there is no box for the lead to type what was wrong.
A_FREE_TEXT_NOTE_IS_WHERE_THE_ANSWER_GETS_PASTED = (
    "A free-text field on a flag is the most helpful thing in the form and the only one "
    "that can hold anything. The lead who pastes the answer into it is being thorough, and "
    "nothing in the interface tells them they have just copied a restricted value into a "
    "store with different permissions. So the vocabulary is closed. Being short by a "
    "member is a complaint somebody can act on; a free-text store cannot be un-filled."
)

#: Why a lead may only flag inside a department their own grants already admit.
A_LEAD_MAY_ONLY_FLAG_INSIDE_THE_DEPARTMENT_THEY_ALREADY_REACH = (
    "A flag names a department and a question id, so being able to file one against "
    "another department's answer discloses that the answer existed and what it was about. "
    "That is the existence plane of a department the lead holds nothing in. The rule is "
    "the ordinary one and the check is the ordinary intersection: build the grant that "
    "flagging this department requires, narrow it by what the flagger holds, and ask "
    "whether the result still admits the department."
)

#: Why a captured case holds field names and has nowhere to put a value.
A_CAPTURED_CASE_HAS_NO_MUST_CONTAIN_BECAUSE_IT_WOULD_BE_FILLED_FROM_PRODUCTION = (
    "`tests/fixtures/golden.py` carries `must_contain=('14 Nov 2026', '12')` and is right "
    "to: a person wrote those literals about a synthetic company. The identical field on a "
    "captured case would be filled from whatever production returned, and the case is then "
    "committed, cloned and printed in CI for ever. A field that is safe when a human types "
    "it and unsafe when a machine fills it does not survive automation, so it is absent "
    "rather than governed. What is carried is the field name, which is what "
    "`brain.ops.canaries` carries for the same reason."
)

#: Why a case cannot be captured from a flag whose trace has aged out.
A_CASE_CAPTURED_AFTER_THE_TRACE_EXPIRED_IS_BUILT_FROM_MEMORY = (
    "A captured case asserts what should have happened. Checking that assertion against "
    "what did happen means opening the trace, and a trace outside its retention window is "
    "gone. A case captured after that is somebody's recollection of an answer they read "
    "last month, committed as a permanent test, and it will be wrong in the direction "
    "that makes it look reasonable. So the flag expires when the thing it points at does."
)

#: What a lead must hold, in the department the answer was given in, to flag it.
#:
#: A write rather than a read. Filing a quality finding creates a row and a piece of work
#: for somebody; being able to read a department's answers does not by itself make somebody
#: a person who may say they were wrong. The noun is the row being written, so the grammar
#: in `brain.core.entitlement` is the one that checks it.
FLAG_CAPABILITY: Final = Capability(value="write:answer_flag")

#: The principal id on the requirement set, which belongs to nobody.
#:
#: `requirement_to_flag` builds an entitlement set describing what flagging one department
#: requires, and that set is not a person's. Named rather than left blank because an empty
#: principal id in a trace reads as a bug in whoever built it.
FLAG_REQUIREMENT: Final[str] = "flag_requirement"

#: How long a flag is worth keeping, in days. Derived, not chosen.
#:
#: A flag is a pointer to a trace and holds nothing else of substance, so it is worth
#: exactly as long as the thing it points at. Taken from `brain.ops.tracing.RETENTION`,
#: which is where the trace window is declared, rather than restated here: a second copy of
#: "thirty days" drifts, and it drifts upwards, because the copy nobody looks at is the one
#: that gets raised. `brain.ops.retention.TRACE_RETENTION_DAYS` derives the same number from
#: the same declaration for the same reason.
FLAG_RETENTION_DAYS: Final[int] = retention_for(TraceRecord.TRACE).days

#: The longest a reference may be, in characters, and the shapes it may not contain.
#:
#: Four times the length of what `brain.gate.compose.new_trace_ref` mints, which is
#: `secrets.token_urlsafe(TRACE_REF_BYTES)` and sixteen characters of URL-safe alphabet.
#: Derived rather than written down as 64, so a reference format widened by whoever owns it
#: moves this with it instead of meeting a literal nobody remembered was here. Generous
#: rather than exact on purpose, because the cap is not the check: what refuses a pasted
#: sentence is the whitespace rule beside it, and what refuses a value in a field name is
#: `_readable_name`. This stops the one shape both of those admit, a long unbroken token,
#: and a field validated only for non-emptiness is a field a paragraph fits in.
REFERENCE_MAX_LENGTH: Final[int] = 4 * (TRACE_REF_BYTES * 4 // 3)


class FlagReason(enum.StrEnum):
    """What a lead says was wrong. A closed vocabulary, and the closure is the point.

    Five members, each naming a shape of wrongness that can be judged by reading the answer
    against the question. None of them can carry a value, which is the whole of
    `A_FREE_TEXT_NOTE_IS_WHERE_THE_ANSWER_GETS_PASTED`.

    Two of them are permission outcomes and three are quality outcomes, and `severity_of`
    is the only place that mapping is written. Which one a member is does not follow from
    how bad it sounds: `REFUSED_WRONGLY` reads like a minor annoyance and is a permission
    failure, because `brain.ops.evaluation.Severity.PERMISSION` covers an answer that
    refused something the asker may see just as much as one that showed what they may not.
    """

    #: The answer stated something that is not so.
    WRONG_FACT = "wrong_fact"
    #: The answer left out something the asker was entitled to and had asked for.
    INCOMPLETE = "incomplete"
    #: The answer was right when the data was fetched and is not right now.
    STALE = "stale"
    #: The answer showed the asker something they may not see.
    SHOULD_HAVE_REFUSED = "should_have_refused"
    #: The asker was refused something they may see.
    REFUSED_WRONGLY = "refused_wrongly"


class Expectation(enum.StrEnum):
    """What shape a captured case says the answer should have had.

    The same three outcomes `tests.fixtures.golden.Expect` names, **member for member and
    value for value**, stated here rather than imported because `src` importing from
    `tests` would be a package that cannot be installed without its own test suite. That is
    `brain.ops.canaries`'s split and this is the same side of it.

    Spelled identically rather than nearly, which is the correction worth having: two enums
    meaning one thing and reading `ANSWERS` here against `ANSWER` there is a correspondence
    no test can assert, so nothing would notice the day a fourth outcome was added to one of
    them. Spelled the same, the drift is one assertion, and it is
    `test_the_two_names_for_one_outcome_cannot_drift_apart`.

    Never stored on a case. `CapturedCase.expectation` computes it from the two field
    tuples, so the shape and the fields cannot disagree: two fields that must agree are two
    things that disagree silently, in whichever direction the caller happened to write.
    """

    #: Fields came back and none were withheld.
    ANSWER = "answer"
    #: The record came back with named fields locked.
    PARTIAL = "partial"
    #: Nothing came back, phrased exactly as a genuine absence is phrased.
    REFUSE = "refuse"


def _readable_name(name: str, *, what: str) -> str:
    """Check that `name` is a field name and not a value, by the only grammar there is.

    A field name is the thing `read:<name>` would be a capability for, so the check is to
    build that capability and let `brain.core.entitlement.CAPABILITY_RE` refuse it. Nothing
    new is invented: a fourth name pattern in this repository would be a fourth chance for
    one of them to be looser than the rest, which is the mistake `brain.ops.sweeps` records
    about the tool-name grammar it used to restate.

    It refuses uppercase, spaces, hyphens and anything that does not start with a letter,
    so `CANARY-CONTRACT-7Q4XZ`, `14 Nov 2026` and `48000` cannot be spelled as one. It is a
    strong filter and not a proof: a lowercase dotted pair is admitted whatever it means.
    The proof is structural and sits in `CapturedCase`, which has no field a value belongs
    in; this stops the fields that do exist from being used as one.
    """
    try:
        Capability(value=f"read:{name}")
    except ValueError as exc:
        msg = f"{what} {name!r} is not a field name; a captured case carries names, never values"
        raise FeedbackError(msg) from exc
    return name


def _reference(value: str, *, what: str) -> str:
    """Check that a value is an identifier rather than something somebody pasted."""
    if not value:
        msg = f"a flag with no {what} points at nothing anybody can look up"
        raise FeedbackError(msg)
    if len(value) > REFERENCE_MAX_LENGTH or any(one.isspace() for one in value):
        msg = (
            f"{what} {value[:20]!r} is not a reference. A reference is one token; "
            "something with whitespace in it is a sentence, and a sentence here is text "
            "from an answer arriving through a field that was meant to hold a pointer."
        )
        raise FeedbackError(msg)
    return value


@dataclass(frozen=True)
class Flag:
    """One department lead saying one answer was wrong.

    Six fields and no seventh. There is no `answer`, no `note`, no `excerpt` and no
    `expected_answer`, and each of those absences is the same absence: a place text from an
    answer could arrive. Adding one is an edit to a frozen dataclass in a module whose
    docstring argues against it, which is a decision somebody makes rather than a line they
    add, and it is the structural half of `CanaryFinding`'s trick in `brain.ops.canaries`.

    `department` is the department the answer was *given in*, not the flagger's own. They
    are usually the same and the check does not assume it: a company-wide quality steward
    holding the capability unrestricted may flag in any department, and a lead holding it in
    one may not flag in another.
    """

    #: Which answer, by `brain.gate.compose.ComposedAnswer.trace_ref`. Quotable, grants
    #: nothing, and the only route back to what was actually said.
    trace_ref: str
    #: Which question, by its id. An id, so it names the run without repeating it.
    question_id: str
    #: The department the answer was given in. What the reach check is about.
    department: str
    #: The principal who filed it.
    flagged_by: str
    #: What they said was wrong, from the closed vocabulary.
    reason: FlagReason
    #: When it was filed. Compared against `FLAG_RETENTION_DAYS`, never against a clock
    #: this module reads.
    at: datetime

    def __post_init__(self) -> None:
        _reference(self.trace_ref, what="trace reference")
        _reference(self.question_id, what="question id")
        for name in ("department", "flagged_by"):
            if not getattr(self, name):
                msg = f"a flag with no {name} cannot be checked against anybody's reach"
                raise FeedbackError(msg)

    def severity(self) -> Severity:
        """How `brain.ops.evaluation` would score what this lead said went wrong."""
        return severity_of(self.reason)


def severity_of(reason: FlagReason) -> Severity:
    """Which of `brain.ops.evaluation`'s two classes a reason falls in.

    Written once, here, and `assert_never` makes a sixth `FlagReason` a type error rather
    than something that silently acquires whichever class a dictionary default carried.
    Every default in a mapping like this is the lenient one, because the lenient one is
    what makes the build pass on the afternoon somebody adds a member.

    A permission outcome is not the same as a severe-sounding one. `REFUSED_WRONGLY` is a
    person being unable to do their job, which sounds like a quality complaint, and it is a
    permission failure by `Severity.PERMISSION`'s own definition: the answer refused
    something the asker may see. It therefore has a threshold of zero and no percentage
    anywhere near it, which is right, because a system that refuses the wrong people is
    failing at the one thing it exists to get right in the other direction.
    """
    match reason:
        case FlagReason.SHOULD_HAVE_REFUSED | FlagReason.REFUSED_WRONGLY:
            return Severity.PERMISSION
        case FlagReason.WRONG_FACT | FlagReason.INCOMPLETE | FlagReason.STALE:
            return Severity.QUALITY
        case _:
            assert_never(reason)


# ------------------------------------------------------------------------------ the reach
def requirement_to_flag(department: str) -> EntitlementSet:
    """What somebody must hold before they may flag an answer given in this department.

    One grant, expressed as an `EntitlementSet` rather than as a capability beside a scope,
    so that `may_flag` can narrow it with the ordinary intersection instead of comparing
    scopes by hand. `brain.ops.denial_alerts.requirement` is the same construction for the
    same reason and this is deliberately shaped like it.

    The scope is built from the department rather than carried alongside it. Two fields
    would be two things that can disagree, and the disagreement is silent in whichever
    direction the caller happened to write.
    """
    if not department:
        msg = "a flag requirement with no department admits every department"
        raise FeedbackError(msg)
    return EntitlementSet(
        principal_id=FLAG_REQUIREMENT,
        grants=(
            Grant(
                capability=FLAG_CAPABILITY,
                scope=Scope(clauses=(Clause(field="department", op=Op.EQ, value=department),)),
            ),
        ),
    )


def may_flag(department: str, flagger: EntitlementSet, *, now: datetime) -> Scope | None:
    """The scope in which this flagger may file against this department, or None.

    Not a bool, for `brain.ops.denial_alerts.reach`'s reason: a bool is a verdict with no
    name, and the scope is what lets a console show *which* departments a lead may flag in
    rather than only that they may flag this one.

    The intersection runs requirement-first, which is `denial_alerts.reach`'s direction:
    `EntitlementSet.intersect` keeps a grant of the receiver's only where the ceiling covers
    it, and `Capability.covers` expands only a trailing wildcard, so narrowing the
    *recipient* by a specific capability drops the wildcard grant of somebody who plainly
    holds it.

    **Here that direction is inherited discipline and not a live guard, which a mutation run
    on 2026-09-07 showed rather than assumed.** Reversing it to `flagger.intersect(...)`
    passed every test in `tests/unit/test_feedback.py`, and the reason is that the two are
    equivalent for this requirement: `FLAG_CAPABILITY` is `write:answer_flag`, and no
    capability the grammar admits covers it except itself. `write:answer_flag.*` does not,
    because `covers` asks whether `write:answer_flag` starts with `write:answer_flag.`, and
    `write:*` is not a capability. So both directions select the same flagger grants, both
    conjoin the same scopes, and `not_after` is the minimum of the same pair. The survivor is
    recorded rather than papered over with a test written to fit it.

    It stops being equivalent the moment `FLAG_CAPABILITY` becomes field-shaped, which is
    what `denial_alerts` deals with every time it runs, because a denial pattern's capability
    is a column. Written this way round so that change is safe when somebody makes it.

    Three existing pieces and no fourth rule. `intersect` decides what narrower means,
    `scope_for` decides what holding it means and refuses an expired principal, which is
    where a lead who left last week stops being able to flag, and `Scope.matches` decides
    whether what survived still admits the department.
    """
    shared = requirement_to_flag(department).intersect(flagger)
    scope = shared.scope_for(FLAG_CAPABILITY, now)
    if scope is None or not scope.matches({"department": department}):
        return None
    return scope


def flag_answer(
    *,
    trace_ref: str,
    question_id: str,
    department: str,
    flagger: EntitlementSet,
    reason: FlagReason,
    now: datetime,
) -> Flag:
    """File a flag, or refuse.

    Takes the flagger's whole entitlement set rather than a principal id beside a claim
    about what they hold, because the set already knows whose it is and a second field is a
    second place for the two to disagree about which person's reach is being evaluated.
    That is `brain.ops.denial_alerts.digest`'s argument about its recipients.

    The refusal says the department and not what is in it. A lead who may not flag in
    finance is told they may not flag in finance, which they can work out from their own
    grants, and is told nothing about whether the question id they typed names anything.
    """
    if may_flag(department, flagger, now=now) is None:
        msg = (
            f"{flagger.principal_id} does not hold {FLAG_CAPABILITY.value} in {department}, "
            "so this flag is not theirs to file"
        )
        raise FeedbackError(msg)
    return Flag(
        trace_ref=trace_ref,
        question_id=question_id,
        department=department,
        flagged_by=flagger.principal_id,
        reason=reason,
        at=now,
    )


def expired(one: Flag, *, now: datetime, retention_days: int = FLAG_RETENTION_DAYS) -> bool:
    """Whether the trace this flag points at has aged out from under it.

    The window is a parameter defaulting to the derived one, for the reason
    `brain.ops.tracing.retention_gaps` takes one: a check that can only ever run against
    the constant beside it cannot be shown to fail, and a check nobody has seen fail is a
    check nobody has evidence about.
    """
    return now - one.at >= timedelta(days=retention_days)


# ------------------------------------------------------------------------- the capture
def capability_shape(entitlement: EntitlementSet) -> tuple[Capability, ...]:
    """The asker's reach reduced to what may be committed: capabilities, sorted, deduped.

    **Everything that identifies a person or a place is dropped here and that is the
    function's whole purpose.** The principal id goes, because a captured case naming an
    employee is a permanent committed record of what that employee could see. Every scope
    goes, because a scope holds values: `department=finance`, `partner_visible=true`, and
    in a real installation whatever clauses a real grant was written with.

    **The price is stated where it is paid.** A case built from this shape reproduces a
    field-level permission failure and cannot reproduce a scope-level one. The corpus's
    sharpest pair is `G04a` and `G04b`: one person, `u_dual`, asked about contract value in
    two departments, answered in sales and refused in web. What separates them is the scope
    on a single `read:client.contract_value` grant, which is the part this function drops,
    so the shape it returns is the same tuple for both and cannot say which of the two a
    case reproduces. What closes that gap is `CapturedCase.mocked_from`, which
    names a fixture in the synthetic company that supplies both the rows and the scopes, so
    the scope-shaped half of the case is rebuilt from synthetic values rather than carried
    from real ones.
    """
    return tuple(sorted({g.capability for g in entitlement.grants}, key=lambda c: c.value))


@dataclass(frozen=True)
class CapturedCase:
    """A flagged answer turned into something that can run for ever, carrying no value.

    **Eight fields, and the interesting ones are the ones that are missing.** There is no
    `answer`, no `must_contain`, no `rows`, no `records`, no `expected_text` and no
    `entitlement`. A value fetched from a business system has nowhere to arrive: the two
    field tuples are checked against the capability grammar, `held` is a tuple of
    `Capability` objects which that grammar has already refused to let hold anything else,
    `mocked_from` is a fixture name and `fault` is an enum member.

    `question` is the exception and it is an honest one. It is carried verbatim because a
    paraphrased question does not reproduce the failure, and it is the asker's own words
    rather than anything the system returned. A question can still name its subject: "what
    is SNM's contract worth" contains a client name. What is eliminated here is everything
    the *system* disclosed; what remains is what the person typed, and there is no version
    of this feature that reproduces a bug without it.
    """

    #: The asker's own words. See the class docstring for the residue this carries.
    question: str
    #: The asker's reach with the person and the places taken out of it.
    held: tuple[Capability, ...]
    #: Field names the answer should have carried. Names, never values.
    answering_fields: tuple[str, ...]
    #: Field names that should have come back locked rather than absent.
    locked_fields: tuple[str, ...]
    #: The synthetic fixture that supplies this case's rows and scopes.
    mocked_from: str
    #: What the lead said was wrong, which decides how the case is scored.
    fault: FlagReason
    #: The flag this came from, so an auditor with the entitlement can open the trace.
    origin_trace_ref: str
    #: The question id the flag named, which is what `CaseResult` is keyed on.
    origin_question_id: str

    def __post_init__(self) -> None:
        if not self.question.strip():
            msg = "a captured case with no question reproduces nothing"
            raise FeedbackError(msg)
        for name in self.answering_fields:
            _readable_name(name, what="answering field")
        for name in self.locked_fields:
            _readable_name(name, what="locked field")
        # A fixture name and not a field name, so it carries no dot: `client.name` here
        # would read as a column and would silently make the mock resolve to nothing.
        _readable_name(self.mocked_from, what="mock source")
        if "." in self.mocked_from:
            msg = (
                f"mock source {self.mocked_from!r} names a field; it must name a fixture in "
                "the synthetic company, which is where this case's rows come from"
            )
            raise FeedbackError(msg)
        _reference(self.origin_trace_ref, what="trace reference")
        _reference(self.origin_question_id, what="question id")
        if self.locked_fields and not self.answering_fields:
            # A case expecting a refusal that also claims fields came back locked. The
            # asker cannot tell those two apart, by construction: `brain.gate.answer`
            # renders a withheld field and an absent record through one constant referenced
            # twice. A case asserting a difference the system does not expose is a case
            # that can only ever be satisfied by breaking that.
            msg = (
                "a case with locked fields and no answering fields expects a refusal that "
                "is distinguishable from an absence, which is the one thing that must not be"
            )
            raise FeedbackError(msg)

    @property
    def expectation(self) -> Expectation:
        """What shape this case says the answer should have had, computed not stored."""
        if not self.answering_fields:
            return Expectation.REFUSE
        if self.locked_fields:
            return Expectation.PARTIAL
        return Expectation.ANSWER

    def severity(self) -> Severity:
        """How a run of this case is scored, from what a person judged rather than guessed.

        The same mapping a flag uses, because the fault came off a flag and a second
        mapping here would be a second answer to one question.
        """
        return severity_of(self.fault)


def capture(
    one: Flag,
    *,
    question: str,
    asked_with: EntitlementSet,
    answering_fields: Iterable[str] = (),
    locked_fields: Iterable[str] = (),
    mocked_from: str,
    now: datetime,
) -> CapturedCase:
    """Turn a flag into a permanent regression case. The one click, and what it may carry.

    **There is no parameter an answer can arrive through**, which is the structural claim
    this function exists to make. `question` is the asker's words, `asked_with` is reduced
    by `capability_shape` before anything is stored, the two field arguments are names
    checked against the capability grammar, and `mocked_from` names a fixture. A caller
    holding the answer text has nowhere to put it.

    `asked_with` is taken whole and narrowed here rather than being taken pre-narrowed,
    deliberately. A signature accepting a ready-made tuple of capabilities would let a
    caller assemble one, and the assembling is the step that has to be trusted. This way
    the reduction happens on the far side of the boundary and there is one implementation
    of it.

    Refuses a flag whose trace has aged out. See
    `A_CASE_CAPTURED_AFTER_THE_TRACE_EXPIRED_IS_BUILT_FROM_MEMORY`.

    Returns rather than writes. A captured case is a red test the day it is captured, so
    committing it lowers the quality share and `score` refuses the run against its
    baseline, which is `brain.ops.evaluation`'s ratchet working in the direction people
    find inconvenient. Somebody has to make that commit, and it has their name on it.
    """
    if expired(one, now=now):
        msg = (
            f"the trace behind {one.question_id} is older than {FLAG_RETENTION_DAYS} days, "
            "so there is nothing left to check a captured case against"
        )
        raise FeedbackError(msg)
    return CapturedCase(
        question=question,
        held=capability_shape(asked_with),
        answering_fields=tuple(answering_fields),
        locked_fields=tuple(locked_fields),
        mocked_from=mocked_from,
        fault=one.reason,
        origin_trace_ref=one.trace_ref,
        origin_question_id=one.question_id,
    )


def case_result_for(case: CapturedCase, *, passed: bool, detail: str = "") -> CaseResult:
    """What a run of this captured case hands to `brain.ops.evaluation.score`.

    The severity comes from what the lead said was wrong and never from the question's
    wording, which is the mistake `tests.fixtures.golden` warns about in its own docstring:
    "how many hours are left" and "how many clients are worth over 50k" read alike and are
    entirely different questions about permission. A person judged this one; nothing here
    guesses.

    `detail` is the harness saying which expectation was not met, and it is a parameter
    rather than something built from the answer for the reason everything else here is
    shaped that way. A default sentence is supplied when the caller offers none, because
    `CaseResult` refuses a failure that says why nowhere.
    """
    return CaseResult(
        question_id=case.origin_question_id,
        severity=case.severity(),
        passed=passed,
        reason=""
        if passed
        else (detail or f"the answer's shape was not {case.expectation.value!r}"),
    )
