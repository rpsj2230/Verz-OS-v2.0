"""What a subtask is asked for, and why the answer may not be a paragraph.

A subtask is a promise about a result, not an instruction to be helpful. The promise has
four parts, which is exactly what the work breakdown names: an objective, an output
schema, tool hints, and a scope predicate. Three of them are ordinary. The fourth is the
one this module exists for.

**Prose is not a permitted contract, and the mechanism is a vocabulary rather than a
rule.** `FieldKind` is a closed set with no member for free text, so a contract that
wanted a paragraph back could not be written, in the same construction
`brain.ops.automation.StepKind` uses to make an agent step unsayable and
`brain.core.errors` uses to keep DENIED and ABSENT to one public sentence. The reason is
not tidiness. **The redactor only works on typed data**: `brain.core.redaction.compute_mask`
decides field by field what a caller may read, and a paragraph has no fields, so a subtask
that returned one would hand the merge step a value nothing in this system can mask. The
result would then be composed into an answer, and the field policy that governs every
other route to the same information would have been walked around by a contract.

`LABEL` is the member that has to be watched, because a string field is the shape prose
arrives in. It is bounded at `MAX_LABEL_CHARS`, and the bound is not a formatting
preference: an unbounded string field is a paragraph with a column name on it.
`MAX_LABEL_CHARS` is `brain.ops.queue.MAX_ARGUMENT_CHARS`, imported rather than chosen
again, because a subtask result and a job argument are the same question asked twice and
`brain.ops.checkpoints` already answered it that way for checkpoint state.

**The objective is prose and that is not a contradiction.** What is refused is prose as
the shape of the *result*. The objective is the instruction, it is read by whoever wrote
the plan and by the model asked to carry it out, and reducing it to a schema would make a
plan nobody can review. See `PROSE_IS_NOT_A_CONTRACT` for the line between the two.

**A result that does not validate is a failed step, not a merge input**, and that is
enforced by a type rather than by a call somebody has to remember. `ValidatedResult` is
frozen and re-runs `result_refusals` in its own constructor, so a hand-built one carrying
a value that was never checked is refused at construction. `brain.orchestration.merge`
takes `ValidatedResult` and has no parameter that could take a raw mapping, which is what
makes the leaf's word "rather" structural: there is no call site at which an invalid
result could be merged, because there is nowhere to pass one.

An extra field is refused as loudly as a missing one, and that is the half that looks
over-strict until you ask what it is. A field the contract never declared is a field the
mask was never computed for, so it is business data arriving into a merge with no policy
attached to it. Missing is a subtask that did not do its job; extra is a subtask that did
something else.

**A subtask ceiling confers nothing.** `subtask_ceiling` produces the right-hand side of
an intersection and never a reach, exactly as `brain.agents.model.entitlement_ceiling`
does, and its principal id carries `SUBTASK_CEILING_PREFIX` for the reason that one
carries `agent:`: a set that reaches a trace must not be readable there as a person. A
contract declaring no capabilities reaches nothing, which is the direction a default has
to fail in.

Rejected: a `PROSE` member with a length cap on it. It is the obvious way to admit the
one case somebody will ask for, and it is the change that makes every sentence above
false: the cap is raised by whoever needs a longer summary, once, and the vocabulary stops
being a boundary. A subtask that genuinely needs to produce readable text produces the
fields the text is composed from, and the composing happens in the merge step where the
mask has already run.

Rejected: validating against a JSON Schema document. It admits `additionalProperties`,
`anyOf` and `"type": "string"` with no bound, which is every shape above wearing a
standard's name, and it moves the decision about what a subtask may return out of a diff
somebody reviews and into a document a planner can emit.

Scope: domain logic. Nothing here calls a model, opens a connection or reads a clock.

Task ids: M18.1.2, M18.1.3, M18.1.4
"""

from __future__ import annotations

import enum
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final, assert_never

from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.scope import Scope
from brain.ops.queue import MAX_ARGUMENT_CHARS

# ------------------------------------------------------------------ written-down reasons
#: Why the result may not be a paragraph, and where prose is still welcome.
PROSE_IS_NOT_A_CONTRACT: Final = (
    "A subtask result is composed into an answer by a merge step, and everything composed "
    "into an answer in this system passes a field mask first. brain.core.redaction works "
    "field by field, so a paragraph is not a value it can mask: it has no fields, and the "
    "honest answer to what a caller may read of it is unanswerable. A contract asking for "
    "prose would therefore route business data around the field policy that governs every "
    "other way to the same information. The objective is prose and stays prose, because it "
    "is the instruction rather than the result and nobody masks an instruction."
)

#: Why a field nobody declared is refused rather than ignored.
AN_UNDECLARED_FIELD_HAS_NO_MASK: Final = (
    "A missing field is a subtask that did not do its job and is easy to read as a "
    "failure. An extra field is worse and reads as harmless: it is a value the contract "
    "never named, so no mask was computed for it, and dropping it silently would make the "
    "refusal depend on the merge step remembering to. Both are refusals, and the extra "
    "one is refused first in the message so that a reader who declared their schema "
    "loosely finds out that is what happened."
)

#: Why a ceiling built from a contract is not a grant.
A_SUBTASK_CEILING_IS_THE_RIGHT_HAND_SIDE: Final = (
    "brain.agents.model.AN_AGENT_CEILING_IS_NOT_A_PRINCIPAL says this of an agent and it "
    "is true of a subtask for the same reason. The ceiling is carried in the type "
    "EntitlementSet.intersect takes because that is the one implementation of the "
    "platform's invariant, it is only ever the second argument, and intersect keeps the "
    "caller's principal id, so a delegated run is still the asker's run. The id is "
    "prefixed so a ceiling that reaches a trace cannot be read there as a person."
)


class ContractError(Exception):
    """A subtask contract, or a result claiming to satisfy one, that cannot mean what it says.

    Outside the `brain.core.errors` taxonomy, like `brain.agents.model.AgentError` and for
    the same reason: those five outcomes describe an answer given to a person, and this is a
    refusal to plan or to merge. Nobody asking a question ever sees one.
    """


# ------------------------------------------------------------------ the vocabulary (M18.1.4)
class FieldKind(enum.StrEnum):
    """Every type a subtask may return.

    There is no member for prose, a paragraph, a summary, a narrative or free text, and
    there is nowhere to add one without changing this enum in a diff somebody reviews. That
    is the whole of `PROSE_IS_NOT_A_CONTRACT`: it is not a rule a planner is asked to
    follow, it is a vocabulary in which the forbidden thing cannot be said.

    `LABEL` is the member to read carefully. It admits a short string because a name, a
    status and a reference are all strings, and it is bounded at `MAX_LABEL_CHARS` because
    an unbounded one is a paragraph with a column name on it.
    """

    #: A reference to something else: a record id, a document id, a slug.
    IDENTIFIER = "identifier"
    #: A short string. Bounded; see `MAX_LABEL_CHARS`.
    LABEL = "label"
    INTEGER = "integer"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    #: Timezone-aware, for the reason every other timestamp in this repository is.
    TIMESTAMP = "timestamp"


#: The longest a `LABEL` may be. `brain.ops.queue.MAX_ARGUMENT_CHARS`, imported rather than
#: chosen again: a job argument, a checkpoint channel and a subtask result field are one
#: question asked three times, and `brain.ops.checkpoints` already imported it for the
#: second. Above this a string is content rather than a reference, and content is the thing
#: a schema was supposed to stop arriving.
MAX_LABEL_CHARS: Final[int] = MAX_ARGUMENT_CHARS

#: A field name, in the grammar `brain.core.scope.Clause.field` already uses, so a field a
#: contract can declare is a field a scope predicate can be written against. Two grammars
#: for one name is one grammar somebody writes around.
FIELD_NAME_RE: Final = r"^[a-z][a-z0-9_]*$"

#: How short an objective may be and still say what the subtask is for. A subtask nobody
#: can read is a subtask nobody can review, and the planner's proposal is reviewed by the
#: person answerable for the run.
MINIMUM_OBJECTIVE: Final = 12


@dataclass(frozen=True)
class FieldSpec:
    """One field a subtask promises to return.

    Frozen, because a contract is read once when the subtask is dispatched and again when
    its result comes back, and a spec that could change between the two would validate a
    result against a promise nobody made.
    """

    name: str
    kind: FieldKind

    def __post_init__(self) -> None:
        if not re.match(FIELD_NAME_RE, self.name):
            msg = (
                f"field name {self.name!r} is not in the grammar {FIELD_NAME_RE}, which is "
                "brain.core.scope.Clause's own, so a scope predicate could not be written "
                "against it"
            )
            raise ContractError(msg)


def value_refusals(spec: FieldSpec, value: object) -> tuple[str, ...]:
    """Every reason this value does not satisfy this field, in words a planner can act on.

    Exhaustive over `FieldKind` by `match` and `assert_never`, which is the point of the
    shape: a seventh kind cannot reach production without somebody deciding what a value of
    it looks like, and a mapping with a default would admit one silently as whatever the
    default happened to be. `brain.gate.leash.route_for` makes the same argument about a
    fourth autonomy tier.

    A boolean is refused where an integer is asked for, and that is not pedantry. `bool` is
    a subclass of `int` in Python, so an `isinstance` check alone admits `True` as the
    number one, and a count of one and a flag saying yes are not the same fact.
    """
    findings: list[str] = []
    match spec.kind:
        case FieldKind.IDENTIFIER | FieldKind.LABEL:
            if not isinstance(value, str):
                findings.append(f"{spec.name}: {type(value).__name__} where {spec.kind} was asked")
            elif not value.strip():
                findings.append(
                    f"{spec.name}: an empty {spec.kind} is a field that was declared and "
                    "not answered, which reads in a merged answer as a real blank"
                )
            elif len(value) > MAX_LABEL_CHARS:
                findings.append(
                    f"{spec.name}: {len(value)} characters, over {MAX_LABEL_CHARS}. "
                    f"{PROSE_IS_NOT_A_CONTRACT}"
                )
        case FieldKind.INTEGER:
            if isinstance(value, bool) or not isinstance(value, int):
                findings.append(
                    f"{spec.name}: {type(value).__name__} where an integer was asked; a "
                    "boolean is an int in Python and a count of one is not a yes"
                )
        case FieldKind.DECIMAL:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                findings.append(f"{spec.name}: {type(value).__name__} where a decimal was asked")
        case FieldKind.BOOLEAN:
            if not isinstance(value, bool):
                findings.append(f"{spec.name}: {type(value).__name__} where a boolean was asked")
        case FieldKind.TIMESTAMP:
            if not isinstance(value, datetime):
                findings.append(f"{spec.name}: {type(value).__name__} where a timestamp was asked")
            elif value.tzinfo is None:
                findings.append(
                    f"{spec.name}: a naive timestamp, which is hours out in whichever "
                    "direction the host happens to sit and says so nowhere"
                )
        case _:
            assert_never(spec.kind)
    return tuple(findings)


# ------------------------------------------------------------------- the contract (M18.1.2)
@dataclass(frozen=True)
class SubtaskContract:
    """What one subtask is asked for: objective, output schema, tool hints, scope predicate.

    All four parts are required and the third is required to be a hint rather than a
    permission. `tool_hints` names tools the planner thinks will be useful; it grants
    nothing and narrows nothing, because what a child may actually call is decided by
    `brain.gate.catalogue.project` against the reach `brain.orchestration.delegation`
    computes. A hint that could add a tool would be a planner writing a grant.

    `scope` and `capabilities` are the two halves of the narrowing this contract
    contributes, and they are separate for the reason `brain.agents.model.AgentAuthority`
    keeps them separate: a scope narrows rows and a capability list narrows what the
    intersection keeps, and one field doing both would make an empty value mean two
    different things.
    """

    subtask_id: str
    #: Prose, and deliberately so. See `PROSE_IS_NOT_A_CONTRACT`.
    objective: str
    #: What comes back. Empty is refused; see `__post_init__`.
    output: tuple[FieldSpec, ...]
    #: Tools the planner expects this to need. Advisory, and never a grant.
    tool_hints: tuple[str, ...] = ()
    #: The rows this subtask may touch, at most.
    scope: Scope = field(default_factory=Scope)
    #: The capabilities this subtask's ceiling admits. Empty reaches nothing.
    capabilities: tuple[Capability, ...] = ()

    def __post_init__(self) -> None:
        if not self.subtask_id.strip():
            msg = "a subtask with no id cannot be depended on, dispatched or merged"
            raise ContractError(msg)
        if len(self.objective.strip()) < MINIMUM_OBJECTIVE:
            msg = (
                f"subtask {self.subtask_id!r} states {self.objective!r} as its objective, "
                "which tells whoever is reviewing the plan nothing about what it is for"
            )
            raise ContractError(msg)
        if not self.output:
            msg = (
                f"subtask {self.subtask_id!r} declares no output fields, so anything it "
                f"returned would satisfy it. {PROSE_IS_NOT_A_CONTRACT}"
            )
            raise ContractError(msg)
        names = [spec.name for spec in self.output]
        duplicated = sorted({name for name in names if names.count(name) > 1})
        if duplicated:
            msg = (
                f"subtask {self.subtask_id!r} declares {duplicated} more than once, so one "
                "of the two specifications decides and which one is an ordering accident"
            )
            raise ContractError(msg)

    @property
    def field_names(self) -> frozenset[str]:
        return frozenset(spec.name for spec in self.output)


# ------------------------------------------------------------------ the ceiling
#: `EntitlementSet.principal_id` on a subtask ceiling, so it is never read as a person.
#: `brain.agents.model.CEILING_PRINCIPAL_PREFIX` is `agent:` for the same reason, and the
#: two are deliberately different strings: a trace showing which of the two narrowed a run
#: is worth more than one prefix serving both.
SUBTASK_CEILING_PREFIX: Final = "subtask:"


def subtask_ceiling(contract: SubtaskContract) -> EntitlementSet:
    """The contract's own narrowing, in the type the one intersection takes.

    **This is not an entitlement and confers nothing.** See
    `A_SUBTASK_CEILING_IS_THE_RIGHT_HAND_SIDE`. Every capability is bound to the contract's
    scope, so the ceiling narrows on both axes at once, exactly as
    `brain.agents.model.entitlement_ceiling` does: a parent holding `read:client.name`
    company-wide, through a subtask scoped to one department, comes out holding it there.

    A contract declaring no capabilities produces a ceiling admitting nothing, so the child
    reaches nothing and there is no work for it to do. That is the direction a default has
    to fail in, and it is the same answer `AgentAuthority` gives for the same absence.

    No `not_after`. A subtask does not expire on a clock; it finishes, fails or is
    cancelled, and each of those is an event with a cause rather than a deadline. A
    time-boxed ceiling here would be a fourth way for a run to stop that nothing lists.
    """
    return EntitlementSet(
        principal_id=f"{SUBTASK_CEILING_PREFIX}{contract.subtask_id}",
        grants=tuple(
            Grant(capability=capability, scope=contract.scope)
            for capability in contract.capabilities
        ),
    )


# ------------------------------------------------------------------ the result (M18.1.3)
def result_refusals(contract: SubtaskContract, result: Mapping[str, object]) -> tuple[str, ...]:
    """Every reason this result is a failed step rather than a merge input.

    Returns all of them rather than the first, matching `brain.ops.queue.queue_url_refusals`
    and `brain.config.check`: a subtask that got three fields wrong should learn that once
    rather than three times, because the thing being corrected is a model's output and each
    round trip is another run.

    Extra fields are reported before missing ones. See `AN_UNDECLARED_FIELD_HAS_NO_MASK`:
    the reader who declared their schema loosely is the one who needs to see it first, and
    a missing field reads as a failure without any help.
    """
    findings: list[str] = []
    declared = contract.field_names
    undeclared = sorted(set(result) - declared)
    findings.extend(
        f"{name}: not declared by {contract.subtask_id!r}. {AN_UNDECLARED_FIELD_HAS_NO_MASK}"
        for name in undeclared
    )
    for spec in contract.output:
        if spec.name not in result:
            findings.append(
                f"{spec.name}: declared by {contract.subtask_id!r} and absent from the "
                "result, so the merge would compose an answer around a hole"
            )
            continue
        findings.extend(value_refusals(spec, result[spec.name]))
    return tuple(findings)


@dataclass(frozen=True)
class ValidatedResult:
    """One subtask's result, after it has been checked against the contract it answers.

    The constructor re-runs `result_refusals`, so this type cannot be built around a value
    that was never checked. That is what makes M18.1.3's word "rather" structural rather
    than remembered: `brain.orchestration.merge` takes these and has no parameter that
    could take a raw mapping, so there is no call site at which an invalid result becomes a
    merge input. `brain.ops.jobs.JobRecord` refuses an impossible row in its own
    constructor for the same reason, which is that a row also arrives by being loaded.

    `values` is a mapping and not a model. What it holds is business data the merge step
    will mask, and turning it into a typed object here would mean this module deciding the
    shape of every subtask anybody ever writes.
    """

    contract: SubtaskContract
    values: Mapping[str, object]

    def __post_init__(self) -> None:
        refusals = result_refusals(self.contract, self.values)
        if refusals:
            msg = (
                f"subtask {self.contract.subtask_id!r} returned a result that does not "
                f"satisfy its contract: {'; '.join(refusals)}"
            )
            raise ContractError(msg)


def validated(contract: SubtaskContract, result: Mapping[str, object]) -> ValidatedResult:
    """The result as a merge input, or a refusal naming everything wrong with it.

    A named producer beside the constructor because the two audiences differ: a caller
    dispatching subtasks wants one function to call, and a reader of `merge`'s signature
    wants a type that cannot have been built any other way. Both exist and the second is
    what the guarantee rests on.
    """
    return ValidatedResult(contract=contract, values=dict(result))


def validated_or_none(
    contract: SubtaskContract, result: Mapping[str, object]
) -> ValidatedResult | None:
    """The same, for a caller collecting a partial run.

    `None` rather than an exception where a caller is gathering several results and expects
    some of them to fail: raising would make the first failure decide how many of the rest
    were even looked at, and a partial answer is the case
    `brain.orchestration.merge` exists to report honestly.
    """
    if result_refusals(contract, result):
        return None
    return validated(contract, result)


def contract_gaps(contracts: Sequence[SubtaskContract]) -> tuple[str, ...]:
    """Every way a set of contracts would fail to hold a plan together.

    Takes the contracts rather than reading anything of its own, for the reason
    `brain.ops.starter.starter_gaps` records: a diagnostic that can only be run against the
    healthy tree has nothing to report on today's data, so switching off any of its
    refusals changes nothing observable and every one of them survives a mutation.
    """
    findings: list[str] = []
    ids = [one.subtask_id for one in contracts]
    duplicated = sorted({one for one in ids if ids.count(one) > 1})
    findings.extend(
        f"{one!r} is the id of more than one subtask, so a dependency naming it names two"
        for one in duplicated
    )
    findings.extend(
        f"{one.subtask_id!r} declares no capabilities, so its ceiling admits nothing and "
        "the child it produces can reach none of the data its objective describes"
        for one in contracts
        if not one.capabilities
    )
    return tuple(findings)
