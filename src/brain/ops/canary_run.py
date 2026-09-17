"""The permission canaries, run on an install as every reach it holds, and what a run found.

`brain.ops.canaries` holds the checks and runs nothing, and says the production run is a
caller's job. `brain.ops.schedule_runner` recorded what that caller needed: the askers
`compare_askers` compares, as live entitlement sets, and something for them to be compared over.
This is both, and the half that talks to PostgreSQL and the answer lane.

**The askers are the reaches this install actually holds, and not one of them is an account.**
Every live principal's reach is loaded through `brain.gate.entitlement_store.StoredEntitlements`,
which is the one resolver, and the run asks once per distinct reach, told apart by
`EntitlementSet.ent_hash`. One more asker is added: a principal id the directory does not hold,
loaded through the same store, which must come back holding nothing. That is the synthetic asker,
and it is synthetic in the only way an install permits. Writing a canary principal and its grants
into the directory is refused twice over already: `brain.ops.starter` refuses to ship an account
nobody created, and `brain.ops.canaries.PRODUCTION_NEVER_PLANTS_A_CANARY` refuses to write a
planted value into a client's records. See `A_CANARY_IS_A_REACH_AND_NEVER_AN_ACCOUNT`.

**Nothing is recorded in anybody's name.** The lane is handed no recorders, so a canary question
reaches neither the question ledger nor the metadata ledger, and nobody's adoption figure moves
because the canaries ran. The reach is the nominal one the resolver returns, not narrowed by a
channel or an assurance ceiling, because that is the widest a request from that person can be
answered at, and a leak only a narrower ceiling hides is still a leak in the model.

**Two halves, and they are the two `PRODUCTION_NEVER_PLANTS_A_CANARY` names.**

The projection: every reach is offered, by `brain.gate.catalogue.project` under a ceiling that
narrows nothing, exactly the tools its grants admit. For the asker who holds nothing the answer is
known without asking the model, since it is admitted to nothing, so a resolver that handed an
unknown principal a grant is caught against a fact outside the system. For a live reach the model
is the only statement of what it admits, so that half catches the projection drifting from the
model and not the model being wrong, which is the fixture suite's.

The refusal: every loaded answer rule is asked about a value nothing holds, a word minted per run,
at every reach, and every reach must receive byte for byte what the asker holding nothing receives.
A reach that reads the entity gets a genuine absence and a reach that does not gets a refusal, and
the two are the same frames or DENIED and ABSENT have come apart. The value is never written
anywhere, so nothing is planted. See `A_VALUE_NOTHING_HOLDS_IS_ASKED_AND_NEVER_WRITTEN`.

**The lane is handed no reachable sources, and that is the one input made uniform on purpose.**
The scope statement is derived from reach, so it differs between two readers by design and
`brain.gate.abstain.SearchScope` argues why that is safe. Comparing frames that carry it would
report every pair of different reaches as distinguishable. Handing every asker none removes the
one difference that is meant to be there and leaves every other. See
`THE_SCOPE_STATEMENT_DIFFERS_BY_REACH_ON_PURPOSE_SO_IT_IS_LEFT_OUT`.

**A red run raises, so the attempt table records it as failed, and what it found goes only to the
alert.** `brain.ops.worker.start_owed` records a runner that returns as `ok` and one that raises as
`failed`, with the exception's text as the stored detail. So `CanariesFoundError` says in its text
that the canaries found something and names nothing, and carries the alert lines beside it; the
lines name the field, tool or rule and the asker, which is what somebody on call can act on, and
they are written to the operator's stream before the raise. `ops.control_run.detail` is read by more
screens and kept for longer than an alert, and a field name there is the listing of the schema
`brain.console.operate.findings_in_reach` exists to filter. See
`A_RED_RUN_IS_RECORDED_FAILED_AND_ITS_SUBJECTS_REACH_ONLY_THE_ALERT`.

Rejected: sampling the reaches, or capping how many are asked. A cap is a pass that checked some of
the install and reads as a pass that checked all of it. A reach is one row read per rule, twice a
day, and an install with more distinct reaches than that can afford has a grant model nobody can
review either.

Rejected: reading a real record's value so a refusal could be compared against something that
exists. It would be the run reading client data outside any person's reach in order to test who
may read it, and the refusal half above already catches the shape of defect this lane has
actually had: a step or a sentence that depends on whether a read happened.

Task ids: M28.2.4, M27.7.19
"""

from __future__ import annotations

import asyncio
import secrets
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, TextIO

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.api_routes import field_policies, row_readers
from brain.core.entitlement import Capability, EntitlementSet
from brain.core.envelope import SideEffect, ToolDefinition
from brain.core.field_policy import FieldPolicy
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.gate.answer import answer_lane
from brain.gate.catalogue import AgentCeiling, project
from brain.gate.context import Channel
from brain.gate.entitlement_store import StoredEntitlements
from brain.gate.fast_lane import FastPathRule, RowReader
from brain.gate.finish import Origin
from brain.gate.rule_store import load_rules
from brain.knowledge.row_store import SessionRowSource
from brain.ops.canaries import CanaryFinding, alert_lines, compare_askers, projection_findings
from brain.ops.trace_sink import CountingTraceSink
from brain.session import make_app_engine, make_session_factory
from brain.tables.identity import PrincipalRow
from brain.tools.startup import build_registry

# ------------------------------------------------------------------ written-down reasons
#: Why no canary is an account.
A_CANARY_IS_A_REACH_AND_NEVER_AN_ACCOUNT: Final = (
    "A synthetic user with grants is a principal in the client's directory that nobody created, "
    "holding access nobody approved, and brain.ops.starter refuses to ship one. So the canaries "
    "ask as the reaches the install already holds, loaded through the one resolver, and add "
    "one asker the directory does not hold, who must be loaded as holding nothing. No row is "
    "written for either, and nothing is recorded in anybody's name."
)

#: Why the refusal half plants nothing.
A_VALUE_NOTHING_HOLDS_IS_ASKED_AND_NEVER_WRITTEN: Final = (
    "Every answer rule is asked about a word minted for this run, which no record holds. A "
    "reach that reads the entity is told nothing was found and a reach that does not is "
    "refused, and the two must be the same frames. The word is put in a question and nowhere "
    "else, so the run plants no value in a client's records."
)

#: Why every asker is handed no reachable sources.
THE_SCOPE_STATEMENT_DIFFERS_BY_REACH_ON_PURPOSE_SO_IT_IS_LEFT_OUT: Final = (
    "The sentence saying what an answer covered is derived from the asker's reach, so two "
    "reaches receive two sentences by design. Comparing frames that carried it would report "
    "every pair of different reaches. Every canary asker is handed no reachable sources, which "
    "removes that one intended difference and leaves every other."
)

#: Why a red run raises and where its subjects go.
A_RED_RUN_IS_RECORDED_FAILED_AND_ITS_SUBJECTS_REACH_ONLY_THE_ALERT: Final = (
    "The worker records a runner that returns as ok and one that raises as failed, keeping the "
    "exception's text as the run's detail. A run that found something returning normally would "
    "be recorded ok, which is a green light over a leak. So it raises, the text it raises with "
    "names nothing, and the lines naming the asker and the field, tool or rule are written to "
    "the operator's stream before it does. The detail column is read by more screens and kept "
    "longer than an alert, and a field name in it is a listing of the schema."
)

#: The principal id of the asker the directory does not hold.
#:
#: Not a value any sign-in mints: `brain.identity.sign_in_binding` binds a subject to a principal
#: an administrator already made, and nothing makes principals with this shape. Were an install to
#: hold one, the resolver would hand it that principal's grants, the projection half would find
#: the asker offered tools it cannot hold, and the run would be red with this id in the alert,
#: which is where somebody would find out.
NOBODY: Final = "canary-holds-nothing"

#: The trace a canary question is asked under. Nothing records it, since the lane is handed no
#: recorders; `Origin` still refuses a trace id the audit ledger would not accept.
CANARY_TRACE: Final = "canary-run"

#: What the agent term of a canary's projection is called. A ceiling that narrows nothing, so the
#: projection measured is the caller's own.
CANARY_AGENT: Final = "permission-canary"

#: The text a red run is raised with, which is what the attempt table keeps. Names nothing.
RED_RUN_DETAIL: Final = (
    "the permission canaries found a defect. What they found was written to the alert and is "
    "not kept here"
)

#: The text a run that could not finish is raised with, for the same reason. Names nothing.
UNFINISHED_RUN_DETAIL: Final = (
    "the permission canaries could not finish. Why was written to the alert and is not kept here"
)

#: How a canary line is marked on the operator's stream, beside the worker's own failure line.
ALERT_PREFIX: Final = "  ! canary_run"

#: The minted word's own prefix. Two letters no English word starts a hex run with, so a word the
#: run minted is recognisable in a slow-query log and cannot be read as a qualifier.
ABSENT_VALUE_PREFIX: Final = "QZ"


class CanaryRunError(Exception):
    """The canaries could not finish. Its text names nothing; see `UNFINISHED_RUN_DETAIL`."""


class CanariesFoundError(Exception):
    """A run found something. Its text names nothing and its lines are for the alert only.

    `alert` is carried beside the message rather than in it, so `str()` of this exception, which
    is what `brain.ops.worker.start_owed` keeps as a failed run's detail, cannot carry a subject.
    """

    def __init__(self, alert: Sequence[str]) -> None:
        super().__init__(RED_RUN_DETAIL)
        self.alert: tuple[str, ...] = tuple(alert)


@dataclass(frozen=True)
class CanaryRun:
    """What one run found, and which rules it asked.

    `rules_asked` is carried so a run that loaded no answer rule says it compared no refusal,
    rather than passing in words that sound like it did.
    """

    findings: tuple[CanaryFinding, ...]
    rules_asked: tuple[str, ...]


# --------------------------------------------------------------------------- the askers
def distinct_reaches(
    loaded: Iterable[EntitlementSet], *, nobody: EntitlementSet
) -> tuple[EntitlementSet, ...]:
    """The asker holding nothing first, then one reach per distinct entitlement set.

    Distinct by `ent_hash`, which leaves the principal out, so two people holding the same grants
    are one asker and the first by id names it. A reach identical to the one holding nothing is
    that asker already and is not asked twice. The nobody asker is kept whatever it holds: that is
    what the projection half judges it on.
    """
    seen = {nobody.ent_hash()}
    found = [nobody]
    for one in sorted(loaded, key=lambda reach: reach.principal_id):
        digest = one.ent_hash()
        if digest in seen:
            continue
        seen.add(digest)
        found.append(one)
    return tuple(found)


async def reaches_on_this_install(
    sessions: async_sessionmaker[AsyncSession], *, now: datetime
) -> tuple[EntitlementSet, ...]:
    """Every live principal's reach through the one resolver, and the asker holding nothing.

    Live is not disabled and not deleted, filtered in the statement and not left to a policy, for
    `brain.identity.principal_directory`'s reason: a connection that is not the application role
    bypasses the policy. The resolver refuses both a grant anyway, so the filter spends no load on
    a principal who would come back empty.
    """
    async with sessions() as session:
        ids = (
            (
                await session.execute(
                    select(PrincipalRow.id)
                    .where(PrincipalRow.deleted_at.is_(None), PrincipalRow.disabled_at.is_(None))
                    .order_by(PrincipalRow.id)
                )
            )
            .scalars()
            .all()
        )
    store = StoredEntitlements(sessions)
    loaded = [await store.load(one, now) for one in ids if one != NOBODY]
    return distinct_reaches(loaded, nobody=await store.load(NOBODY, now))


# ----------------------------------------------------------------------- the projection
def admitted(reach: EntitlementSet, tool: ToolDefinition, now: datetime) -> bool:
    """Whether the entitlement model admits this reach to this tool, asked of the reach alone.

    An unparseable requirement admits nobody, which is the projection's own rule and the safe
    reading of a typo.
    """
    try:
        needed = Capability(value=tool.required_capability)
    except ValueError:
        return False
    return reach.holds(needed, now)


def projection_check(
    reach: EntitlementSet, definitions: Sequence[ToolDefinition], *, now: datetime
) -> tuple[CanaryFinding, ...]:
    """The tools this reach is offered against the tools it holds, both directions.

    For the asker holding nothing the admissible set is empty by definition and is not asked of
    the reach at all, so a resolver that handed it a grant is caught against a fact the system did
    not supply.
    """
    ceiling = AgentCeiling(
        agent_id=CANARY_AGENT,
        allowed_tools=frozenset(one.name for one in definitions),
        max_side_effect=SideEffect.MONEY,
    )
    offered = project(definitions, reach, ceiling, now=now).names
    admissible = (
        ()
        if reach.principal_id == NOBODY
        else tuple(one.name for one in definitions if admitted(reach, one, now))
    )
    return projection_findings(asker=reach.principal_id, offered=offered, admissible=admissible)


# -------------------------------------------------------------------------- the refusal
def absent_question(rule: FastPathRule, value: str) -> str:
    """The rule's own question, with the minted value where the slot is."""
    return rule.template.replace("{" + rule.slot + "}", value)


def minted_value() -> str:
    """A word no record holds, minted per run.

    See `A_VALUE_NOTHING_HOLDS_IS_ASKED_AND_NEVER_WRITTEN`.
    """
    return f"{ABSENT_VALUE_PREFIX}{secrets.token_hex(5).upper()}"


async def said_to(
    question: str,
    reach: EntitlementSet,
    *,
    rules: Sequence[FastPathRule],
    readers: Mapping[tuple[str, str], RowReader],
    policies: Mapping[str, FieldPolicy],
    now: datetime,
) -> str | None:
    """Every frame one reach receives for one question, joined, or None when the lane raised.

    A raise for one reach and frames for another is a refusal that differs from an absence by
    being a fault, so it is kept as None for `compare_askers` to report rather than stopping the
    run. No recorders and no reachable sources: see the module docstring.
    """
    origin = Origin(
        trace_id=CANARY_TRACE,
        principal=Principal(
            id=reach.principal_id,
            kind=PrincipalKind.SERVICE,
            employment=Employment.SERVICE,
            display_name="Permission canary",
        ),
        channel=Channel.SCHEDULER,
    )
    try:
        answered = await answer_lane(
            question,
            origin=origin,
            recorders=(),
            rules=rules,
            readers=readers,
            entitlement=reach,
            policies=policies,
            reachable_sources=(),
            sink=CountingTraceSink(),
            now=now,
            clock=lambda: now,
        )
    except Exception:
        # Broad on purpose: whatever one reach raised is a difference between reaches, and the
        # finding says so without carrying the exception's text anywhere.
        return None
    return "".join(answered.frames)


def refusal_check(rule_id: str, said: Mapping[str, str | None]) -> tuple[CanaryFinding, ...]:
    """Every reach's frames against what the asker holding nothing received.

    Every reach is compared, the holder of nothing included: when its own answer is missing there
    is no refusal to compare with, and each reach, that asker first, is reported as having no
    answer rather than the check passing over an empty sentence.
    """
    absence = said.get(NOBODY)
    return compare_askers(
        question_id=rule_id,
        answers={} if absence is None else {k: v for k, v in said.items() if v is not None},
        refused=said.keys(),
        absence_text="" if absence is None else absence,
    )


async def ask_every_reach(
    reaches: Sequence[EntitlementSet],
    *,
    definitions: Sequence[ToolDefinition],
    rules: Sequence[FastPathRule],
    readers: Mapping[tuple[str, str], RowReader],
    policies: Mapping[str, FieldPolicy],
    now: datetime,
    value: str,
) -> CanaryRun:
    """Both halves, over reaches, tools and rules already in hand. Reads nothing itself."""
    if not reaches or reaches[0].principal_id != NOBODY:
        msg = (
            "a canary run with no asker holding nothing has no refusal to compare with and no "
            "projection it can judge against a fact of its own"
        )
        raise CanaryRunError(msg)
    findings: list[CanaryFinding] = []
    for reach in reaches:
        findings.extend(projection_check(reach, definitions, now=now))
    for rule in sorted(rules, key=lambda one: one.rule_id):
        question = absent_question(rule, value)
        said = {
            reach.principal_id: await said_to(
                question, reach, rules=rules, readers=readers, policies=policies, now=now
            )
            for reach in reaches
        }
        findings.extend(refusal_check(rule.rule_id, said))
    return CanaryRun(
        findings=tuple(findings), rules_asked=tuple(sorted(one.rule_id for one in rules))
    )


async def run_canaries(
    sessions: async_sessionmaker[AsyncSession], *, tool_source: str, now: datetime, value: str
) -> CanaryRun:
    """The registry, the rules and the reaches, built the way the application builds them.

    `build_registry` over `SessionRowSource`, `load_rules`, and `row_readers` and `field_policies`
    from `brain.api_routes`, which are what the answer route hands the lane, so the canaries ask
    the lane an asker reaches and not a copy assembled here.
    """
    registry = build_registry(source=tool_source, records=SessionRowSource(sessions))
    rules = await load_rules(sessions)
    reaches = await reaches_on_this_install(sessions, now=now)
    return await ask_every_reach(
        reaches,
        definitions=registry.definitions(),
        rules=rules,
        readers=row_readers(registry),
        policies=field_policies(registry),
        now=now,
        value=value,
    )


# --------------------------------------------------------------------------- the verdict
def verdict(run: CanaryRun) -> str:
    """The detail a green run is recorded with, or `CanariesFoundError` for a red one.

    The detail says what was compared and no count of anything. See
    `A_RED_RUN_IS_RECORDED_FAILED_AND_ITS_SUBJECTS_REACH_ONLY_THE_ALERT`.
    """
    if run.findings:
        raise CanariesFoundError(alert_lines(run.findings))
    if not run.rules_asked:
        return (
            "passed on the projection alone: every reach was offered exactly the tools it holds, "
            "and no answer rule is loaded, so no refusal was compared"
        )
    return (
        "passed: every reach was offered exactly the tools it holds, and every answer rule asked "
        "about a value nothing holds was answered identically at every reach"
    )


def raise_the_alert(lines: Iterable[str], stream: TextIO | None = None) -> None:
    """Write each line to the operator's stream, beside the worker's own failure line."""
    out = sys.stderr if stream is None else stream
    for line in lines:
        print(f"{ALERT_PREFIX} {line}", file=out)


def run_canaries_now(
    database_url: str,
    *,
    now: datetime,
    tool_source: str,
    loop_factory: Callable[[], asyncio.AbstractEventLoop] | None = None,
    value: str | None = None,
    stream: TextIO | None = None,
) -> str:
    """`run_canaries` from a thread with no event loop of its own, and its verdict.

    The shape `brain.knowledge.item_store.run_reverification_now` takes. A red run writes its
    lines to the alert and raises `CanariesFoundError`; a run that could not finish writes why to
    the alert and raises `CanaryRunError`, whose text names nothing either, because an exception
    from a database or a reader can quote a column.
    """

    async def once() -> CanaryRun:
        engine = make_app_engine(database_url)
        try:
            return await run_canaries(
                make_session_factory(engine),
                tool_source=tool_source,
                now=now,
                value=minted_value() if value is None else value,
            )
        finally:
            await engine.dispose()

    try:
        run = asyncio.run(once(), loop_factory=loop_factory)
    except Exception as exc:
        raise_the_alert((f"could not finish: {type(exc).__name__}: {exc}",), stream)
        raise CanaryRunError(UNFINISHED_RUN_DETAIL) from exc
    try:
        return verdict(run)
    except CanariesFoundError as red:
        raise_the_alert(red.alert, stream)
        raise
