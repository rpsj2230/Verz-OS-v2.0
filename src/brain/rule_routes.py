"""Fast-lane rules from the console: a department administrator lists, adds, tests, retires them.

M6.5.1 asks that a department's administrator add, test and retire a fast-lane rule for their own
department from the console, and that the rule answer without a model call from the next request.
`brain.gate.rule_store` reads the rule table on every question for the asker's department and the
whole install's, and `0199` gives a rule a department. These are the four routes the Rules page
calls, and every one of them is the grant's question asked at a place.

**The authority is the one an uploaded table is changed under, and no capability is new.**
`admin:field_classification` writes a rule and `read:field_classification` lists one, each asked
at the rule's place with `brain.console.govern._in_reach`: a department's slug for a department's
rule, and `NOWHERE` for a rule the whole install asks with, which only a grant over everything
admits. Nothing in `brain.identity.first_administrator.ADMINISTRATION` names fast-lane rules, and
the classification grants are the closest existing authority by what they decide: an uploaded
price list's classification is what the fast lane answers about it, and most department rules are
question shapes over a department's own uploaded tables (`brain.knowledge.classified_rows`). So
the person who decides what a department's table says to whom also decides which questions it
answers with no model. See `A_RULE_IS_WRITTEN_UNDER_THE_GRANTS_A_TABLE_IS_CHANGED_UNDER`.
Rejected: a new `admin:fast_path_rule`, which would be a capability no administrator holds on any
install today, so no department's administrator could use the screen until somebody granted it.

**A rule another department wrote is answered as a rule that does not exist.** The list holds the
rules at places the reader's read grant admits, and retiring a rule at a place their write grant
does not admit is refused in the words a missing rule gets. A test or an addition names its place
itself, so it is refused for the place, which tells the administrator nothing they did not type. A
department's rule id is stored under its department, `<department>__<name>`, so two departments
may use one name and neither learns from a refusal that the other did; an install-wide rule's name
may not contain `__` for the same reason. See `A_RULE_OUT_OF_REACH_IS_A_RULE_THAT_DOES_NOT_EXIST`.

**A test saves nothing and reads at the tester's own reach.** It builds the candidate rule through
`rules_from_rows`, the validator every stored rule passes, matches the question against it alone
with `brain.gate.fast_lane.match_rule`, and answers through `respond`, the redactor and
`served_from`, the lane's own three steps, at the administrator's reach. So a rule over a column
the administrator may not read tests as answering nothing, and a name that does not exist tests the
same way: the test says whether the words matched and what the lane would say, and nothing about
which records exist. See `A_TEST_IS_THE_LANE_AT_THE_TESTERS_OWN_REACH`.

**A rule is retired and never edited.** Nothing here updates a rule's words: a change is a
retirement and an addition. The table does not yet refuse such an update itself; `0199` says
why.

Task ids: M6.5.1
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Final

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import async_sessionmaker

from brain.api import API_PREFIX, COMMON_RESPONSES
from brain.api_routes import Asked, Asking
from brain.attribution import trace_of_request
from brain.classification_routes import CLASSIFICATION_READ, CLASSIFICATION_WRITE
from brain.console.govern import NOWHERE, _in_reach
from brain.core.department import SLUG_PATTERN
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.envelope import OBJECT_NAME_PATTERN
from brain.core.errors import Absent, Denied, Failed
from brain.core.fast_path import MAX_TEMPLATE_CHARS, MIN_TEMPLATE_CHARS
from brain.core.redaction import redact
from brain.gate.answer import policy_for, served_from
from brain.gate.caches import MAX_QUESTION_CHARS
from brain.gate.fast_lane import (
    FastLaneAnswer,
    FastLaneError,
    FastPathRule,
    entities_served,
    match_rule,
    respond,
    rules_from_rows,
)
from brain.gate.rule_store import KeptRule, StoredRules
from brain.ops.classification_store import Writer

log = structlog.get_logger(__name__)

# ------------------------------------------------------------------ written-down reasons
#: Why a rule is written under the classification grants.
A_RULE_IS_WRITTEN_UNDER_THE_GRANTS_A_TABLE_IS_CHANGED_UNDER: Final = (
    "No capability names fast-lane rules, and the classification grants decide what the fast "
    "lane answers about an uploaded table, which is what most department rules ask about. So a "
    "rule is listed under the read grant and written under the write grant, each asked at the "
    "rule's place: a department's for a department's rule, everything for the install's."
)

#: Why a rule out of reach is refused as a missing one.
A_RULE_OUT_OF_REACH_IS_A_RULE_THAT_DOES_NOT_EXIST: Final = (
    "A rule at a place the reader's grant does not admit is not listed, and retiring it is "
    "refused in the words a missing rule gets. A test or an addition at such a place is refused "
    "for the place, which the administrator chose, and never for a rule, so an administrator "
    "learns nothing about another department's rules. A department's rule id is stored under "
    "its department, so two departments may use one name and neither learns of the other."
)

#: Why a test reads at the tester's reach and says nothing about records.
A_TEST_IS_THE_LANE_AT_THE_TESTERS_OWN_REACH: Final = (
    "A test runs the candidate rule through the lane's own match, read, redaction and sentence "
    "at the administrator's own reach, and saves nothing. A rule over a column they may not "
    "read answers nothing, as a name that does not exist does, so a test cannot be used to "
    "learn what exists beyond what its tester already reads."
)

# ------------------------------------------------------------------------ the figures
#: Listing a rule, and changing one: the classification grants. See the reason above.
RULE_READ: Final[Capability] = CLASSIFICATION_READ
RULE_WRITE: Final[Capability] = CLASSIFICATION_WRITE

#: What separates a department from a rule's own name in a stored id. Two underscores, which the
#: department slug grammar cannot hold, so the department a stored id names is unambiguous.
DEPARTMENT_SEPARATOR: Final = "__"

#: What the routes say, in sentences a person reads.
NO_SUCH_RULE: Final = "There is no live rule by that name that you may change."
NOT_YOUR_DEPARTMENT: Final = "You may not write rules for that department."
ADDED: Final = "The rule is live and answers from the next question."
NOT_ADDED_TAKEN: Final = (
    "The rule was not added: a live rule here already has that name or those words."
)
NOT_ADDED_INVALID: Final = (
    "The rule was not added: it needs one {slot} in its words, the slot's name between the "
    "braces, enough words around it, and names of letters, digits and underscores."
)
RETIRED: Final = "The rule is retired and answers nothing from the next question."
TEST_MATCHED: Final = "The question matches the rule's words."
TEST_DID_NOT_MATCH: Final = "The question does not match the rule's words, so it would not answer."
TEST_ANSWERED: Final = "The rule would answer this question with no model."
TEST_NOTHING: Final = (
    "The rule matches but would answer nothing at your reach: either nothing has that name or "
    "you may not read the answer."
)
THE_RULES_LIST: Final = (
    "Rules answer a question in exactly these words from records, with no model. A department's "
    "rule answers its own people only, and a rule with no department answers everyone."
)


# ------------------------------------------------------------------------- the shapes
class FastRuleAsked(BaseModel):
    """A rule as an administrator writes it: a name, its place, its words and where it reads."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=60, pattern=OBJECT_NAME_PATTERN)
    #: The department whose askers it answers, or None for the whole install.
    department: str | None = Field(default=None, min_length=2, max_length=60, pattern=SLUG_PATTERN)
    template: str = Field(min_length=MIN_TEMPLATE_CHARS, max_length=MAX_TEMPLATE_CHARS)
    slot: str = Field(min_length=1, max_length=60, pattern=OBJECT_NAME_PATTERN)
    source: str = Field(min_length=1, max_length=60, pattern=OBJECT_NAME_PATTERN)
    entity: str = Field(min_length=1, max_length=60, pattern=OBJECT_NAME_PATTERN)
    match_field: str = Field(min_length=1, max_length=60, pattern=OBJECT_NAME_PATTERN)
    answer_field: str = Field(min_length=1, max_length=60, pattern=OBJECT_NAME_PATTERN)


class FastRuleTried(FastRuleAsked):
    """A candidate rule and a question to ask it, which nothing saves."""

    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)


class FastRuleView(BaseModel):
    """One live rule as the Rules page draws it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: str
    department: str | None
    template: str
    slot: str
    source: str
    entity: str
    match_field: str
    answer_field: str
    created_by: str
    created_at: datetime


class FastRulesView(BaseModel):
    """The rules this reader may see, and where they may write one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rules: list[FastRuleView]
    #: The reader's own department, which the form offers first, or None.
    own_department: str | None
    #: Whether the reader may write a rule the whole install asks with.
    may_write_install: bool
    told: str


class FastRuleWritten(BaseModel):
    """What an addition or a retirement came to, and the one sentence a person is told."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    done: bool
    rule_id: str | None
    told: str


class FastRuleTrial(BaseModel):
    """What a candidate rule would do with one question, at the tester's reach."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    matches: bool
    answer: str | None
    told: str


# ------------------------------------------------------------------------- the decisions
def place_of(department: str | None) -> Mapping[str, str]:
    """Where a rule sits, as a grant's scope is matched against it."""
    return NOWHERE if department is None else {"department": department}


def may_read_at(reach: EntitlementSet, department: str | None, now: datetime | None) -> bool:
    """Whether this reader's read grant admits a rule at this place."""
    return _in_reach(reach, RULE_READ, place_of(department), now)


def may_write_at(reach: EntitlementSet, department: str | None, now: datetime | None) -> bool:
    """Whether both grants admit a rule at this place: a change is read and written there."""
    where = place_of(department)
    return _in_reach(reach, RULE_READ, where, now) and _in_reach(reach, RULE_WRITE, where, now)


def stored_id(department: str | None, name: str) -> str | None:
    """The id a rule is kept under, or None for a name that cannot be kept at that place.

    A department's rule is `<department>__<name>`; an install-wide rule is its name, which may not
    hold the separator, so no install-wide id can be read as a department's. See
    `A_RULE_OUT_OF_REACH_IS_A_RULE_THAT_DOES_NOT_EXIST`.
    """
    if DEPARTMENT_SEPARATOR in name:
        return None
    return name if department is None else f"{department}{DEPARTMENT_SEPARATOR}{name}"


def candidate(asked: FastRuleAsked) -> FastPathRule | None:
    """The rule an administrator wrote, through the validator every stored rule passes."""
    rule_id = stored_id(asked.department, asked.name)
    if rule_id is None:
        return None
    row = {
        "rule_id": rule_id,
        "template": asked.template,
        "slot": asked.slot,
        "source": asked.source,
        "entity": asked.entity,
        "match_field": asked.match_field,
        "answer_field": asked.answer_field,
    }
    try:
        [rule] = rules_from_rows([row])
    except FastLaneError:
        return None
    return rule


def view_of(kept: KeptRule) -> FastRuleView:
    return FastRuleView(
        rule_id=kept.rule.rule_id,
        department=kept.department,
        template=kept.rule.template,
        slot=kept.rule.slot,
        source=kept.rule.source,
        entity=kept.rule.entity,
        match_field=kept.rule.match_field,
        answer_field=kept.rule.answer_field,
        created_by=kept.created_by,
        created_at=kept.created_at,
    )


def readable(
    kept: Sequence[KeptRule], reach: EntitlementSet, now: datetime | None
) -> list[FastRuleView]:
    """The rules at places this reader's read grant admits, and no others."""
    return [view_of(one) for one in kept if may_read_at(reach, one.department, now)]


async def added(
    rules: StoredRules,
    asked: FastRuleAsked,
    *,
    reach: EntitlementSet,
    writer: Writer,
    now: datetime,
) -> FastRuleWritten:
    """Write one rule at a place this administrator may write, answered in one sentence."""
    if not may_write_at(reach, asked.department, now):
        raise Denied("rule place out of reach", public_message=NOT_YOUR_DEPARTMENT)
    rule = candidate(asked)
    if rule is None:
        return FastRuleWritten(done=False, rule_id=None, told=NOT_ADDED_INVALID)
    if not await rules.add(rule, department=asked.department, writer=writer):
        return FastRuleWritten(done=False, rule_id=None, told=NOT_ADDED_TAKEN)
    return FastRuleWritten(done=True, rule_id=rule.rule_id, told=ADDED)


async def retired(
    rules: StoredRules, rule_id: str, *, reach: EntitlementSet, writer: Writer, now: datetime
) -> FastRuleWritten:
    """Retire one live rule this administrator may write; one refusal for any other id."""
    found = next((one for one in await rules.live() if one.rule.rule_id == rule_id), None)
    if found is None or not may_write_at(reach, found.department, now):
        raise Absent("no live rule in reach", public_message=NO_SUCH_RULE)
    if not await rules.retire(rule_id, writer=writer):
        raise Absent("rule retired meanwhile", public_message=NO_SUCH_RULE)
    return FastRuleWritten(done=True, rule_id=rule_id, told=RETIRED)


async def tried(
    state: Any, asked: FastRuleTried, *, reach: EntitlementSet, now: datetime
) -> FastRuleTrial:
    """What the candidate rule would answer to this question, at the tester's reach, saved nowhere.

    See `A_TEST_IS_THE_LANE_AT_THE_TESTERS_OWN_REACH`.
    """
    if not may_write_at(reach, asked.department, now):
        raise Denied("rule place out of reach", public_message=NOT_YOUR_DEPARTMENT)
    rule = candidate(asked)
    if rule is None:
        return FastRuleTrial(matches=False, answer=None, told=NOT_ADDED_INVALID)
    readers, policies, source_policies = await lane_wiring_of(state)
    served = entities_served(readers) | {(rule.source, rule.entity)}
    if match_rule(asked.question, (rule,), served=served) is None:
        return FastRuleTrial(matches=False, answer=None, told=TEST_DID_NOT_MATCH)
    found = await respond(
        asked.question, rules=(rule,), readers=readers, entitlement=reach, now=now
    )
    sentence = ""
    if isinstance(found, FastLaneAnswer):
        policy = policy_for(found, policies, source_policies)
        if policy is not None:
            payload = redact(found.result, entitlement=reach, policy=policy, now=now).payload
            sentence = served_from(found, payload)
    if not sentence:
        return FastRuleTrial(matches=True, answer=None, told=TEST_NOTHING)
    return FastRuleTrial(matches=True, answer=sentence, told=TEST_ANSWERED)


async def lane_wiring_of(state: Any) -> tuple[Any, Any, Any]:
    """The readers and classifications the answer route hands the fast lane, built as it does.

    `brain.api_routes.answered_for`'s own sources: the registry's readers and policies, the
    uploaded tables' and a switched-on Lark Base's. Imported here rather than at the top because
    those helpers import the routes the answer route mounts.
    """
    from brain.api_routes import (
        base_lane_of,
        field_policies,
        row_readers,
        source_field_policies,
    )
    from brain.ops.classification_store import classified_lane_of
    from brain.tools.registry import ToolRegistry

    registry = getattr(state, "tools", None)
    if not isinstance(registry, ToolRegistry):
        raise Failed("no tool registry on this process")
    tables = await classified_lane_of(state)
    base = await base_lane_of(state)
    readers = {**row_readers(registry), **tables.readers, **base.readers}
    policies = {**field_policies(registry), **tables.policies, **base.policies}
    source_policies = {**source_field_policies(registry), **base.source_policies}
    return readers, policies, source_policies


def writer_of(asked: Asking) -> Writer:
    """The caller the gate resolved, their reach and the request's trace, as the rule's author."""
    return Writer(
        actor_id=asked.caller.principal.id,
        ent_hash=asked.reach.ent_hash(),
        trace_id=trace_of_request(),
    )


# ------------------------------------------------------------------------- the routes
RULES_PATH: Final = "/rules"

router = APIRouter(prefix=API_PREFIX, tags=["rules"])


def _store(request: Request) -> StoredRules:
    sessions = getattr(request.app.state, "db_sessions", None)
    if not isinstance(sessions, async_sessionmaker):
        raise Failed("no database on this process")
    return StoredRules(sessions)


def _gate(asked: Asking, capability: Capability) -> None:
    """The grant held somewhere at all, before anything is read. One refusal for everybody else."""
    if not asked.reach.holds(capability, asked.now):
        log.info("rules screen not answerable", principal=asked.caller.principal.id)
        raise Denied("no rule grant", public_message=NO_SUCH_RULE)


@router.get(RULES_PATH, response_model=FastRulesView, responses=COMMON_RESPONSES)
async def my_rules(request: Request, asked: Asked) -> FastRulesView:
    """The live rules at every place this reader's read grant admits."""
    _gate(asked, RULE_READ)
    kept = await _store(request).live()
    return FastRulesView(
        rules=readable(kept, asked.reach, asked.now),
        own_department=asked.caller.principal.primary_department,
        may_write_install=may_write_at(asked.reach, None, asked.now),
        told=THE_RULES_LIST,
    )


@router.post(RULES_PATH, response_model=FastRuleWritten, responses=COMMON_RESPONSES)
async def add_rule(request: Request, body: FastRuleAsked, asked: Asked) -> FastRuleWritten:
    """Add one rule at a place this administrator may write. Live from the next question."""
    _gate(asked, RULE_WRITE)
    written = await added(
        _store(request), body, reach=asked.reach, writer=writer_of(asked), now=asked.now
    )
    log.info("rule added" if written.done else "rule not added", rule=written.rule_id)
    return written


@router.post(f"{RULES_PATH}/test", response_model=FastRuleTrial, responses=COMMON_RESPONSES)
async def try_rule(request: Request, body: FastRuleTried, asked: Asked) -> FastRuleTrial:
    """What a candidate rule would answer to one question at the tester's reach, saved nowhere."""
    _gate(asked, RULE_WRITE)
    return await tried(request.app.state, body, reach=asked.reach, now=asked.now)


@router.post(
    f"{RULES_PATH}/{{rule_id}}/retire", response_model=FastRuleWritten, responses=COMMON_RESPONSES
)
async def retire_rule(request: Request, rule_id: str, asked: Asked) -> FastRuleWritten:
    """Retire one live rule this administrator may write. Gone from the next question."""
    _gate(asked, RULE_WRITE)
    written = await retired(
        _store(request), rule_id, reach=asked.reach, writer=writer_of(asked), now=asked.now
    )
    log.info("rule retired", rule=rule_id)
    return written
