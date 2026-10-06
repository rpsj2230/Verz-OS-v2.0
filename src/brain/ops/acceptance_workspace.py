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

from sqlalchemy import Connection, event, insert, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, SessionTransaction

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from pydantic import JsonValue

    from brain.agents.model import AgentRecord

#: Where this module's checks stand on the Install page: after every module that was there before
#: it. See `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 270

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


class _WorkerSession(Session):
    """A session of the check's connection whose every transaction runs as the login.

    The worker's schedule runs automations through `brain.session.make_session_factory`, which sets
    no role, and `agent.automation_run` is written by that login and never by the application role
    (`0067` grants the application SELECT on it). So the check runs the worker's step as the
    worker does, which is `brain.ops.acceptance_checks_lifecycle._swept`'s arrangement for the
    re-verification sweep, and every write it makes is still inside the check's transaction.
    """


@event.listens_for(_WorkerSession, "after_begin")
def _as_the_login(
    session: Session, transaction: SessionTransaction, connection: Connection
) -> None:
    del session, transaction
    connection.exec_driver_sql("RESET ROLE")


def worker_sessions(h: Harness) -> async_sessionmaker[AsyncSession]:
    """Sessions of the check's connection as the worker's schedule opens them."""
    return async_sessionmaker(
        bind=h.connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
        autoflush=False,
        sync_session_class=_WorkerSession,
    )


async def installed_agent(
    h: Harness,
    owner: str,
    *,
    skills: Sequence[tuple[str, str]] = (),
    connectors: Sequence[str] = (),
    overlay: Mapping[str, JsonValue] | None = None,
    capabilities: Sequence[str] = (),
    allowed_tools: Sequence[str] = (),
    suffix: str = "",
    scope: Scope | None = None,
    guardrails: Any = None,
) -> str:
    """An agent of acceptance_a installed from a template the check signs, with `overlay` set here.

    The three rows `brain.agents.install_store.finish` writes, from its own row builders, and the
    instance row field by field as `brain.ops.acceptance_checks_skills._an_agent` writes it.
    """
    from brain.agents.install_store import agent_values, version_values
    from brain.agents.model import AgentAudience, answering_on
    from brain.agents.template import (
        ManifestAuthority,
        ManifestIdentity,
        SkillRef,
        TemplateManifest,
        install,
        materialise,
        publish,
    )
    from brain.core.entitlement import Capability
    from brain.gate.context import Channel
    from brain.knowledge.visibility import Visibility
    from brain.tables.agent import AgentRow
    from brain.tables.template import TemplateInstanceRow, TemplateVersionRow

    agent_id, key = f"acceptance_{h.run}{suffix}", secrets.token_hex(32)
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
            authority=ManifestAuthority(
                scope=Scope.department(A) if scope is None else scope,
                capabilities=tuple(Capability(value=one) for one in capabilities),
                allowed_tools=tuple(allowed_tools),
            ),
            **({} if guardrails is None else {"guardrails": guardrails}),
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
        # Switched on for the console, where the workspace asks it, as a person would tick it.
        insert(AgentRow).values(
            **agent_values(answering_on(effective.record, (Channel.CONSOLE.value,)))
        ),
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


# ------------------------------------------------- 3. connectors: attached, requested, hidden
#: The install's own source every install has: the uploaded price list, read through `local`.
LOCAL_SOURCE: Final = "local"
LOCAL_TOOL: Final = "local.read_price_list"
LOCAL_READ: Final = "read:price_list"


@check(
    leaves=("M39.2.1.4",),
    sentence=(
        "An agent naming this install's own price list source shows it attached when its ceiling "
        "allows the source's tool and requested when it does not, to a reader who may be told of "
        "the source, and shows a reader who may not no row for it at all."
    ),
)
async def an_agents_connector_is_attached_or_requested_by_its_ceiling(h: Harness) -> None:
    from brain.agent_capability_routes import connector_details
    from brain.agent_routes import install_for, install_of
    from brain.ops.acceptance_checks_tools import _install_registry
    from brain.tables.template import TemplateInstanceRow

    await h.found_departments()
    steward, outsider = h.principal(A, "steward"), h.principal(B, "outsider")
    await h.person(steward, department=A, grants=_everywhere(LOCAL_READ))
    await h.person(outsider, department=B)
    registry = _install_registry(h)
    if LOCAL_TOOL not in {one.name for one in registry.definitions()}:
        raise CheckFailedError("the install's registry does not register its own price list tool")
    attached_id = await installed_agent(
        h,
        steward,
        connectors=(LOCAL_SOURCE,),
        capabilities=(LOCAL_READ,),
        allowed_tools=(LOCAL_TOOL,),
    )
    requested_id = await installed_agent(h, steward, connectors=(LOCAL_SOURCE,), suffix="_asks")

    async def presence(agent_id: str, reader: str) -> list[tuple[str, str]]:
        record = await stored_agent(h, agent_id)
        async with h.sessions() as session:
            pair = (await session.execute(install_for(agent_id))).one_or_none()
        if pair is None or not isinstance(pair[0], TemplateInstanceRow):
            raise CheckFailedError("the workspace route's install read found no install")
        made = install_of(pair[0], pair[1], record)
        rows = connector_details(made, record, registry, await h.reach(reader), h.now)
        return [(one.source, one.presence) for one in rows]

    if await presence(attached_id, steward) != [(LOCAL_SOURCE, "attached")]:
        raise CheckFailedError("a source whose tool the ceiling allows was not shown attached")
    if await presence(requested_id, steward) != [(LOCAL_SOURCE, "requested")]:
        raise CheckFailedError("a source the agent names and cannot use was not shown requested")
    if await presence(attached_id, outsider) != []:
        raise CheckFailedError("a reader who may not be told of a source was shown its row")


# ------------------------------------------------------- 4. skills from the approved library
@check(
    leaves=("M39.2.2.1", "M39.2.2.2", "M39.2.2.3", "M39.2.2.4", "M39.2.2.5"),
    sentence=(
        "An agent's skill chip carries the pinned skill's version, source and review state and "
        "how often it ran; an approved library skill is offered to attach, an unreviewed one only "
        "with the address of its review, and a skill whose description adds nothing to its name "
        "is refused when it is assigned."
    ),
)
async def an_agents_skills_are_chips_and_offers_from_the_library(
    h: Harness,
) -> None:
    from brain.agent_capability_routes import invocations_of, skill_blocks
    from brain.agent_routes import install_for, install_of
    from brain.console.agent_tabs import AgentTabError, SkillInvocation, review_route
    from brain.console.skill_library import SkillLibraryError, added, decided, read_package
    from brain.console.workspace import Basis
    from brain.ops.acceptance_checks_skills import (
        _administrator,
        _an_agent,
        _assign,
        _named,
        _skill_md,
        _store,
    )
    from brain.ops.skill_store import StoredSkills
    from brain.tables.skill_invocation import SkillInvocationRow
    from brain.tables.template import TemplateInstanceRow

    await h.found_departments()
    admin = await _administrator(h, "skills")
    reach = await h.reach(admin)
    store = StoredSkills(h.sessions)

    async def approved(name: str, description: str) -> Any:
        made = added(
            read_package("SKILL.md", _skill_md(name, description=description)), by=admin, at=h.now
        )
        await _store(h, made, reach)
        if not await store.decide(
            decided(made, reviewer=admin, approve=True, at=h.now),
            ent_hash=reach.ent_hash(),
            trace_id=h.trace_id,
        ):
            raise CheckFailedError("an administrator could not approve a skill they imported")
        return made

    pinned_name = _named(h, "pinned")
    pinned = await approved(pinned_name, "Use when a workspace check asks for its pinned skill")
    spare_name = _named(h, "spare")
    await approved(spare_name, "Use when a workspace check offers a skill to attach")
    waiting_name = _named(h, "waiting")
    waiting = added(
        read_package(
            "SKILL.md",
            _skill_md(waiting_name, description="Use when a workspace check waits on review"),
        ),
        by=admin,
        at=h.now,
    )
    await _store(h, waiting, reach)
    vague_name = _named(h, "vague")
    vague = await approved(vague_name, "Use when acceptance vague")

    agent_id = await _an_agent(h, admin)
    await _assign(h, pinned.digest, agent_id, reach)
    try:
        await _assign(h, vague.digest, agent_id, reach)
    except (SkillLibraryError, AgentTabError):
        pass
    else:
        raise CheckFailedError("a skill whose description adds nothing to its name was assigned")

    async with h.sessions() as session:
        await session.execute(
            insert(SkillInvocationRow),
            [
                {
                    "agent_id": agent_id,
                    "skill_name": pinned_name,
                    "digest": pinned.digest,
                    "principal_id": admin,
                    "trace_id": f"{h.trace_id}-k{n}",
                    "used_at": h.now - timedelta(hours=n + 1),
                }
                for n in range(2)
            ],
        )
        await session.commit()

    record = await stored_agent(h, agent_id)
    since = h.now - timedelta(days=30)
    async with h.sessions() as session:
        pair = (await session.execute(install_for(agent_id))).one_or_none()
        rows = (
            await session.execute(
                invocations_of(agent_id, since, basis=Basis.EVERYONE, caller_id=admin)
            )
        ).all()
    if pair is None or not isinstance(pair[0], TemplateInstanceRow):
        raise CheckFailedError("the workspace route's install read found no install")
    made = install_of(pair[0], pair[1], record)
    chips, unused, offers = skill_blocks(
        made,
        record,
        library=await store.library(),
        invocations=[
            SkillInvocation(agent_id=agent_id, skill_name=name, principal_id=who, at=at)
            for who, name, at in rows
        ],
        reach=reach,
        caller_id=admin,
        basis=Basis.EVERYONE,
        listed=True,
        editable=True,
        now=h.now,
    )
    if [(one.name, one.version, one.review, one.runs) for one in chips] != [
        (pinned_name, "1.0.0", "approved", 2)
    ]:
        raise CheckFailedError("the pinned skill's chip did not carry its version, review and runs")
    if not chips[0].source or not chips[0].detachable or unused:
        raise CheckFailedError("the pinned skill's chip did not say where it came from")
    offered = {one.name: (one.control, one.route) for one in offers}
    if offered.get(spare_name) != ("attach", ""):
        raise CheckFailedError("an approved library skill was not offered to attach")
    if offered.get(waiting_name) != ("review", review_route(waiting_name)):
        raise CheckFailedError("an unreviewed skill was offered without the address of its review")
    if pinned_name in offered:
        raise CheckFailedError("a skill the agent already runs was offered again")


# ------------------------------------------------------------- 5. knowledge as a predicate
@check(
    leaves=("M39.2.3.1", "M39.2.3.2", "M39.2.3.3", "M39.2.3.4"),
    sentence=(
        "An agent of acceptance_a draws on knowledge by the predicate its scope is, which matches "
        "the reader's two documents there, one verified and one not, and not the document "
        "uploaded to acceptance_b; an upload there is reported as one the agent does not reach, "
        "and an upload into acceptance_a as one it does."
    ),
)
async def an_agents_knowledge_is_a_predicate_over_the_readers_documents(
    h: Harness,
) -> None:
    from brain.agent_capability_routes import (
        knowledge_scope_of,
        knowledge_view,
        reader_items,
    )
    from brain.console.agent_tabs import AddRoute, plan_addition
    from brain.knowledge.ingest import MediaType, ParseFailure
    from brain.knowledge.search import KNOWLEDGE_UPLOAD
    from brain.ops.acceptance_checks import KNOWLEDGE_READS, _in, _upload
    from brain.ops.acceptance_checks_lifecycle import REVIEW_AHEAD, _as, _verify
    from brain.ops.acceptance_documents import a_markdown_document

    await h.found_departments()
    steward, elsewhere = h.principal(A, "steward"), h.principal(B, "steward")
    await h.person(steward, department=A, grants=_in(A, *KNOWLEDGE_READS, KNOWLEDGE_UPLOAD.value))
    await h.person(elsewhere, department=B, grants=_in(B, *KNOWLEDGE_READS, KNOWLEDGE_UPLOAD.value))
    agent_id = await installed_agent(h, steward)
    record = await stored_agent(h, agent_id)
    scope = knowledge_scope_of(record)
    if scope is None:
        raise CheckFailedError("an agent scoped to a department had no knowledge predicate")

    async def uploaded(who: str, department: str, word: str) -> str:
        read = await _upload(
            h,
            who,
            filename=f"Acceptance {word}.md",
            declared=MediaType.MARKDOWN.value,
            body=a_markdown_document("Acceptance workspace", f"This document says {word}."),
            department=department,
        )
        if isinstance(read, ParseFailure):
            raise CheckFailedError("a well-formed Markdown document could not be added")
        return str(read.item.item_id)

    first = await uploaded(steward, A, h.word())
    await uploaded(steward, A, h.word())
    await uploaded(elsewhere, B, h.word())
    if await _verify(h, await _as(h, steward), first, review_by=h.now + REVIEW_AHEAD) is None:
        raise CheckFailedError("the steward could not verify a document they added")

    reach = await h.reach(steward)
    items, _ = await reader_items(h.sessions, reach, h.now)
    ours = [one for one in items if one.visibility.department == A]
    view = knowledge_view(scope, items, at_least=False, now=h.now)
    if [(one.field, one.value) for one in view.clauses] != [("department", A)]:
        raise CheckFailedError("the agent's knowledge was not the predicate its scope is")
    if (view.matched, view.verified, view.unverified, view.stale) != (len(ours), 1, 1, 0):
        raise CheckFailedError("the slice did not count the reader's documents the predicate meets")
    if len(ours) != 2:
        raise CheckFailedError("the reader was not shown the two documents they added")

    other_reach = await h.reach(elsewhere)
    theirs, _ = await reader_items(h.sessions, other_reach, h.now)
    if knowledge_view(scope, theirs, at_least=False, now=h.now).matched != 0:
        raise CheckFailedError("a reader elsewhere was counted documents of the agent's department")
    outside = next(iter(one for one in theirs if one.visibility.department == B), None)
    if outside is None:
        raise CheckFailedError("the document uploaded elsewhere did not read back to its uploader")
    if plan_addition(scope, outside, AddRoute.UPLOAD).reached:
        raise CheckFailedError("an upload outside the predicate was reported as reached")
    if not plan_addition(scope, ours[0], AddRoute.UPLOAD).reached:
        raise CheckFailedError("an upload inside the predicate was reported as not reached")


# ------------------------------------------- 6. who can use it, its ceiling, and a preview
@check(
    leaves=("M39.3.1.1", "M39.3.1.2", "M39.3.1.3", "M39.3.1.4"),
    sentence=(
        "An agent of acceptance_a is found by its department and not by acceptance_b, saying that "
        "finding it gives no access; its ceiling is shown whole to a reader of capabilities and "
        "locked to others; and a preview for a person holding the price list read lists the tool "
        "their run would reach, while a person holding nothing is told the run returns nothing."
    ),
)
async def an_agent_is_found_by_its_audience_and_previewed_as_a_person(
    h: Harness,
) -> None:
    from brain.agent_capability_routes import availability_view, preview_of
    from brain.agent_routes import install_for, install_of
    from brain.agents.model import AUDIENCE_IS_NOT_AUTHORITY
    from brain.console.reach_view import (
        CEILING_DISCLOSURE,
        PREVIEW_DISCLOSURE,
        PREVIEW_RETURNS_NOTHING,
        ceiling_block,
    )
    from brain.gate.roster import viewer_for
    from brain.identity.principal_store import StoredPrincipals
    from brain.ops.acceptance_checks_tools import _install_registry
    from brain.tables.template import TemplateInstanceRow

    await h.found_departments()
    steward, holder, empty, outsider = (
        h.principal(A, "steward"),
        h.principal(A, "holder"),
        h.principal(A, "empty"),
        h.principal(B, "outsider"),
    )
    await h.person(
        steward,
        department=A,
        grants=_everywhere(CEILING_DISCLOSURE.value, PREVIEW_DISCLOSURE.value),
    )
    await h.person(holder, department=A, grants=_everywhere(LOCAL_READ))
    await h.person(empty, department=A)
    await h.person(outsider, department=B)
    agent_id = await installed_agent(
        h,
        steward,
        connectors=(LOCAL_SOURCE,),
        capabilities=(LOCAL_READ,),
        allowed_tools=(LOCAL_TOOL,),
    )
    record = await stored_agent(h, agent_id)

    people = StoredPrincipals(h.sessions)

    async def viewer(principal_id: str) -> Any:
        found = await people.live_principal(principal_id)
        if found is None:
            raise CheckFailedError("a reserved principal did not read back as a live person")
        return viewer_for(found)

    inside = availability_view(record, await viewer(holder))
    beyond = availability_view(record, await viewer(outsider))
    if (inside.level, inside.department, inside.reader_is_included) != ("department", A, True):
        raise CheckFailedError("a member of the agent's department was not in its audience")
    if beyond.reader_is_included:
        raise CheckFailedError("a person in another department was in the agent's audience")
    if inside.words != AUDIENCE_IS_NOT_AUTHORITY:
        raise CheckFailedError("the availability block did not say it gives nobody access")

    shown = ceiling_block(record, await h.reach(steward), h.now)
    locked = ceiling_block(record, await h.reach(holder), h.now)
    if shown.locked or LOCAL_READ not in shown.capabilities:
        raise CheckFailedError("a reader of capabilities was not shown the agent's whole ceiling")
    if not locked.locked or locked.capabilities:
        raise CheckFailedError("a reader who may not read capabilities was shown the ceiling")

    registry = _install_registry(h)
    async with h.sessions() as session:
        pair = (await session.execute(install_for(agent_id))).one_or_none()
    if pair is None or not isinstance(pair[0], TemplateInstanceRow):
        raise CheckFailedError("the workspace route's install read found no install")
    made = install_of(pair[0], pair[1], record)
    previewer = await h.reach(steward)

    async def preview(person: str, by: Any) -> Any:
        return await preview_of(
            h.sessions,
            record=record,
            install=made,
            registry=registry,
            person_id=person,
            previewer=by,
            now=h.now,
        )

    held = await preview(holder, previewer)
    none = await preview(empty, previewer)
    if held is None or [one.name for one in held.tools] != [LOCAL_TOOL] or held.rung is None:
        raise CheckFailedError("a preview did not list the tool the person's run would reach")
    if none is None or none.tools or none.notice != PREVIEW_RETURNS_NOTHING:
        raise CheckFailedError("a person holding nothing was previewed as reaching something")
    if await preview(holder, await h.reach(holder)) is not None:
        raise CheckFailedError("a reader who may not read grants was given somebody's preview")


# ------------------------------------------------------------- 7. memory and learning
@check(
    leaves=(
        "M39.4.1.1",
        "M39.4.1.2",
        "M39.4.1.3",
        "M39.4.1.4",
        "M39.4.1.5",
        "M39.4.2.1",
        "M39.4.2.2",
        "M39.4.2.4",
    ),
    sentence=(
        "Memories formed from a person's turn with an agent read as text, stated apart from "
        "inferred, to its steward, and to the person as what it keeps about them; the steward's "
        "edit shows in the history with its diff and the person's delete takes theirs out of "
        "recall; a colleague sees neither; the tiers say which learn and route a gated change "
        "to its department."
    ),
)
async def an_agents_memory_is_text_its_owner_corrects_and_its_tiers_route(
    h: Harness,
) -> None:
    from brain.agent_memory_routes import agent_entries, changeable, memory_view, replacement_for
    from brain.console.govern_estate import UNDO_AUTHORITY
    from brain.console.reach_view import BACK_LINK, run_reach
    from brain.console.reads import Plane, plane_capability
    from brain.console.screens import screen
    from brain.console.workspace import Tab, tab
    from brain.core.entitlement import Capability
    from brain.memory.digest import Learning
    from brain.memory.formation import Formation, MemoryKind
    from brain.memory.signals import Signal
    from brain.memory.tiers import Change, Tier, propose
    from brain.memory.turn import Turn
    from brain.ops.acceptance_checks import _in
    from brain.ops.memory_store import (
        StoredFormations,
        StoredMemoryRecords,
        learning_row,
        memory_row,
    )

    await h.found_departments()
    steward, person, colleague = (
        h.principal(A, "steward"),
        h.principal(A, "person"),
        h.principal(A, "colleague"),
    )
    memory_read = tab(Tab.MEMORY).read.requires.value
    content = plane_capability(Plane.CONTENT).value
    await h.person(
        steward,
        department=A,
        grants=_everywhere(
            LOCAL_READ,
            memory_read,
            *_planes(),
            screen("scopes").read.requires.value,
            UNDO_AUTHORITY.value,
        ),
    )
    for one in (person, colleague):
        await h.person(one, department=A, grants=_in(A, LOCAL_READ, memory_read, content))
    agent_id = await installed_agent(
        h,
        steward,
        capabilities=(LOCAL_READ,),
        allowed_tools=(LOCAL_TOOL,),
        scope=Scope.unrestricted(),
    )
    record = await stored_agent(h, agent_id)

    # The person's own turn, answered at their run reach, formed by the product's own step.
    stated, inferred = "my invoices go to the finance inbox", "I prefer short answers"
    turn = Turn(
        trace_id=f"{h.trace_id}-turn",
        principal_id=person,
        said=f"Remember that {stated}. {inferred}.",
        answered=True,
        reach=run_reach(await h.reach(person), record),
        at=h.now,
        agent_id=agent_id,
    )
    formed = await StoredFormations(h.sessions).form(turn)
    if len(formed.memory_ids) != 2:
        raise CheckFailedError("a person's turn with the agent did not form its two memories")

    # A gated change the agent proposed in acceptance_a, written as the formation step writes one.
    gated = Learning(
        memory_id=f"m{h.word().lower()[2:]}{'0' * 25}"[:26],
        proposal=propose(Change.LEASH_INCREASE, subject=f"agent:{agent_id}"),
        formation=Formation(
            principal_id=steward,
            capabilities=(Capability(value=LOCAL_READ),),
            scope=Scope.department(A),
            ent_hash="0" * 32,
            formed_at=h.now,
            kind=MemoryKind.PERSISTENT,
        ),
        agent_id=agent_id,
    )
    await h.execute(
        memory_row(gated, "Raise the agent's rung for price lists"), learning_row(gated)
    )

    async def seen(who: str) -> Any:
        async with h.sessions() as session:
            stored, entries = await agent_entries(session, record)
        return stored, memory_view(
            record, stored, entries, reader=await h.reach(who), department=A, now=h.now
        )

    stored, by_steward = await seen(steward)
    curated = [one.statement for one in by_steward.curated]
    if stated not in curated or [one.statement for one in by_steward.extracted] != [inferred]:
        raise CheckFailedError("the agent's memory did not read as stated apart from inferred")
    if not all(one.changeable for one in (*by_steward.curated, *by_steward.extracted)):
        raise CheckFailedError("the agent's steward was not offered its memory to change")
    _, by_person = await seen(person)
    if sorted(one.statement for one in by_person.about_you) != sorted((stated, inferred)):
        raise CheckFailedError("a person was not shown what the agent keeps about them")
    _, by_colleague = await seen(colleague)
    theirs = {
        one.statement
        for one in (*by_colleague.curated, *by_colleague.extracted, *by_colleague.about_you)
    }
    if theirs & {stated, inferred}:
        raise CheckFailedError("a colleague was shown what the agent keeps about somebody else")
    if Tier.GATED.value in by_steward.active_tiers or Tier.AUTOMATIC.value not in (
        by_steward.active_tiers
    ):
        raise CheckFailedError("the active tiers did not say the agent learns short of tier three")
    if not by_steward.tier_one or not all(one.undo_offered for one in by_steward.tier_one):
        raise CheckFailedError("the automatic changes were not listed with their undo")
    routed = [(one.department, one.back_to) for one in by_steward.tier_three or []]
    if routed != [(A, BACK_LINK.format(agent_id=agent_id))]:
        raise CheckFailedError("a gated change was not routed to its department's queue")

    # The steward corrects the stated memory; the person deletes the inferred one.
    records = StoredMemoryRecords(h.sessions)
    by_id = {one.memory_id: one for one in stored.learnings}
    first = next(one.memory_id for one in by_steward.curated if one.statement == stated)
    corrected = "my invoices go to the accounts inbox"
    if changeable(by_colleague, first) is not None:
        raise CheckFailedError("a colleague was offered a memory they are not shown")
    edited = await records.edit(
        by_id[first],
        replacement_for(by_id[first], corrected, at=h.now),
        corrected,
        prompted_by=Signal.REJECTED,
        actor=steward,
        trace_id=h.trace_id,
        ent_hash="0" * 32,
    )
    if edited.replacement is None:
        raise CheckFailedError("the steward's correction of the agent's memory was not written")
    extracted_id = next(one.memory_id for one in by_person.about_you if one.statement == inferred)
    if not changeable(by_person, extracted_id):
        raise CheckFailedError("a person was not offered to delete a memory about themselves")
    undone = await records.undo(
        by_id[extracted_id], actor=person, trace_id=h.trace_id, ent_hash="0" * 32
    )
    if undone.correction is None:
        raise CheckFailedError("a person's delete of a memory about themselves was not written")

    _, after = await seen(steward)
    now_curated = [one.statement for one in after.curated]
    if corrected not in now_curated or stated in now_curated or after.extracted:
        raise CheckFailedError("an edit or a delete did not change what the agent remembers")
    step = next((one for one in after.history if one.replaced_id == first), None)
    if step is None or step.trigger != Signal.REJECTED.value:
        raise CheckFailedError("the history did not record the correction and what caused it")
    if not any(line.startswith("-") and "finance" in line for line in step.diff) or not any(
        line.startswith("+") and "accounts" in line for line in step.diff
    ):
        raise CheckFailedError("the history did not show the correction as a diff")


# --------------------------------------------------------------------------- 8. automations
@check(
    leaves=(
        "M39.6.1.1",
        "M39.6.1.2",
        "M39.6.1.3",
        "M39.6.1.4",
        "M39.6.1.5",
        "M39.6.2.1",
        "M39.6.2.2",
        "M39.6.2.4",
    ),
    sentence=(
        "An automation installed from the gallery in one step is listed under its own agent and "
        "no other, named as an outcome, registered with what it guards; its owner cannot start it "
        "and a second administrator can; it runs as its owner and its run is listed with the next "
        "one; stopping and removing it are rows written with the schedule, and it runs no more."
    ),
)
async def an_agents_automation_is_installed_started_run_and_removed(
    h: Harness,
) -> None:
    from sqlalchemy import update

    from brain.console.agent_automations import (
        automations_for,
        outcome_name_refusals,
        registry_gaps,
    )
    from brain.console.automation_gallery import (
        AUTOMATION_AUTHORITY,
        install,
        new_automation_id,
        preview,
        template_by_id,
    )
    from brain.console.automation_schedule import (
        changed,
        may_start,
        may_stop,
        shown_start,
        shown_stop,
    )
    from brain.console.automations import Change, ChangeKind, may_remove, shown
    from brain.console.questions_view import QUESTION_AUTHORITY
    from brain.console.workspace import Tab, tab
    from brain.gate.entitlement_store import StoredEntitlements
    from brain.identity.principal_store import StoredPrincipals
    from brain.ops.agent_automation_store import StoredAgentAutomations
    from brain.ops.automation_run import PausedBecause, RunOutcome
    from brain.ops.automation_run_store import StoredAutomationSchedules, run_one
    from brain.tables.agent_automation import AgentAutomationRow
    from brain.tables.automation_run import STARTED

    await h.found_departments()
    owner, approver = h.principal(A, "owner"), h.principal(A, "approver")
    tab_read = tab(Tab.AUTOMATIONS).read.requires.value
    for one in (owner, approver):
        await h.person(
            one,
            department=A,
            grants=_everywhere(
                AUTOMATION_AUTHORITY.value, tab_read, QUESTION_AUTHORITY.value, *_planes()
            ),
        )
    agent_id = await installed_agent(
        h, owner, capabilities=(QUESTION_AUTHORITY.value,), scope=Scope.unrestricted()
    )
    other_id = await installed_agent(h, owner, suffix="_other")
    record = await stored_agent(h, agent_id)
    people = StoredPrincipals(h.sessions)
    owner_principal = await people.live_principal(owner)
    template = template_by_id("unanswered_questions")
    if owner_principal is None or template is None:
        raise CheckFailedError("the check's owner or the gallery's template did not read back")

    # One step: the preview the gallery shows, confirmed, installed paused.
    owner_reach = await h.reach(owner)
    shown_install = preview(
        template, record, installer=owner_principal, installer_reach=owner_reach
    )
    installation = install(
        shown_install,
        confirmation=shown_install.confirmation,
        automation_id=new_automation_id(),
    )
    done = await StoredAgentAutomations(h.sessions).install(
        installation, ent_hash=owner_reach.ent_hash(), trace_id=h.trace_id
    )
    if not done.created:
        raise CheckFailedError("installing an automation from the gallery wrote nothing")
    automation_id = done.automation_id

    schedules = StoredAutomationSchedules(h.sessions)
    listed = await schedules.listed(agent_id)
    if [one.automation.automation_id for one in listed] != [automation_id]:
        raise CheckFailedError("the automation was not listed under the agent that owns it")
    if await schedules.listed(other_id):
        raise CheckFailedError("an automation was listed under an agent that does not own it")
    [held] = listed
    if outcome_name_refusals(held.automation.name):
        raise CheckFailedError("an installed automation was not named as an outcome")
    if held.guards != template.guards or registry_gaps([held.automation], [installation.entry]):
        raise CheckFailedError("the automation's registry entry did not say what it guards")
    if not held.automation.paused:
        raise CheckFailedError("an installed automation was scheduled before anybody started it")
    seen = automations_for(agent_id, [held.automation], await h.reach(approver), h.now)
    if [one.automation_id for one in seen] != [automation_id]:
        raise CheckFailedError("a reader of the agent's automations was not shown it")

    # A start is a gated change: never by whom it runs as, and by another administrator.
    cadence = held.cadence or template.cadence
    start = shown_start(held.automation, cadence, now=h.now)
    becomes = start.becomes
    if becomes is None:
        raise CheckFailedError("the automation's cadence gave no next run to start at")
    if may_start(held.automation, owner_reach, agent=record, becomes=becomes, now=h.now):
        raise CheckFailedError("an automation's owner could start it without a second person")
    approver_reach = await h.reach(approver)
    if not may_start(held.automation, approver_reach, agent=record, becomes=becomes, now=h.now):
        raise CheckFailedError("a second administrator could not start the automation")
    written = await schedules.change(
        changed(start, confirmation=start.confirmation, guards=held.guards),
        reason=STARTED,
        actor=approver,
        ent_hash=approver_reach.ent_hash(),
        trace_id=h.trace_id,
        at=h.now,
    )
    [started] = await schedules.listed(agent_id)
    if not written or started.automation.next_run_at != becomes:
        raise CheckFailedError("starting the automation did not schedule its next run")

    # Due now, and run as its owner by the worker's own step.
    await h.execute(
        *h.attributed(approver),
        update(AgentAutomationRow)
        .where(AgentAutomationRow.automation_id == automation_id)
        .values(next_run_at=h.now),
    )
    ran = await run_one(
        worker_sessions(h),
        automation_id,
        now=h.now,
        principals=people,
        entitlements=StoredEntitlements(h.sessions),
    )
    if ran is None or ran.outcome is not RunOutcome.SUCCEEDED:
        raise CheckFailedError("a due automation did not run as its owner")
    [after_run] = await schedules.listed(agent_id)
    last = after_run.runs[0] if after_run.runs else None
    if last is None or last.principal_id != owner or last.ent_hash is None:
        raise CheckFailedError("the automation's run was not recorded as its owner's")
    if after_run.automation.next_run_at is None or after_run.automation.next_run_at <= h.now:
        raise CheckFailedError("after a run the automation was not scheduled again")

    # Stopped by whom it runs as, then removed, each a row written with the schedule.
    if not may_stop(after_run.automation, owner_reach, now=h.now):
        raise CheckFailedError("an automation's owner could not stop it")
    stop = shown_stop(after_run.automation, after_run.cadence or template.cadence)
    await schedules.change(
        changed(stop, confirmation=stop.confirmation, guards=after_run.guards),
        reason=PausedBecause.STOPPED.value,
        actor=owner,
        ent_hash=owner_reach.ent_hash(),
        trace_id=h.trace_id,
        at=h.now,
    )
    [stopped] = await schedules.listed(agent_id)
    if not stopped.automation.paused:
        raise CheckFailedError("stopping the automation left it scheduled")
    if not may_remove(stopped.automation, owner_reach, removed=False, now=h.now):
        raise CheckFailedError("an automation's owner could not remove it")
    removed = await schedules.apply(
        automation_id,
        Change(kind=ChangeKind.REMOVED, at=h.now, changed_by=owner),
        expect=shown(stopped.automation, cadence=stopped.cadence, removed=False),
        ent_hash=owner_reach.ent_hash(),
        trace_id=h.trace_id,
    )
    [gone] = await schedules.listed(agent_id)
    if not removed or not gone.removed or len(gone.runs) != 1:
        raise CheckFailedError("removing the automation did not keep it and its run as a row")
    if await run_one(
        worker_sessions(h),
        automation_id,
        now=h.now,
        principals=people,
        entitlements=StoredEntitlements(h.sessions),
    ):
        raise CheckFailedError("a removed automation ran again")
