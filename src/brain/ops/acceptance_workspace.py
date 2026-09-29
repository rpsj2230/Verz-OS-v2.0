"""The install acceptance checks for one agent's page: what it is built from, and its figures.

Each check drives the functions the agent page's routes call, in the order they call them,
against the install's own database: the workspace route's `install_for`, `install_of` and
`tab_strip`; the stats route's `agent_requests`, `spend_for`, `agent_period_views` and
`projection_view`; and the budget route's `may_set_budget` and `write_budget`. Every row a check
writes is in its rolled-back transaction, in acceptance_a, for an agent named for the run.

**The agent is installed from a template the check signs with a key it makes**, as
`brain.ops.acceptance_checks_skills._an_agent` installs one, with the three rows
`brain.agents.install_store.finish` writes. Rejected: publishing through the builder, which needs
the install's template key and a draft, neither of which says anything about the page.

**The figures are over rows the check writes where the product writes them.** A request is an
`obs.request_telemetry` row naming the agent as `selected_agent`, as the answer lane records one,
and a run's cost is an `ops.spend_actual` row, as `brain.ops.usage_store` records one. The check
never reads a row it did not write: every statement it runs is narrowed to the run's agent.

**Month to date is computed from the day the check runs.** The check's rows are placed relative
to its own clock, and what it expects of the month to date is worked out from the first of the
current month, so a check run on the first of a month and one run on the twentieth both hold.

Task ids: M38.5.1
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Mapping, Sequence
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import insert, text

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from pydantic import JsonValue

    from brain.agents.model import AgentRecord

A, B = RESERVED_DEPARTMENTS

# ------------------------------------------------------------------------ the figures
#: The persona the template ships, and the one the install changes it to.
TEMPLATE_PERSONA: Final = "Answers an install acceptance check and nobody else."
LOCAL_PERSONA: Final = "Answers an install acceptance check, as changed on this install."

#: The skill the template pins, by a digest the check computes over a body it never stores.
SKILL_NAME: Final = "acceptance-skill"

#: The connector the template declares.
CONNECTOR: Final = "acceptance_source"


def _everywhere(*capabilities: str) -> tuple[tuple[str, Scope], ...]:
    return tuple((one, Scope.unrestricted()) for one in capabilities)


def _planes() -> tuple[str, ...]:
    """Every console plane capability, so a reader's screen read is decided by the read alone."""
    from brain.console.reads import Plane, plane_capability

    return tuple(plane_capability(one).value for one in Plane)


async def installed_agent(
    h: Harness,
    owner: str,
    *,
    skills: Sequence[tuple[str, str]] = (),
    connectors: Sequence[str] = (),
    overlay: Mapping[str, JsonValue] | None = None,
) -> str:
    """An agent of acceptance_a installed from a template the check signs, with `overlay` set here.

    The three rows `brain.agents.install_store.finish` writes, from its own row builders, and the
    instance row field by field as `brain.ops.acceptance_checks_skills._an_agent` writes it.
    """
    from brain.agents.install_store import agent_values, version_values
    from brain.agents.model import AgentAudience
    from brain.agents.template import (
        ManifestAuthority,
        ManifestIdentity,
        SkillRef,
        TemplateManifest,
        install,
        materialise,
        publish,
    )
    from brain.knowledge.visibility import Visibility
    from brain.tables.agent import AgentRow
    from brain.tables.template import TemplateInstanceRow, TemplateVersionRow

    agent_id, key = f"acceptance_{h.run}", secrets.token_hex(32)
    signed = publish(
        TemplateManifest(
            identity=ManifestIdentity(
                template_id=agent_id,
                version=1,
                published_by=owner,
                display_name="Acceptance check template",
                summary="Answers the install's acceptance checks.",
            ),
            persona=TEMPLATE_PERSONA,
            skills=tuple(SkillRef(name=name, digest=digest) for name, digest in skills),
            connectors=tuple(connectors),
            authority=ManifestAuthority(scope=Scope.department(A)),
        ),
        key=key,
        signed_by=owner,
        at=h.now,
    )
    instance = install(
        signed, key=key, instance_id=agent_id, created_by=owner, at=h.now, overlay=overlay
    )
    effective = materialise(
        signed,
        instance,
        audience=AgentAudience(level=Visibility.DEPARTMENT, owner_id=owner, department=A),
    )
    await h.execute(
        *h.attributed(owner),
        insert(TemplateVersionRow).values(**version_values(signed)),
        insert(TemplateInstanceRow).values(
            id=agent_id,
            template_id=instance.template_id,
            template_version=instance.template_version,
            content_digest=instance.content_digest,
            overlay=dict(instance.overlay),
            field_owners={
                path: owned.model_dump(mode="json")
                for path, owned in instance.overlay_owners.items()
            },
            effective_document=dict(effective.document),
            effective_hash=effective.config_hash,
            created_by=owner,
        ),
        insert(AgentRow).values(**agent_values(effective.record)),
    )
    return agent_id


async def stored_agent(h: Harness, agent_id: str) -> AgentRecord:
    """The agent as the workspace route reads it back, through `record_of`."""
    from brain.agent_routes import one_agent, record_of

    async with h.sessions() as session:
        row = (await session.execute(one_agent(agent_id))).scalar_one_or_none()
    record = None if row is None else record_of(row)
    if record is None:
        raise CheckFailedError("the check's agent did not read back as an agent")
    return record


# --------------------------------------------- 1. what an agent is built from, and its diff
@check(
    leaves=("M39.1.1.2", "M39.1.1.4", "M39.1.1.5"),
    sentence=(
        "An agent installed on this install from a signed template pins its skill by digest and "
        "names its connector, and its stored install holds references and never a copy; the "
        "persona changed on the install is flagged as divergent and the composition diff sets "
        "the template's value beside the install's, marking which side each came from."
    ),
)
async def an_agent_pins_its_parts_and_its_diff_shows_local_changes(
    h: Harness,
) -> None:
    from brain.agent_routes import POPULATED_HERE, holds_settings, install_for, install_of
    from brain.console.workspace import Attachment, Part, WorkspaceError, tab_strip
    from brain.tables.template import TemplateInstanceRow

    await h.found_departments()
    steward = h.principal(A, "steward")
    await h.person(steward, department=A, grants=_everywhere("read:agent", *_planes()))
    digest = hashlib.sha256(f"{h.word()} body".encode()).hexdigest()
    agent_id = await installed_agent(
        h,
        steward,
        skills=((SKILL_NAME, digest),),
        connectors=(CONNECTOR,),
        overlay={"persona": LOCAL_PERSONA},
    )
    record = await stored_agent(h, agent_id)

    # The workspace route's own read: the install and the version it is pinned to.
    async with h.sessions() as session:
        pair = (await session.execute(install_for(agent_id))).one_or_none()
        stored = (
            await session.execute(
                text(
                    "SELECT effective_document -> 'skills' FROM agent.template_instance"
                    " WHERE id = :id"
                ).bindparams(id=agent_id)
            )
        ).scalar_one_or_none()
    if pair is None:
        raise CheckFailedError("the workspace route's install read found no install")
    instance_row, version_row = pair
    if not isinstance(instance_row, TemplateInstanceRow):
        raise CheckFailedError("the workspace route's install read returned no instance row")
    made = install_of(instance_row, version_row, record)
    if made is None:
        raise CheckFailedError("the check's install did not construct for the workspace")

    # M39.1.1.2: a reference with a pinned version, never an inline copy.
    if [(one.name, one.digest) for one in made.skills] != [(SKILL_NAME, digest)]:
        raise CheckFailedError("the install did not carry its skill pinned by digest")
    if made.connectors != (CONNECTOR,):
        raise CheckFailedError("the install did not carry the connector its template names")
    if not isinstance(stored, list) or [sorted(one) for one in stored] != [["digest", "name"]]:
        raise CheckFailedError("a stored skill attachment held more than its name and digest")
    try:
        Attachment(part=Part.SKILLS, ref=SKILL_NAME, version="latest")
    except WorkspaceError:
        pass
    else:
        raise CheckFailedError("an attachment pinned to a moving version was accepted")

    # M39.1.1.4: the part the install changed is flagged, and a part it did not change is not.
    if made.divergent != (Part.PERSONA.value,):
        raise CheckFailedError("the divergence flag did not name exactly the changed persona")

    # M39.1.1.5: the diff, side by side, with each side's source.
    rows = {one.path: one for one in made.composition}
    persona, skills = rows.get("persona"), rows.get("skills")
    if persona is None or skills is None:
        raise CheckFailedError("the composition diff left out the persona or the skills")
    if (persona.template, persona.instance) != (f'"{TEMPLATE_PERSONA}"', f'"{LOCAL_PERSONA}"'):
        raise CheckFailedError("the diff did not set the template's persona beside this one")
    if persona.source != "instance" or skills.source != "template":
        raise CheckFailedError("the diff did not say which side each value came from")
    if skills.template != skills.instance:
        raise CheckFailedError("an unchanged part differed between the diff's two sides")

    # The diff travels with the Settings tab, which a reader of the agent's configuration holds.
    reach = await h.reach(steward)
    if not holds_settings(tab_strip(reach, populated=POPULATED_HERE, now=h.now)):
        raise CheckFailedError("a reader of agents was not given the Settings tab the diff is on")


# ------------------------------------------- 2. the figures and the month against a budget
def _spend(agent_id: str, principal: str, cost: int, at: Any, trace: str) -> dict[str, Any]:
    from brain.core.lane import Lane
    from brain.gate.context import TrafficClass

    return {
        "principal_id": principal,
        "principal_kind": "human",
        "traffic": TrafficClass.HUMAN_INTERACTIVE.value,
        "department": A,
        "agent_id": agent_id,
        "model": "acceptance-model",
        "lane": Lane.ANSWER.value,
        "cost_minor": cost,
        "at": at,
        "trace_id": trace,
    }


def _request(agent_id: str, principal: str, at: Any, traffic: str, trace: str) -> dict[str, Any]:
    from brain.core.lane import Lane
    from brain.ops.telemetry import RequestStatus

    return {
        "received_at": at,
        "trace_id": trace,
        "traffic_class": traffic,
        "principal": principal,
        "entitlement_hash": "0" * 32,
        "lane": Lane.ANSWER.value,
        "cache_hit": False,
        "status": RequestStatus.ANSWERED.value,
        "duration_ms": 1.0,
        "selected_agent": agent_id,
    }


@check(
    leaves=("M39.1.3.1", "M39.1.3.2", "M39.1.3.3", "M39.1.3.4"),
    sentence=(
        "An agent's spend, runs and messages are counted over seven, thirty and ninety days and "
        "the month to date, an automation's run counting as a run and not a message; its cost is "
        "named per person, heaviest first, to a reader of everybody's spend and only as their own "
        "to anybody else; and its month projects against a monthly budget its department's budget "
        "administrator set, which a member cannot set."
    ),
)
async def an_agents_figures_follow_the_period_and_project_to_its_budget(
    h: Harness,
) -> None:
    from brain.agent_routes import actual_of, spend_for, steward_names
    from brain.agent_workspace_routes import BUDGET_AUTHORITY, may_set_budget, write_budget
    from brain.console.entity_stats import agent_periods, earliest
    from brain.console.workspace import Basis, Range, basis_for, window
    from brain.console_stats_routes import _agent_runs, agent_period_views, projection_view
    from brain.gate.context import TrafficClass
    from brain.ops.spend import Actual
    from brain.tables.spend import SpendActualRow
    from brain.tables.telemetry import RequestTelemetryRow

    await h.found_departments()
    heavy, light, budgeter = (
        h.principal(A, "heavy"),
        h.principal(A, "light"),
        h.principal(A, "budget"),
    )
    await h.person(heavy, department=A)
    await h.person(light, department=A)
    await h.person(
        budgeter,
        department=A,
        grants=(
            *_everywhere("read:budget", "read:usage", *_planes()),
            (BUDGET_AUTHORITY.value, Scope.department(A)),
        ),
    )
    agent_id = await installed_agent(h, heavy)
    record = await stored_agent(h, agent_id)

    person, scheduled = TrafficClass.HUMAN_INTERACTIVE.value, TrafficClass.AUTOMATION.value
    requests = [
        (heavy, h.now - timedelta(hours=1), person),
        (light, h.now - timedelta(hours=2), person),
        (heavy, h.now - timedelta(hours=3), scheduled),
        (heavy, h.now - timedelta(days=45), person),
    ]
    spends = [
        (heavy, 300, h.now - timedelta(hours=1)),
        (light, 100, h.now - timedelta(hours=2)),
        (heavy, 50, h.now - timedelta(days=60)),
    ]
    async with h.sessions() as session:
        await session.execute(
            insert(RequestTelemetryRow),
            [
                _request(agent_id, who, at, traffic, f"{h.trace_id}-q{n}")
                for n, (who, at, traffic) in enumerate(requests)
            ],
        )
        await session.execute(
            insert(SpendActualRow),
            [
                _spend(agent_id, who, cost, at, f"{h.trace_id}-s{n}")
                for n, (who, cost, at) in enumerate(spends)
            ],
        )
        await session.commit()

    reader = await h.reach(budgeter)
    member = await h.reach(light)
    since = earliest(agent_periods(h.now))
    async with h.sessions() as session:
        runs = await _agent_runs(session, agent_id, since, basis=Basis.EVERYONE, caller_id=budgeter)
        costs = (await session.execute(spend_for(agent_id, since))).scalars().all()
        names = await steward_names(session, [heavy, light])
    spend: list[Actual] = [one for one in (actual_of(row) for row in costs) if one is not None]
    cost_basis = basis_for(reader, h.now)
    if cost_basis is not Basis.EVERYONE or basis_for(member, h.now) is not Basis.OWN:
        raise CheckFailedError("the budget read did not decide whose spend each reader is shown")

    views = agent_period_views(
        agent_id,
        runs=runs,
        spend=spend,
        caller_id=budgeter,
        basis=Basis.EVERYONE,
        cost_basis=cost_basis,
        names=names,
        now=h.now,
    )
    by_range = {one.range: one for one in views}
    if list(by_range) != [one.value for one in Range]:
        raise CheckFailedError("the figures were not given over the four periods the page offers")
    week, quarter = by_range[Range.SEVEN_DAYS.value], by_range[Range.NINETY_DAYS.value]
    if (week.runs, week.messages, quarter.runs, quarter.messages) != (3, 2, 4, 3):
        raise CheckFailedError(
            "an automation's run was counted as a message, or a period missed one"
        )
    if [(one.principal_id, one.spend_minor) for one in week.callers] != [
        (heavy, 300),
        (light, 100),
    ]:
        raise CheckFailedError("the cost per person was not everybody's, heaviest first")
    if [one.spend_minor for one in quarter.callers] != [350, 100]:
        raise CheckFailedError("the ninety days did not hold the cost the week does not")
    own = agent_period_views(
        agent_id,
        runs=runs,
        spend=spend,
        caller_id=light,
        basis=Basis.OWN,
        cost_basis=Basis.OWN,
        names=names,
        now=h.now,
    )
    if any(
        [(one.principal_id, one.spend_minor) for one in period.callers] != [(light, 100)]
        for period in own[:3]
    ):
        raise CheckFailedError("a member was shown somebody else's cost through the agent")
    month_start, _ = window(Range.MONTH_TO_DATE, h.now)
    to_date_runs = sum(1 for _, at, _ in requests if at >= month_start)
    if by_range[Range.MONTH_TO_DATE.value].runs != to_date_runs:
        raise CheckFailedError("the month to date did not count the runs since the first")

    # The budget: its department's budget administrator sets it, a member does not.
    if not may_set_budget(reader, record, h.now) or may_set_budget(member, record, h.now):
        raise CheckFailedError("the budget authority did not decide who may set an agent's budget")
    async with h.sessions() as session:
        first = await write_budget(
            session,
            agent_id=agent_id,
            ceiling_minor=1000,
            reason="Set by an install acceptance check",
            author=budgeter,
            ent_hash=reader.ent_hash(),
            trace_id=h.trace_id,
            now=h.now,
        )
        second = await write_budget(
            session,
            agent_id=agent_id,
            ceiling_minor=2000,
            reason="Changed by an install acceptance check",
            author=budgeter,
            ent_hash=reader.ent_hash(),
            trace_id=h.trace_id,
            now=h.now + timedelta(seconds=1),
        )
        await session.commit()
    if first is None or second is None or (first.version, second.version) != (1, 2):
        raise CheckFailedError("a second monthly budget did not supersede the first as version two")
    ledgered = (
        await h.execute(
            text(
                "SELECT count(*) FROM obs.audit_entry WHERE subject = :subject"
                " AND action = 'setting' AND actor_id = :actor"
            ).bindparams(subject=f"agent:{agent_id}", actor=budgeter)
        )
    ).scalar_one()
    if int(ledgered) < 2:
        raise CheckFailedError("setting an agent's budget did not reach the ledger")

    after = h.now + timedelta(seconds=2)
    projected = projection_view(
        agent_id, ceiling=second, spend=spend, cost_basis=cost_basis, now=after
    )
    to_date = sum(cost for _, cost, at in spends if at >= month_start)
    if projected is None or (projected.spent_minor, projected.ceiling_minor) != (to_date, 2000):
        raise CheckFailedError("the month was not projected against the agent's own budget")
    if projected.projected_minor < to_date:
        raise CheckFailedError("the month-end projection fell below what was already spent")
    if projection_view(agent_id, ceiling=second, spend=spend, cost_basis=Basis.OWN, now=after):
        raise CheckFailedError("a reader of their own spend was given the month's projection")
