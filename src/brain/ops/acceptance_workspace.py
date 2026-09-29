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
    capabilities: Sequence[str] = (),
    allowed_tools: Sequence[str] = (),
    suffix: str = "",
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
    from brain.core.entitlement import Capability
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
                scope=Scope.department(A),
                capabilities=tuple(Capability(value=one) for one in capabilities),
                allowed_tools=tuple(allowed_tools),
            ),
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
