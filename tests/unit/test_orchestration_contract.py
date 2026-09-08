"""A subtask promises typed fields, and a result that does not satisfy the promise is a failure.

The rule this file is mostly about is that prose is not a permitted contract, and the
reason is not tidiness: the redactor works field by field, so a paragraph is a value
nothing in this system can mask, and a subtask returning one would route business data
around the field policy that governs every other way to the same information. So the tests
below assert the vocabulary as a closed set rather than asserting that a particular string
is refused, because a member added later would pass the second and fail the first.

Real `Capability`, `Scope` and `EntitlementSet` throughout, and the ceiling is compared
against what `brain.core.entitlement.EntitlementSet.intersect` actually keeps rather than
against a set built to match.

Task ids: M18.1.2, M18.1.3, M18.1.4
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from brain.core.entitlement import Capability
from brain.core.scope import Clause, Op, Scope
from brain.ops.queue import MAX_ARGUMENT_CHARS
from brain.orchestration.contract import (
    MAX_LABEL_CHARS,
    SUBTASK_CEILING_PREFIX,
    ContractError,
    FieldKind,
    FieldSpec,
    SubtaskContract,
    ValidatedResult,
    contract_gaps,
    result_refusals,
    subtask_ceiling,
    validated,
    validated_or_none,
    value_refusals,
)

NOW = datetime(2026, 9, 8, 4, 0, tzinfo=UTC)
NAME = Capability(value="read:client.name")
TOTAL = Capability(value="read:invoice.total")

OUTPUT = (
    FieldSpec(name="client_id", kind=FieldKind.IDENTIFIER),
    FieldSpec(name="status", kind=FieldKind.LABEL),
    FieldSpec(name="open_invoices", kind=FieldKind.INTEGER),
    FieldSpec(name="balance", kind=FieldKind.DECIMAL),
    FieldSpec(name="overdue", kind=FieldKind.BOOLEAN),
    FieldSpec(name="checked_at", kind=FieldKind.TIMESTAMP),
)

RESULT = {
    "client_id": "c-9",
    "status": "open",
    "open_invoices": 3,
    "balance": 1250.5,
    "overdue": True,
    "checked_at": NOW,
}


def _contract(**overrides: object) -> SubtaskContract:
    fields: dict[str, object] = {
        "subtask_id": "s-1",
        "objective": "Report the open invoice position for this client",
        "output": OUTPUT,
        "capabilities": (NAME, TOTAL),
    }
    fields.update(overrides)
    return SubtaskContract(**fields)  # type: ignore[arg-type]


# ----------------------------------------------------------------- the vocabulary (M18.1.4)
def test_there_is_no_field_kind_for_prose():
    """**The mechanism is a vocabulary, not a rule.**

    Asserted as the exact set rather than by checking that some particular word is refused,
    because a `PROSE` member added later would pass a "is prose refused" test written
    against a string and fail this one.

    Delete this and a paragraph becomes expressible as a subtask result, and the merge step
    gets a value `brain.core.redaction.compute_mask` cannot mask."""
    assert {one.value for one in FieldKind} == {
        "identifier",
        "label",
        "integer",
        "decimal",
        "boolean",
        "timestamp",
    }


def test_the_label_bound_is_the_queues_own_bound_rather_than_a_figure_chosen_here():
    """A job argument, a checkpoint channel and a subtask result field are one question
    asked three times, and `brain.ops.checkpoints` already imported the answer for the
    second.

    Delete this and `MAX_LABEL_CHARS` becomes a free constant: raising it would make a
    string field longer without anybody deciding that content had become admissible in a
    queue row too."""
    assert MAX_LABEL_CHARS == MAX_ARGUMENT_CHARS


def test_a_label_over_the_bound_is_prose_with_a_column_name_on_it():
    """The member most likely to be abused, held at its bound.

    Delete this and `LABEL` becomes an unbounded string field, which is the shape the whole
    enum exists to make unsayable."""
    spec = FieldSpec(name="status", kind=FieldKind.LABEL)

    assert value_refusals(spec, "x" * MAX_LABEL_CHARS) == ()

    refusals = value_refusals(spec, "x" * (MAX_LABEL_CHARS + 1))
    assert len(refusals) == 1
    assert f"over {MAX_LABEL_CHARS}" in refusals[0]


@pytest.mark.parametrize("blank", ["", " ", "\t"])
def test_a_blank_label_is_a_field_declared_and_not_answered(blank):
    """Whitespace as well as the empty string, because a subtask returning a space has
    answered nothing and a strip-free check admits it.

    Delete this and a merged answer could carry a real-looking blank in a field the reader
    assumes was filled in."""
    refusals = value_refusals(FieldSpec(name="status", kind=FieldKind.LABEL), blank)

    assert len(refusals) == 1
    assert "declared and not answered" in refusals[0]


def test_a_boolean_is_not_an_integer():
    """`bool` is a subclass of `int` in Python, so an `isinstance` check alone admits `True`
    as the number one, and a count of one and a flag saying yes are not the same fact.

    Delete this and a subtask could answer "yes" where the contract asked "how many", and
    the merged answer would report one."""
    spec = FieldSpec(name="open_invoices", kind=FieldKind.INTEGER)

    assert value_refusals(spec, 1) == ()

    refusals = value_refusals(spec, True)
    assert len(refusals) == 1
    assert "boolean is an int" in refusals[0]


def test_a_decimal_field_refuses_a_boolean_for_the_same_reason():
    """The same trap one type along, because `bool` is an `int` and an `int` is admitted
    where a decimal is asked for.

    Delete this and the integer case above would be the only one covered, and a decimal
    field would accept True as 1.0."""
    spec = FieldSpec(name="balance", kind=FieldKind.DECIMAL)

    assert value_refusals(spec, 12) == ()
    assert value_refusals(spec, 12.5) == ()
    assert len(value_refusals(spec, True)) == 1


def test_a_naive_timestamp_is_refused():
    """Every other timestamp in this repository is timezone-aware for the same reason: a
    naive one is hours out in whichever direction the host sits and says so nowhere.

    Delete this and a subtask could return a time that means something different on the box
    that merged it from the box that produced it."""
    spec = FieldSpec(name="checked_at", kind=FieldKind.TIMESTAMP)

    assert value_refusals(spec, NOW) == ()

    refusals = value_refusals(spec, datetime(2026, 9, 8, 4, 0))
    assert len(refusals) == 1
    assert "naive" in refusals[0]


def test_every_kind_admits_something_and_refuses_something():
    """Exhaustive over the enum, so a seventh kind arrives with no rule and fails here
    rather than admitting every value that reaches it.

    Delete this and a new member could be added whose `value_refusals` branch was never
    exercised, which is the shape a default in a mapping produces."""
    good: dict[FieldKind, object] = {
        FieldKind.IDENTIFIER: "c-9",
        FieldKind.LABEL: "open",
        FieldKind.INTEGER: 3,
        FieldKind.DECIMAL: 1.5,
        FieldKind.BOOLEAN: False,
        FieldKind.TIMESTAMP: NOW,
    }
    bad: dict[FieldKind, object] = {
        FieldKind.IDENTIFIER: 9,
        FieldKind.LABEL: 9,
        FieldKind.INTEGER: "three",
        FieldKind.DECIMAL: "one",
        FieldKind.BOOLEAN: "yes",
        FieldKind.TIMESTAMP: "now",
    }

    assert set(good) == set(FieldKind)
    for kind in FieldKind:
        spec = FieldSpec(name="field", kind=kind)
        assert value_refusals(spec, good[kind]) == (), kind
        assert value_refusals(spec, bad[kind]) != (), kind


# ------------------------------------------------------------------ the contract (M18.1.2)
def test_a_contract_declaring_no_output_fields_is_refused():
    """A contract with an empty schema is satisfied by anything, which is prose with extra
    steps.

    Delete this and the whole vocabulary above could be bypassed by declaring nothing."""
    with pytest.raises(ContractError, match="declares no output fields"):
        _contract(output=())


def test_the_objective_is_prose_and_that_is_the_point():
    """What is refused is prose as the shape of the *result*. The objective is the
    instruction, read by whoever reviews the plan, and reducing it to a schema would make a
    plan nobody can review.

    Delete this and somebody reading only the module's title could conclude that prose is
    refused everywhere and turn the objective into an enum."""
    one = _contract(objective="Report the open invoice position for this client")

    assert one.objective.startswith("Report")


def test_an_objective_too_short_to_review_is_refused():
    """The plan is reviewed by the person answerable for the run, and a subtask called "go"
    cannot be reviewed at all.

    Delete this and a planner could propose subtasks nobody reading the plan can judge."""
    with pytest.raises(ContractError, match="tells whoever is reviewing"):
        _contract(objective="go")


def test_a_contract_with_no_id_is_refused():
    """A subtask with no id cannot be depended on, dispatched or matched to its result.

    Delete this and a plan could carry an anonymous subtask, and every set comparison in
    `plan_refusals` would match it against the empty string."""
    with pytest.raises(ContractError, match="no id"):
        _contract(subtask_id="  ")


def test_a_field_declared_twice_is_refused():
    """Two specifications for one name means one of them decides and which one is an
    ordering accident.

    Delete this and a contract could declare a field as an integer and as a label at once,
    and whether a result validated would depend on tuple order."""
    with pytest.raises(ContractError, match="more than once"):
        _contract(
            output=(
                FieldSpec(name="status", kind=FieldKind.LABEL),
                FieldSpec(name="status", kind=FieldKind.INTEGER),
            )
        )


def test_a_field_name_outside_the_scope_grammar_is_refused():
    """The grammar is `brain.core.scope.Clause`'s own, so a field a contract can declare is
    a field a scope predicate can be written against.

    Delete this and a contract could declare a field no scope could ever narrow, which is a
    value nothing can be filtered on."""
    with pytest.raises(ContractError, match="grammar"):
        FieldSpec(name="Client ID", kind=FieldKind.IDENTIFIER)


# ------------------------------------------------------------------ the ceiling
def test_a_subtask_ceiling_binds_every_capability_to_the_contracts_scope():
    """The ceiling narrows on both axes at once, exactly as an agent's does.

    Delete this and the scope predicate M18.1.2 asks for would be carried on the contract
    and applied to nothing, so a subtask scoped to one department would reach every one."""
    scope = Scope(clauses=(Clause(field="department", op=Op.EQ, value="finance"),))

    ceiling = subtask_ceiling(_contract(scope=scope))

    assert ceiling.principal_id == f"{SUBTASK_CEILING_PREFIX}s-1"
    assert {one.capability.value for one in ceiling.grants} == {NAME.value, TOTAL.value}
    assert all(one.scope == scope for one in ceiling.grants)
    assert ceiling.not_after is None


def test_a_contract_declaring_no_capabilities_reaches_nothing():
    """The direction a default has to fail in, and the same answer
    `brain.agents.model.AgentAuthority` gives for the same absence.

    Delete this and an empty capability list could come to mean everything, which is the one
    default that turns a new subtask into a wide one."""
    ceiling = subtask_ceiling(_contract(capabilities=()))

    assert ceiling.grants == ()
    assert not ceiling.holds(NAME)


# ------------------------------------------------------------------ the result (M18.1.3)
def test_a_result_that_satisfies_its_contract_validates():
    """The positive half. A validator tested only by its refusals is satisfied by one that
    refuses everything, and this one stands between every subtask and the merge.

    Delete this and `result_refusals` could return a finding unconditionally, which would
    turn every run into a run with no results and a full set of gaps."""
    one = _contract()

    assert result_refusals(one, RESULT) == ()
    assert validated(one, RESULT).values == RESULT


def test_a_missing_field_is_refused():
    """A merge composing an answer around a hole reports something it does not have.

    Delete this and a subtask could answer half its contract and the merged answer would
    carry the missing field as absent rather than as a gap."""
    short = {key: value for key, value in RESULT.items() if key != "balance"}

    refusals = result_refusals(_contract(), short)

    assert len(refusals) == 1
    assert "declared by 's-1' and absent" in refusals[0]


def test_an_undeclared_field_is_refused_and_reported_first():
    """A field the contract never named is a field no mask was computed for, so it is
    business data arriving into a merge with no policy attached.

    Reported before a missing one because the reader who declared their schema loosely is
    the one who needs to see it, and a missing field reads as a failure without any help.

    Delete this and a subtask could return anything it liked alongside what was asked for,
    and the extra values would be merged."""
    extra = {**RESULT, "internal_note": "chased twice"}
    short = {key: value for key, value in extra.items() if key != "balance"}

    refusals = result_refusals(_contract(), short)

    assert len(refusals) == 2
    assert "internal_note" in refusals[0]
    assert "no mask" in refusals[0]
    assert "balance" in refusals[1]


def test_a_validated_result_cannot_be_built_around_an_unchecked_value():
    """**This is where "failure rather than merge input" stops being a sentence.**

    The constructor re-runs the contract check, so the type cannot be built by hand around a
    value nothing validated, and `brain.orchestration.merge.merge` takes this type and has
    no parameter a raw mapping could arrive through.

    Delete this and the guarantee reduces to whoever calls `validated` rather than
    constructing one directly."""
    with pytest.raises(ContractError, match="does not satisfy its contract"):
        ValidatedResult(contract=_contract(), values={"client_id": "c-9"})


def test_a_caller_gathering_a_partial_run_gets_none_rather_than_an_exception():
    """Raising would make the first failure decide how many of the rest were even looked at,
    and a partial answer is the case the merge step exists to report honestly.

    Delete this and a run with one bad subtask would report nothing about the other seven."""
    one = _contract()

    assert validated_or_none(one, RESULT) is not None
    assert validated_or_none(one, {"client_id": "c-9"}) is None


# ------------------------------------------------------------------------- the diagnostic
def test_contract_gaps_reports_a_duplicate_id_and_a_contract_that_reaches_nothing():
    """Both halves in one test, and the healthy case beside them, because a diagnostic that
    can only be run against the healthy tree cannot be shown to fail.

    Delete this and a plan could carry two subtasks with one id, which makes every
    dependency naming it name two."""
    healthy = (_contract(), _contract(subtask_id="s-2"))

    assert contract_gaps(healthy) == ()

    findings = contract_gaps(
        (_contract(), _contract(), _contract(subtask_id="s-3", capabilities=()))
    )
    assert len(findings) == 2
    assert "more than one subtask" in findings[0]
    assert "declares no capabilities" in findings[1]
