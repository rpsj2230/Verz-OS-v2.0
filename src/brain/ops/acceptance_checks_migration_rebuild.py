"""Install checks for what a migration from another system leans on: an agent is rebuilt from a
template at Shadow with a ceiling of its own, an imported skill waits for its review, adoption
leaves machines out, and the scheduler and its safety controls are all accounted for.

`brain.migration` is a set of refusals over an in-memory register (see its package docstring), and
what it says a migration must do is already what the product's own paths do: **an agent exists
only because it was installed from a signed template, so there is no importer of a foreign
agent's configuration to refuse**; the install route writes a ceiling, starts every target at
Shadow, and a skill added from elsewhere arrives unreviewed. These checks show that on an install
rather than in `brain.migration`'s own tests, by driving the routes a person would.

**Nothing here imports a foreign system's agent, skill or memory**, because nothing in this
product does. The leaves say "rather than importing" and the proof is that the only way in is the
template route, which is what the first check walks.

**The skill is added as an administrator adds one and approved by a second.** The library's own
review route is the queue the leaf names; the check adds a package as one administrator, finds it
unreviewed and not executable, approves it as another through the route, and finds it executable
and signed by the second.

Task ids: M37.2.2.3, M37.2.3.1, M37.2.3.2, M37.2.3.3, M37.3.2.4, M37.5.1.2, M37.5.1.4
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Final

from sqlalchemy import insert, select

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2210

A, _B = RESERVED_DEPARTMENTS

#: A capability no template in the catalogue names, so a caller holding it shows the ceiling narrow.
NOT_ANY_TEMPLATE_S: Final = "read:payroll.total"

NOT_FROM_ITS_TEMPLATE: Final = (
    "an agent installed from a template was not recorded as that template's version, unchanged"
)
A_FOREIGN_FIELD_CAME_WITH_IT: Final = (
    "an agent installed from a template carried a changed field the template did not declare"
)
NO_CEILING: Final = "an agent installed from a template held no ceiling of its own"
THE_CEILING_DID_NOT_NARROW: Final = (
    "a run of an installed agent was not narrowed to the ceiling it was installed with"
)
NOT_AT_SHADOW: Final = "an installed agent did not start at Shadow on every target"
NO_TEMPLATE_TO_INSTALL: Final = "this release ships no template that names a capability and a leash"
AN_IMPORT_WAS_TRUSTED: Final = "a skill added from outside was executable before anyone reviewed it"
NOT_QUEUED: Final = "a skill added from outside was not waiting in the library for its review"
NOT_REVIEWED_AS_SECOND_PERSON: Final = (
    "a skill approved through the review route was not stored as approved by that reviewer"
)
A_MACHINE_WAS_COUNTED: Final = "adoption counted a question that a machine asked"
A_PERSON_WAS_NOT_COUNTED: Final = "adoption did not count a question that a person asked"
A_JOB_WAS_NOT_LISTED: Final = "the Jobs screen did not list every control the scheduler runs"
A_CONTROL_HAS_NO_CALLER: Final = "a safety control the registry says is called is not called"
NO_TREE_HERE: Final = (
    "this install carries the product as a package without its source tree, which the registry "
    "check reads, so it cannot be asked here"
)


# --------------------------------------------- 1. rebuilt from a template (M37.2.3.1 to M37.2.3.3)
@check(
    leaves=("M37.2.3.1", "M37.2.3.2", "M37.2.3.3"),
    sentence=(
        "An agent installed from a signed template through the gallery's install route is "
        "recorded as that template's version with nothing added to it, holds the ceiling its "
        "template declares so a caller's run through it is narrowed to that ceiling, and starts "
        "at Shadow on every target of its leash."
    ),
)
async def an_agent_is_rebuilt_from_a_template_with_a_ceiling_and_at_shadow(h: Harness) -> None:
    from brain.agents.catalogue import CATALOGUE
    from brain.agents.install_store import version_values
    from brain.agents.model import entitlement_ceiling
    from brain.agents.template import publish
    from brain.core.entitlement import Capability, EntitlementSet, Grant
    from brain.ops.acceptance_checks_templates import _administrator, _copy, _gallery, _install
    from brain.ops.acceptance_workspace import stored_agent
    from brain.ops.automation import flow_reach
    from brain.tables.template import TemplateInstanceRow, TemplateVersionRow

    shipped = next(
        (one for one in CATALOGUE if one.authority.capabilities and one.guardrails.leash), None
    )
    if shipped is None:
        raise CheckNotRunError(NO_TEMPLATE_TO_INSTALL)
    await h.found_departments()
    administrator = await _administrator(h)
    key = secrets.token_hex(32)
    signed = publish(
        _copy(shipped, f"acceptance_{h.run}_rebuilt"),
        key=key,
        signed_by=administrator,
        at=h.now,
    )
    await h.execute(
        *h.attributed(administrator), insert(TemplateVersionRow).values(**version_values(signed))
    )
    made = await _install(h, _gallery(h, key), administrator, signed)
    agent_id = str(made["agent"]["agent_id"])

    instance = (
        await h.execute(select(TemplateInstanceRow).where(TemplateInstanceRow.id == agent_id))
    ).scalar_one_or_none()
    identity = signed.manifest.identity
    if (
        instance is None
        or instance.template_id != identity.template_id
        or instance.template_version != identity.version
        or instance.content_digest != signed.content_digest
    ):
        raise CheckFailedError(NOT_FROM_ITS_TEMPLATE)
    if instance.overlay:
        raise CheckFailedError(A_FOREIGN_FIELD_CAME_WITH_IT)

    ceiling = entitlement_ceiling(await stored_agent(h, agent_id))
    if not ceiling.grants:
        raise CheckFailedError(NO_CEILING)
    named = sorted({one.capability.value for one in ceiling.grants})
    caller = EntitlementSet(
        principal_id=h.principal(A, "caller"),
        grants=tuple(
            Grant(capability=Capability(value=value), scope=Scope.unrestricted())
            for value in (*named, NOT_ANY_TEMPLATE_S)
        ),
    )
    run = flow_reach(caller, ceiling)
    held = {one.capability.value for one in run.grants}
    if not held or not held <= set(named) or NOT_ANY_TEMPLATE_S in held:
        raise CheckFailedError(THE_CEILING_DID_NOT_NARROW)

    rungs = {str(one["rung"]) for one in made["leash"]}
    if rungs != {"shadow"}:
        raise CheckFailedError(NOT_AT_SHADOW)


# ------------------------------------------------- 2. an added skill waits (M37.2.2.3)
@check(
    leaves=("M37.2.2.3",),
    sentence=(
        "A skill package added to the library by one administrator is stored undecided and not "
        "executable, and becomes executable only when another administrator approves it through "
        "the library's review route, after which it is stored as approved by that second "
        "administrator."
    ),
)
async def a_skill_added_from_outside_runs_only_after_its_review(h: Harness) -> None:
    from brain.ops.acceptance_checks_skill_packages import _added
    from brain.ops.acceptance_checks_skills import _administrator, _named, _skill_md
    from brain.ops.acceptance_skill_console import _asking, _console, _request
    from brain.ops.skill_store import StoredSkills
    from brain.skill_routes import ReviewAsked, review_skill

    await h.found_departments()
    importer = await _administrator(h, "importer", reviews=False)
    reviewer = await _administrator(h, "second")
    app = _console(h)
    name = _named(h, "foreign")
    digest = await _added(h, app, importer, "SKILL.md", _skill_md(name))
    kept = await StoredSkills(h.sessions).skill(digest)
    if kept is None or kept.imported.reviewer:
        raise CheckFailedError(NOT_QUEUED)
    if kept.imported.is_executable():
        raise CheckFailedError(AN_IMPORT_WAS_TRUSTED)
    await review_skill(
        _request(app), digest, ReviewAsked(decision="approve"), await _asking(h, reviewer)
    )
    after = await StoredSkills(h.sessions).skill(digest)
    if after is None or after.imported.reviewer != reviewer or not after.imported.is_executable():
        raise CheckFailedError(NOT_REVIEWED_AS_SECOND_PERSON)


# -------------------------------------------- 3. adoption leaves machines out (M37.3.2.4)
@check(
    leaves=("M37.3.2.4",),
    sentence=(
        "Of three questions recorded in acceptance_a, one asked by a person on the console and "
        "two by machines (a service account, and a person's name on the scheduler), the "
        "Adoption route shows the department with one question and one person."
    ),
)
async def adoption_counts_the_person_and_leaves_the_machines_out(h: Harness) -> None:
    from brain.adoption import Asked
    from brain.core.principal import PrincipalKind
    from brain.gate.context import Channel
    from brain.listing import ListAsked
    from brain.ops.acceptance_operations_console import asking_as, console_for
    from brain.ops.acceptance_operations_console_3 import READS_AGENTS, READS_USAGE
    from brain.ops.question_store import record
    from brain.report_routes import adoption

    await h.found_departments()
    person, scheduled, reader = (h.principal(A, role) for role in ("person", "schedule", "reader"))
    service = h.principal(A, "service")
    await h.person(person, department=A)
    await h.person(scheduled, department=A)
    await h.person(
        reader,
        department=A,
        grants=((READS_USAGE, Scope.department(A)), (READS_AGENTS, Scope.unrestricted())),
    )
    at = datetime.now(UTC) - timedelta(minutes=5)
    for suffix, who, kind, channel in (
        ("p", person, PrincipalKind.HUMAN, Channel.CONSOLE),
        ("s", service, PrincipalKind.SERVICE, Channel.CONSOLE),
        ("t", scheduled, PrincipalKind.HUMAN, Channel.SCHEDULER),
    ):
        async with h.sessions() as session:
            await record(
                session,
                Asked(
                    trace_id=f"{h.trace_id}-adopt-{suffix}",
                    principal_id=who,
                    principal_kind=kind,
                    channel=channel,
                    department=A,
                    at=at,
                ),
            )
            await session.commit()
    shown = await adoption(
        console_for(h).request(), await asking_as(h, reader), ListAsked(), days=1
    )
    line = next((one for one in shown.items if one.department == A), None)
    if line is None or line.questions < 1:
        raise CheckFailedError(A_PERSON_WAS_NOT_COUNTED)
    if (line.questions, line.people) != (1, 1):
        raise CheckFailedError(A_MACHINE_WAS_COUNTED)


# ---------------------------------- 4. every control is scheduled and called (M37.5.1.2, M37.5.1.4)
@check(
    leaves=("M37.5.1.2", "M37.5.1.4"),
    sentence=(
        "The Jobs route lists every control the scheduler is the one to start, none of the "
        "safety controls the registry says something calls is without a caller, and the "
        "registry's own audit of the source finds nothing out of step."
    ),
)
async def every_scheduled_control_is_listed_and_has_a_caller(
    h: Harness,
) -> None:
    from brain.jobs_routes import jobs
    from brain.ops import controls
    from brain.ops.acceptance_operations_console import asking_as, console_for, screen_grants
    from brain.ops.schedule import schedulable

    await h.found_departments()
    reader = h.principal(A, "queue")
    await h.person(reader, department=A, grants=screen_grants("queue"))
    listed = await jobs(console_for(h).request(), await asking_as(h, reader))
    if {one.control for one in listed.jobs} != {one.name for one in schedulable()}:
        raise CheckFailedError(A_JOB_WAS_NOT_LISTED)
    if not controls.SRC.is_dir():
        raise CheckNotRunError(NO_TREE_HERE)
    if controls.registry_gaps():
        raise CheckFailedError(A_CONTROL_HAS_NO_CALLER)
