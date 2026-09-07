"""A flag that points at an answer, and a captured case that cannot carry one.

Every test here is about one failure wearing a different coat: a quality workflow becoming a
disclosure store. A flag that copied the answer, a captured case with a field a fetched value
fits in, a lead who can file against a department they hold nothing in, or a case captured
from a trace nobody can still open. Each is helpful, each is what somebody would build if the
hazard were not written down, and each is checked here rather than argued about.

The positive siblings matter as much. A reach check tested only by its refusals is satisfied
by one that refuses every flag, and a validator tested only on canary tokens is satisfied by
one that refuses every field name, so each guard below has a test proving the thing still
works.

Task ids: M28.3.1, M28.3.2
"""

from __future__ import annotations

import ast
import inspect
from dataclasses import fields as dataclass_fields
from datetime import UTC, datetime, timedelta

import pytest

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Clause, Op, Scope
from brain.gate.compose import new_trace_ref
from brain.ops import feedback
from brain.ops.evaluation import Severity, accept_baseline, score
from brain.ops.feedback import (
    FLAG_CAPABILITY,
    FLAG_RETENTION_DAYS,
    REFERENCE_MAX_LENGTH,
    CapturedCase,
    Expectation,
    FeedbackError,
    Flag,
    FlagReason,
    capability_shape,
    capture,
    case_result_for,
    expired,
    flag_answer,
    may_flag,
    requirement_to_flag,
    severity_of,
)
from brain.ops.tracing import TraceRecord, retention_for
from tests.fixtures.company import NOW, canary_tokens, person
from tests.fixtures.golden import GOLDEN, Expect

#: A reference of the shape the system actually mints, so nothing here invents a format.
REF = new_trace_ref()

#: Far enough apart that a grant live at one is expired at the other, and both far enough
#: from any real clock that this does not become a dated test. The shape
#: `test_denial_alerts` uses for the same reason.
BEFORE_EXPIRY = datetime(2098, 1, 1, tzinfo=UTC)
AT_EXPIRY = datetime(2099, 1, 1, tzinfo=UTC)
AFTER_EXPIRY = datetime(2100, 1, 1, tzinfo=UTC)


def lead(
    pid: str,
    *,
    department: str | None = "maintenance",
    capability: str = FLAG_CAPABILITY.value,
    not_after: datetime | None = None,
) -> EntitlementSet:
    """Somebody holding the flag capability, in one department or company-wide."""
    scope = Scope.unrestricted() if department is None else Scope.department(department)
    return EntitlementSet(
        principal_id=pid,
        grants=(Grant(capability=Capability(value=capability), scope=scope),),
        not_after=not_after,
    )


def a_flag(*, department: str = "maintenance", at: datetime = NOW) -> Flag:
    return Flag(
        trace_ref=REF,
        question_id="G01a",
        department=department,
        flagged_by="u_aaron",
        reason=FlagReason.WRONG_FACT,
        at=at,
    )


# ------------------------------------------------------------------- who may flag


def test_a_department_lead_flags_an_answer_given_in_their_own_department() -> None:
    """**The leaf itself, and the positive case every refusal below is measured against.**

    A reach check tested only by what it refuses is satisfied by one that refuses
    everything, and a console whose flag button never works is indistinguishable from a
    console with no button.

    Delete this and `may_flag` can return None unconditionally with every other reach test
    in this file still green."""
    aaron = lead("u_aaron", department="maintenance")

    filed = flag_answer(
        trace_ref=REF,
        question_id="G01a",
        department="maintenance",
        flagger=aaron,
        reason=FlagReason.WRONG_FACT,
        now=NOW,
    )

    assert filed.flagged_by == "u_aaron"
    assert filed.trace_ref == REF
    assert filed.question_id == "G01a"
    assert filed.at == NOW
    assert filed.reason is FlagReason.WRONG_FACT


def test_a_lead_may_not_flag_an_answer_given_in_a_department_they_do_not_reach() -> None:
    """**Flagging another department's answer discloses that the answer existed and roughly
    what it was about**, which is the existence plane of a department the lead holds nothing
    in. A flag names a department and a question id, so filing one is a read.

    Delete this and the flag surface becomes a way to enumerate which questions other
    departments asked, which is a disclosure created by a quality feature."""
    aaron = lead("u_aaron", department="maintenance")

    assert may_flag("finance", aaron, now=NOW) is None

    with pytest.raises(FeedbackError, match="not theirs to file"):
        flag_answer(
            trace_ref=REF,
            question_id="G09",
            department="finance",
            flagger=aaron,
            reason=FlagReason.SHOULD_HAVE_REFUSED,
            now=NOW,
        )


def test_a_company_wide_steward_may_flag_in_a_department_they_hold_nothing_else_in() -> None:
    """The second positive case, and it is a different branch from the first: an
    unrestricted scope has no clause to match, so this is what proves the check asks whether
    the surviving grant *admits* the department rather than whether it names it.

    Delete this and `may_flag` can be narrowed to an equality test on a department string,
    which refuses the quality steward the whole workflow depends on."""
    steward = lead("u_steward", department=None)

    for department in ("maintenance", "web", "sales", "finance"):
        scope = may_flag(department, steward, now=NOW)
        assert scope is not None, department
        assert scope.matches({"department": department})


def test_holding_the_capability_nowhere_is_not_reduced_to_holding_it_everywhere() -> None:
    """A person with no flag grant at all must be refused, and the interesting half is that
    the refusal comes from the same intersection rather than from a special case: their
    entitlement covers nothing, so the requirement's grant survives nothing.

    `u_rupash` is the Super Admin in the fixture and holds `admin:grant` unrestricted, which
    is as close as this company comes to a bypass. He still cannot flag.

    Delete this and an empty intersection can be read as an unrestricted one, which is the
    direction that fails open."""
    for pid in ("u_rupash", "u_weiling", "u_jason"):
        assert may_flag("maintenance", person(pid).entitlement(), now=NOW) is None


def test_a_lead_whose_access_has_expired_may_no_longer_flag() -> None:
    """Expiry is checked where it is always checked, by passing `now` into `scope_for`, so a
    lead who left last week stops being able to file on the day their access ends rather
    than on the day somebody tidies a list.

    Both halves, because a check that refuses everybody passes the refusal half: the same
    entitlement flags before the boundary and does not after it.

    Delete this and `now` can be dropped from the reach check, at which point a leaver's
    grants keep working for as long as the grant table holds them."""
    leaver = lead("u_leaver", department="maintenance", not_after=AT_EXPIRY)

    assert may_flag("maintenance", leaver, now=BEFORE_EXPIRY) is not None
    assert may_flag("maintenance", leaver, now=AFTER_EXPIRY) is None

    with pytest.raises(FeedbackError):
        flag_answer(
            trace_ref=REF,
            question_id="G01a",
            department="maintenance",
            flagger=leaver,
            reason=FlagReason.STALE,
            now=AFTER_EXPIRY,
        )


def test_a_flag_grant_with_a_clause_the_check_cannot_answer_fails_closed() -> None:
    """A grant scoped on something other than the department, the partner's second clause
    being the fixture's example of one, is refused rather than admitted. The reach check
    knows a department and nothing else, so a clause it cannot evaluate must not be treated
    as satisfied.

    `Scope.matches` is what makes this true: an absent field never satisfies a predicate. The
    test exists because the alternative reading, "ignore clauses about fields we were not
    given", is the one somebody writes when a partner complains they cannot flag.

    Delete this and a second clause on a flag grant becomes decoration."""
    partner = EntitlementSet(
        principal_id="u_partner",
        grants=(
            Grant(
                capability=FLAG_CAPABILITY,
                scope=Scope(
                    clauses=(
                        Clause(field="department", op=Op.EQ, value="sales"),
                        Clause(field="partner_visible", op=Op.EQ, value="true"),
                    )
                ),
            ),
        ),
    )

    assert may_flag("sales", partner, now=NOW) is None


def test_the_reach_check_narrows_through_the_one_intersect_and_not_a_third_copy() -> None:
    """**There are exactly two implementations of the platform's central rule and a third is
    forbidden**, which CLAUDE.md states and which no behavioural test can assert: a hand
    written scope comparison that happens to agree today passes every case above.

    Asserted over the parsed function rather than over its text, because this module's own
    docstring names `intersect` several times and a substring search would be satisfied by
    the argument for the thing rather than the thing.

    Delete this and `may_flag` acquires its own loop over `grants`, which is the copy that is
    subtly wrong and the one that ends up in production."""
    tree = ast.parse(inspect.getsource(may_flag))
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    read = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}

    assert {"intersect", "scope_for", "matches"} <= called
    for forbidden in ("grants", "clauses"):
        assert forbidden not in read, f"may_flag reads {forbidden} and is deciding for itself"


def test_the_requirement_to_flag_names_no_person_and_carries_one_grant() -> None:
    """The requirement is a description of what flagging costs, not a description of
    anybody, so its principal id belongs to nobody and it holds exactly the one grant.

    The scope is built from the department rather than carried beside it: two fields would
    be two things that can disagree, silently, in whichever direction the caller wrote.

    Delete this and the requirement can acquire a second grant, which widens what a flagger
    must hold in a way that reads as tightening."""
    required = requirement_to_flag("maintenance")

    assert required.principal_id != "u_aaron"
    assert len(required.grants) == 1
    assert required.grants[0].capability == FLAG_CAPABILITY
    assert required.grants[0].scope.matches({"department": "maintenance"})
    assert not required.grants[0].scope.matches({"department": "web"})

    with pytest.raises(FeedbackError, match="admits every department"):
        requirement_to_flag("")


def test_flagging_costs_a_write_and_reading_a_department_does_not_buy_it() -> None:
    """A lead who may read a department's answers is not thereby somebody who may file
    quality findings about them. The capability is a write, and `u_aaron`'s wide read grants
    over his own department do not cover it.

    Anchored on the capability's own verb rather than on the string, so renaming the noun
    leaves the property intact and changing the verb does not.

    Delete this and `FLAG_CAPABILITY` can be repointed at `read:client` and every reach test
    above goes on passing, because the fixture's leads hold that."""
    assert FLAG_CAPABILITY.verb == "write"
    assert person("u_aaron").entitlement().holds(FLAG_CAPABILITY, NOW) is False

    reader = lead("u_reader", department="maintenance", capability="read:client.name")
    assert may_flag("maintenance", reader, now=NOW) is None


# ---------------------------------------------------------- what a flag may carry


def test_a_flag_has_nowhere_to_put_the_answer_it_is_about() -> None:
    """**The structural half of "a flag is a pointer and never a second copy".** The prose
    says the answer text must not travel; this says there is no attribute for it to travel
    in, so including it is an edit to a frozen dataclass in a module arguing against it.

    Delete this and `note: str = ""` appears on the model, every other test here passes
    because none of them set it, and the first lead to paste an answer into it has created a
    copy of a restricted value under their own permissions rather than the asker's."""
    names = {f.name for f in dataclass_fields(Flag)}

    assert names == {"trace_ref", "question_id", "department", "flagged_by", "reason", "at"}
    for forbidden in ("answer", "note", "comment", "excerpt", "text", "expected_answer", "body"):
        assert forbidden not in names, f"a flag can carry a {forbidden}"


def test_what_was_wrong_comes_from_a_closed_list_that_can_hold_nothing() -> None:
    """The vocabulary is closed so there is no field a sentence fits in. An annotator or a
    lead who needs to say more than it allows is telling us the list is short by a member,
    which is a decision somebody makes in a commit.

    Asserted by trying to mint a member from free text, which is what a free-text note would
    amount to if the enum were widened to a plain string.

    Delete this and `reason: str` replaces the enum, and the most helpful field in the form
    is the one that can hold an answer."""
    assert {r.value for r in FlagReason} == {
        "wrong_fact",
        "incomplete",
        "stale",
        "should_have_refused",
        "refused_wrongly",
    }

    with pytest.raises(ValueError, match="is not a valid FlagReason"):
        FlagReason("the answer said SNM is worth 48000")


def test_a_reference_field_refuses_something_somebody_pasted() -> None:
    """A field validated only for non-emptiness is a field a paragraph fits in. A reference
    is one token: anything with whitespace in it is a sentence, and a sentence arriving here
    is text from an answer coming through a field meant to hold a pointer.

    Anchored on what `brain.gate.compose.new_trace_ref` actually mints rather than on the
    cap beside it, so lowering the cap below a real reference fails here, and on a blob far
    longer than any reference this system produces, so raising it fails here too.

    Delete this and the cap can be set to anything, including nothing, and the whitespace
    rule is the only thing left between the flag store and an answer."""
    assert len(new_trace_ref()) < REFERENCE_MAX_LENGTH
    assert a_flag().trace_ref == REF

    pasted = "eyJhbGciOiJIUzI1NiJ9." + "a" * 180
    for bad in ("SNM hosting expires 14 Nov 2026", pasted, ""):
        with pytest.raises(FeedbackError):
            Flag(
                trace_ref=bad,
                question_id="G01a",
                department="maintenance",
                flagged_by="u_aaron",
                reason=FlagReason.WRONG_FACT,
                at=NOW,
            )


def test_a_flag_that_names_no_department_cannot_be_checked_against_anybodys_reach() -> None:
    """A flag with a blank department or a blank flagger is one nothing can decide about,
    and a check that cannot decide must refuse rather than pass.

    Delete this and an empty department reaches `Scope.matches`, where an absent value and
    an empty one are two different kinds of nothing."""
    with pytest.raises(FeedbackError, match="cannot be checked"):
        Flag(
            trace_ref=REF,
            question_id="G01a",
            department="",
            flagged_by="u_aaron",
            reason=FlagReason.WRONG_FACT,
            at=NOW,
        )

    with pytest.raises(FeedbackError, match="cannot be checked"):
        Flag(
            trace_ref=REF,
            question_id="G01a",
            department="maintenance",
            flagged_by="",
            reason=FlagReason.WRONG_FACT,
            at=NOW,
        )


# ------------------------------------------------------------- what may be captured


def test_a_captured_case_has_no_field_a_fetched_value_could_arrive_in() -> None:
    """**The load-bearing absence, asserted as an absence.** A captured case is committed,
    so it lands in every checkout, every CI log and every fork, under permissions belonging
    to nobody. A field holding what production returned is a permanent disclosure created by
    a usability feature.

    The corpus's `must_contain` is the same idea and is safe, because a person wrote those
    literals about a company they invented. The identical field here would be filled from a
    run. That is why it is absent rather than governed.

    Delete this and `must_contain: tuple[str, ...]` appears on the case, the capture button
    fills it from the answer, and nothing in the suite notices."""
    names = {f.name for f in dataclass_fields(CapturedCase)}

    assert names == {
        "question",
        "held",
        "answering_fields",
        "locked_fields",
        "mocked_from",
        "fault",
        "origin_trace_ref",
        "origin_question_id",
    }
    for forbidden in (
        "answer",
        "must_contain",
        "rows",
        "records",
        "expected_text",
        "entitlement",
        "value",
        "result",
    ):
        assert forbidden not in names, f"a captured case can carry a {forbidden}"


def test_capture_has_no_parameter_an_answer_can_arrive_through() -> None:
    """The other half of the same claim, on the surface rather than on the store. A caller
    holding the answer text must have nowhere to put it, or the absence of a field is worked
    around by a keyword argument that fills two.

    Asserted on the signature, because behaviour today says nothing about what a signature
    can acquire tomorrow.

    Delete this and `expected_answer=` appears on `capture`, which is how the field comes
    back."""
    parameters = set(inspect.signature(capture).parameters)

    assert parameters == {
        "one",
        "question",
        "asked_with",
        "answering_fields",
        "locked_fields",
        "mocked_from",
        "now",
    }
    for forbidden in ("answer", "text", "response", "said", "records", "rows", "must_contain"):
        assert forbidden not in parameters, f"an answer arrives through {forbidden}"


def test_every_fact_the_corpus_expects_an_answer_to_carry_is_refused_as_a_field_name() -> None:
    """**The hazard, run against the real values rather than against an invented one.** Every
    `must_contain` literal in the golden corpus and every canary token in the synthetic
    company is a value, and none of them can be spelled as a field name: the check builds
    `read:<name>` and lets the capability grammar refuse it.

    Anchored on the fixtures rather than on strings written here, so a canary added to the
    company is covered the day it is added.

    Delete this and the two field tuples become somewhere to write "14 Nov 2026", which is
    the shape of the disclosure this whole module is arranged around."""
    facts = {fact for one in GOLDEN for fact in one.must_contain} | set(canary_tokens())
    assert len(facts) > 5, "the corpus stopped supplying values and this asserts nothing"

    for fact in sorted(facts):
        with pytest.raises(FeedbackError, match="never values"):
            capture(
                a_flag(),
                question="what is SNM's contract worth",
                asked_with=person("u_weiling").entitlement(),
                answering_fields=(fact,),
                mocked_from="snm_construction",
                now=NOW,
            )


def test_a_case_that_cannot_be_run_again_is_refused_at_the_point_it_is_captured() -> None:
    """A case with no question reproduces nothing: it is a row saying an answer was wrong,
    with no way to ask for the answer again. And an origin reference that is a pasted
    sentence rather than a pointer leaves an auditor nothing to open, which is the same
    failure as the flag's own reference check and is checked in both places because a case
    can be constructed without ever passing through a flag.

    Delete this and the capture button can produce cases that look like tests and cannot be
    run, which is the most expensive kind of green."""

    def a_case(*, question: str = "what is SNM's contract worth", ref: str = REF) -> CapturedCase:
        return CapturedCase(
            question=question,
            held=(),
            answering_fields=("contract_value",),
            locked_fields=(),
            mocked_from="snm_construction",
            fault=FlagReason.WRONG_FACT,
            origin_trace_ref=ref,
            origin_question_id="G02a",
        )

    assert a_case().question

    with pytest.raises(FeedbackError, match="reproduces nothing"):
        a_case(question="   ")
    with pytest.raises(FeedbackError, match="is not a reference"):
        a_case(ref="the lead said the number was out of date")


def test_a_field_name_check_is_a_filter_and_the_proof_is_structural() -> None:
    """The positive sibling of the test above, and the honest statement of its limit. Real
    field names are admitted, or the feature captures nothing. An ordinary lowercase word is
    admitted too, whatever it means, because no grammar can tell a field name from a word.

    What makes that safe is not this check: it is that `CapturedCase` has no field a value
    belongs in, which the structural test above asserts. Two independent reasons, and this
    records which one is doing the work.

    Delete this and `_readable_name` can be tightened until nothing captures, or loosened to
    admit anything, and only one of those two shows up anywhere else."""
    captured = capture(
        a_flag(),
        question="When does SNM hosting expire and how many maintenance hours are left?",
        asked_with=person("u_weiling").entitlement(),
        answering_fields=("hosting_expiry", "hours_remaining"),
        mocked_from="snm_construction",
        now=NOW,
    )

    assert captured.answering_fields == ("hosting_expiry", "hours_remaining")
    assert captured.expectation is Expectation.ANSWER

    # Admitted, and it is a word rather than a value. Recorded so nobody reads the test
    # above as proving more than it does.
    assert capture(
        a_flag(),
        question="what is SNM's contract worth",
        asked_with=person("u_weiling").entitlement(),
        answering_fields=("permission",),
        mocked_from="snm_construction",
        now=NOW,
    ).answering_fields == ("permission",)


def test_the_mock_source_names_a_fixture_and_never_a_column() -> None:
    """`mocked_from` is where a captured case's rows come from, so it names something in the
    synthetic company. A dotted name reads as a column, and a mock resolving to a column
    resolves to nothing, which is a case that passes by testing an empty answer.

    Delete this and a case can be captured against `client.contract_value`, which mocks
    nothing and goes green for ever."""
    with pytest.raises(FeedbackError, match="names a field"):
        capture(
            a_flag(),
            question="what is SNM's contract worth",
            asked_with=person("u_weiling").entitlement(),
            answering_fields=("contract_value",),
            mocked_from="client.contract_value",
            now=NOW,
        )


def test_the_askers_reach_is_reduced_to_capabilities_with_the_person_and_places_removed() -> None:
    """**A captured case naming an employee is a permanent committed record of what that
    employee could see, and a scope is where the places live.** `capability_shape` drops both
    and keeps the capability names, which is what `brain.ops.canaries` carries for the same
    reason.

    Run against a real persona rather than an assembled set, because the thing being removed
    is what a real grant carries: `u_dual` holds two departments and a principal id, and
    neither may survive into a committed file.

    Delete this and the shape carries `principal_id` or a `department=finance` clause into
    the repository, where no revocation reaches it."""
    daniel = person("u_dual").entitlement()

    shape = capability_shape(daniel)

    assert shape == tuple(sorted({g.capability for g in daniel.grants}, key=lambda c: c.value))
    assert all(isinstance(one, Capability) for one in shape)

    written = repr(shape)
    assert "u_dual" not in written
    for place in ("sales", "web", "department", "partner_visible"):
        assert place not in written, f"the shape carries {place}"


def test_one_capability_held_in_two_places_reduces_to_one_entry() -> None:
    """The deduplication is what makes the shape a shape rather than a grant list with the
    scopes blanked. Two grants differing only in scope are one capability once the scope is
    gone, and leaving both would let a reader count how many places somebody holds it in.

    Constructed rather than taken from a persona, and deliberately so: no persona in
    `tests/fixtures/company.py` holds one capability twice, so this shape cannot be reached
    through the fixture and the case would otherwise go untested.

    Delete this and the shape becomes a count of somebody's grants, which is a number about
    a person."""
    twice = EntitlementSet(
        principal_id="u_twice",
        grants=(
            Grant(capability=Capability(value="read:client.name"), scope=Scope.department("sales")),
            Grant(capability=Capability(value="read:client.name"), scope=Scope.department("web")),
        ),
    )

    assert capability_shape(twice) == (Capability(value="read:client.name"),)


def test_a_captured_case_cannot_tell_two_departments_apart_and_the_mock_is_what_closes_it() -> None:
    """**The price, stated where it is paid.** `G04a` and `G04b` are one person asking about
    contract value in two departments, answered in sales and refused in web, and what
    separates them is a scope. The shape drops scopes, so a case built from either carries
    the same `held`, and the only thing distinguishing the two cases is which synthetic
    fixture supplies their rows.

    Delete this and the limitation stops being visible, and somebody captures a scope-level
    permission failure believing the case reproduces it."""
    daniel = person("u_dual").entitlement()
    sales, web = (one for one in GOLDEN if one.qid in ("G04a", "G04b"))
    assert sales.asked_by == web.asked_by == "u_dual"
    assert sales.expect is not web.expect

    cases = [
        capture(
            a_flag(department="sales"),
            question=one.question,
            asked_with=daniel,
            answering_fields=("contract_value",) if one.expect is Expect.ANSWER else (),
            mocked_from=f"{one.qid.lower()}_clients",
            now=NOW,
        )
        for one in (sales, web)
    ]

    assert cases[0].held == cases[1].held
    assert cases[0].mocked_from != cases[1].mocked_from
    assert cases[0].expectation is Expectation.ANSWER
    assert cases[1].expectation is Expectation.REFUSE


def test_a_case_expecting_a_refusal_cannot_also_claim_a_field_came_back_locked() -> None:
    """A withheld field and an absent record are rendered through one constant referenced
    twice, so the asker cannot tell them apart by construction. A case asserting a difference
    the system does not expose can only ever be satisfied by exposing it.

    Delete this and a captured case can demand that a refusal be distinguishable from an
    absence, which is the one thing that must never be true, written as a test that fails
    until somebody makes it true."""
    with pytest.raises(FeedbackError, match="distinguishable from an absence"):
        CapturedCase(
            question="what is SNM's contract worth",
            held=(),
            answering_fields=(),
            locked_fields=("contract_value",),
            mocked_from="snm_construction",
            fault=FlagReason.SHOULD_HAVE_REFUSED,
            origin_trace_ref=REF,
            origin_question_id="G02a",
        )


def test_the_shape_of_a_case_is_computed_from_its_fields_rather_than_stored_beside_them() -> None:
    """Two fields that must agree are two things that disagree silently. The expectation is a
    property, so a case whose fields say one thing cannot claim another.

    All three outcomes, because a property returning one constant satisfies any single check.

    Delete this and `expectation` becomes a stored field a caller sets, and the first case
    captured with the wrong one passes by asserting the wrong shape."""
    assert "expectation" not in {f.name for f in dataclass_fields(CapturedCase)}

    def case(*, answering: tuple[str, ...], locked: tuple[str, ...]) -> CapturedCase:
        return CapturedCase(
            question="show me everything about SNM Construction",
            held=(),
            answering_fields=answering,
            locked_fields=locked,
            mocked_from="snm_construction",
            fault=FlagReason.INCOMPLETE,
            origin_trace_ref=REF,
            origin_question_id="G03",
        )

    assert case(answering=("name",), locked=()).expectation is Expectation.ANSWER
    assert case(answering=("name",), locked=("contract_value",)).expectation is Expectation.PARTIAL
    assert case(answering=(), locked=()).expectation is Expectation.REFUSE


def test_the_two_names_for_one_outcome_cannot_drift_apart() -> None:
    """`brain.ops.feedback.Expectation` restates `tests.fixtures.golden.Expect` because `src`
    must not import from `tests`. Restating it means two lists that can drift, and the only
    thing that can notice is a test that holds them side by side.

    Member for member and value for value, so a fourth outcome added to the corpus fails here
    rather than producing a captured case with a shape the corpus cannot express.

    Delete this and the two vocabularies diverge quietly, and a case captured as one outcome
    is scored against a corpus that means another."""
    assert {e.name for e in Expectation} == {e.name for e in Expect}
    assert {e.value for e in Expectation} == {e.value for e in Expect}


# --------------------------------------------------------------- when it may be captured


def test_the_flag_window_is_the_trace_window_and_not_a_second_copy_of_thirty_days() -> None:
    """A flag is a pointer to a trace and holds nothing else of substance, so it is worth
    exactly as long as the thing it points at. Taken from where the trace window is declared
    rather than restated, because a second copy of "thirty days" drifts, and it drifts
    upwards: the copy nobody looks at is the one that gets raised.

    Anchored against `brain.ops.tracing`, which is outside this module, so repointing the
    constant at any other number fails here.

    Delete this and `FLAG_RETENTION_DAYS = 365` passes every other test in this file."""
    assert retention_for(TraceRecord.TRACE).days == FLAG_RETENTION_DAYS


def test_a_case_captured_after_the_trace_expired_is_built_from_somebodys_memory() -> None:
    """A captured case asserts what should have happened, and checking that means opening the
    trace. Outside its window there is nothing to open, so the case is somebody's
    recollection of an answer they read last month, committed as a permanent test, and it
    will be wrong in the direction that makes it look reasonable.

    Both sides of the boundary, and the window comes from `brain.ops.tracing` rather than
    from the constant under test, so a widened constant fails here rather than moving the
    test with it.

    Delete this and a flag outlives its trace, which turns the capture button into a way of
    writing tests about answers nobody can check."""
    window = timedelta(days=retention_for(TraceRecord.TRACE).days)
    filed = a_flag(at=NOW)

    assert expired(filed, now=NOW + window) is True
    assert expired(filed, now=NOW + window - timedelta(seconds=1)) is False

    with pytest.raises(FeedbackError, match="nothing left to check"):
        capture(
            filed,
            question="When does SNM hosting expire?",
            asked_with=person("u_weiling").entitlement(),
            answering_fields=("hosting_expiry",),
            mocked_from="snm_construction",
            now=NOW + window,
        )

    still_open = capture(
        filed,
        question="When does SNM hosting expire?",
        asked_with=person("u_weiling").entitlement(),
        answering_fields=("hosting_expiry",),
        mocked_from="snm_construction",
        now=NOW + window - timedelta(days=1),
    )
    assert still_open.origin_trace_ref == filed.trace_ref


def test_the_retention_window_is_a_parameter_so_the_check_can_be_seen_to_fail() -> None:
    """A check that can only ever run against the constant beside it cannot be shown to fail,
    and a check nobody has seen fail is a check nobody has evidence about. The window is a
    parameter defaulting to the derived one, which is the shape
    `brain.ops.tracing.retention_gaps` takes for the same reason.

    Delete this and `expired` can only be exercised at one window, so the comparison itself
    is never under test."""
    filed = a_flag(at=NOW)

    assert expired(filed, now=NOW + timedelta(days=2), retention_days=1) is True
    assert expired(filed, now=NOW + timedelta(days=2), retention_days=90) is False


# --------------------------------------------------------------------- what it scores as


def test_an_answer_that_showed_too_much_is_scored_where_no_percentage_reaches_it() -> None:
    """**A permission outcome is not the same as a severe-sounding one.** `REFUSED_WRONGLY`
    reads like a minor annoyance and is a permission failure, because a system that refuses
    the wrong people is failing at the thing it exists to get right in the other direction.

    Anchored against `brain.ops.evaluation.score` rather than against the enum, so the
    mapping is asserted by what it does to a run: a single permission fault fails a run whose
    quality is otherwise perfect.

    Delete this and `severity_of` can return `QUALITY` for everything, at which point a
    disclosure is averaged into a share and clears the floor."""
    for reason in (FlagReason.SHOULD_HAVE_REFUSED, FlagReason.REFUSED_WRONGLY):
        assert severity_of(reason) is Severity.PERMISSION

    leaked = case_result_for(
        CapturedCase(
            question="what is SNM's contract worth",
            held=(),
            answering_fields=("contract_value",),
            locked_fields=(),
            mocked_from="snm_construction",
            fault=FlagReason.SHOULD_HAVE_REFUSED,
            origin_trace_ref=REF,
            origin_question_id="G02a",
        ),
        passed=False,
    )
    verdict = score([leaked, case_result_for(_quality_case(), passed=True)])

    assert verdict.may_merge is False
    assert verdict.permission_failures == ("G02a",)
    assert verdict.quality_share == 1.0


def test_an_answer_that_was_merely_wrong_is_scored_where_a_floor_applies() -> None:
    """The positive sibling, and the reason the two classes exist. An answer being less good
    is a matter of degree and a suite with no tolerance is switched off in a fortnight, so
    the three quality reasons land where a floor applies rather than where zero does.

    Delete this and every flag becomes a permission failure, which is the mapping that makes
    the department lead's button the thing that reddens the build."""
    for reason in (FlagReason.WRONG_FACT, FlagReason.INCOMPLETE, FlagReason.STALE):
        assert severity_of(reason) is Severity.QUALITY

    results = [case_result_for(_quality_case(), passed=n > 0) for n in range(20)]
    verdict = score(results)

    assert verdict.permission_failures == ()
    assert verdict.quality_share == 0.95
    assert verdict.may_merge is True


def test_a_failing_case_says_why_and_the_reason_never_comes_from_the_answer() -> None:
    """`CaseResult` refuses a failure that says why nowhere, so a default sentence is
    supplied. It is built from the case's own expected shape, which is a name, and never from
    what the run produced, which is a value.

    Delete this and the harness supplies the answer text as the failure reason, and a CI log
    is the fourth place a restricted value is now written down."""
    failed = case_result_for(_quality_case(), passed=False)
    passed = case_result_for(_quality_case(), passed=True)

    assert failed.reason
    assert failed.question_id == "G01a"
    assert passed.reason == ""

    told = case_result_for(_quality_case(), passed=False, detail="the date was a month out")
    assert told.reason == "the date was a month out"


def test_capturing_a_case_writes_nothing_and_moves_no_bar() -> None:
    """**A captured case is red the day it is captured**, so committing it lowers the quality
    share and `score` refuses the run against its baseline. That is the ratchet working in
    the direction people find inconvenient, and the only legitimate way to record the lower
    figure is `accept_baseline`, which refuses a failing run.

    So a lead clicking a button cannot turn the build red on their own, and cannot quietly
    accept the lower figure either: somebody has to commit the case, and that commit has
    their name on it.

    Delete this and `capture` acquires a write, or this module acquires `accept_baseline`,
    and the harness starts recording its own baseline one acceptable loss at a time."""
    verdict = score([case_result_for(_quality_case(), passed=False)])

    assert verdict.may_merge is False
    with pytest.raises(ValueError, match="cannot become the baseline"):
        accept_baseline(verdict)

    tree = ast.parse(inspect.getsource(feedback))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "CaseResult" in imported, "the import walk read nothing and asserts nothing"
    assert "accept_baseline" not in imported


def _quality_case() -> CapturedCase:
    """A case whose fault is a quality judgement, for the scoring tests above."""
    return CapturedCase(
        question="When does SNM hosting expire?",
        held=(),
        answering_fields=("hosting_expiry",),
        locked_fields=(),
        mocked_from="snm_construction",
        fault=FlagReason.WRONG_FACT,
        origin_trace_ref=REF,
        origin_question_id="G01a",
    )
