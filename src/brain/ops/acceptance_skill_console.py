"""The install acceptance checks for the Skills screen's acts and the builder's second person.

Each check calls the route functions the page calls, in the order a person presses them: on the
Skills screen, assigning a version to an agent, searching and filtering the library, retiring a
version, detaching it and reinstating it; on the builder, starting a draft, saving it, checking it,
publishing it, and approving it as somebody else from the Approvals queue. Every call is made as the
reader the page serves, with the install's own sessions and tool registry, and admitted at the
strong session the console asks of anybody holding an administrative authority.

**Routes rather than the functions under them, for the owner's rule that a console page is done
when it works on his install.** The page tests in CI prove what the pages draw from an answer; these
prove the answer, on this install's schema and grants. See
`brain.ops.acceptance_agent_console.A_CONSOLE_LEAF_IS_PROVED_THROUGH_ITS_ROUTE`, which argues the
same choice for the agent's own pages.

**Insert-only is asked of the tables, not of the answers.** A retirement, a reinstatement and a
detachment are each read back as rows of `agent.skill_retirement` and `agent.skill_detachment`,
counted for the check's own digest, and the assignment the detachment ended is read back as still
present. An answer saying "reinstated" over a table whose earlier row was updated in place would
otherwise pass. See `A_LIBRARY_ACT_IS_A_ROW_AND_NEVER_AN_EDIT`.

**The builder's publish is signed with a key the check makes**, as
`brain.ops.acceptance_workspace.installed_agent` signs its template, and never with the install's
own template key: the check reads nothing from the vault, and what it publishes is rolled back with
everything else it wrote.

Task ids: M27.11.8, M27.15.55, M27.15.56, M27.15.31
"""

from __future__ import annotations

import json
import secrets
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Final, cast

from sqlalchemy import func, select

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI

#: Where this module's checks stand on the Install page: after the agent console's.
#: See `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 301

A, B = RESERVED_DEPARTMENTS

A_LIBRARY_ACT_IS_A_ROW_AND_NEVER_AN_EDIT: Final = (
    "Retiring, reinstating and detaching a skill are each read back as a row the act added, and "
    "the assignment a detachment ended as still there, so a library that edited its history in "
    "place fails the check even when every answer it gave read correctly."
)


# ------------------------------------------------------------------------ the console
def _console(h: Harness) -> FastAPI:
    """The state the Skills screen's and the builder's routes read, over the check's
    transaction: sessions, settings, the install's own tool registry and a key the check made."""
    from fastapi import FastAPI

    from brain.ops.acceptance_checks_tools import _install_registry

    app = FastAPI()
    app.state.settings = h.settings
    app.state.db_sessions = h.sessions
    app.state.tools = _install_registry(h)
    app.state.template_key = secrets.token_hex(32)
    return app


def _request(app: FastAPI) -> Any:
    from starlette.requests import Request

    return Request({"type": "http", "app": app, "headers": [], "method": "POST"})


async def _asking(h: Harness, principal_id: str) -> Any:
    """A signed-in administrator as the console admits one: the principal, the reach at a strong
    session, and the check's instant."""
    from brain.gate.admission import Assurance, admit
    from brain.gate.context import Channel
    from brain.identity.principal_store import StoredPrincipals

    person = await StoredPrincipals(h.sessions).live_principal(principal_id)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    reach = admit(await h.reach(principal_id), Channel.CONSOLE, Assurance.STRONG)
    # A cast at the routes' boundary: they read these three, and a `Caller` is minted only from
    # a verified token.
    return cast(
        Any,
        SimpleNamespace(caller=SimpleNamespace(principal=person), reach=reach, now=h.now),
    )


def _body(response: Any) -> dict[str, Any]:
    found = json.loads(bytes(response.body))
    if not isinstance(found, dict):
        raise CheckFailedError("a route answered with something other than a document")
    return found


# ------------------------------------------- 1. the library's acts, each a row
@check(
    leaves=("M27.11.8", "M27.15.55", "M27.15.56"),
    sentence=(
        "An administrator assigns an approved skill to an agent and is told the tools it reaches "
        "through the agent's ceiling; the library finds it by name with the agent counted; "
        "retiring it names that agent and detaches nobody, assigning it again is refused, and "
        "retiring, detaching and reinstating each add a row and change none."
    ),
)
async def a_skills_library_acts_are_rows_and_assignments_follow_them(h: Harness) -> None:
    import structlog

    from brain.api_routes import FILTER_SEPARATOR
    from brain.console.skill_library import added, decided, read_package
    from brain.core.errors import Absent
    from brain.listing import ListAsked
    from brain.ops.acceptance_checks_skills import _administrator, _named, _skill_md, _store
    from brain.ops.acceptance_workspace import LOCAL_READ, LOCAL_TOOL, installed_agent
    from brain.ops.skill_store import StoredSkills
    from brain.skill_routes import (
        AssignAsked,
        assign_skill,
        detach_skill,
        reinstate_skill,
        retire_skill,
        skill_library,
    )
    from brain.tables.skill import SkillAssignmentRow, SkillDetachmentRow, SkillRetirementRow

    await h.found_departments()
    admin = await _administrator(h, "skills")
    await h.grant(admin, LOCAL_READ, Scope.unrestricted())
    reach = await h.reach(admin)
    name = _named(h, "library")
    made = added(
        read_package(
            "SKILL.md",
            _skill_md(
                name,
                description="Use when the library's acts are checked on this install",
                extra=(f"tools: [{LOCAL_TOOL}]",),
            ),
        ),
        by=admin,
        at=h.now,
    )
    await _store(h, made, reach)
    if not await StoredSkills(h.sessions).decide(
        decided(made, reviewer=admin, approve=True, at=h.now),
        ent_hash=reach.ent_hash(),
        trace_id=h.trace_id,
    ):
        raise CheckFailedError("an administrator could not approve a skill they imported")
    first = await installed_agent(
        h, admin, capabilities=(LOCAL_READ,), allowed_tools=(LOCAL_TOOL,), suffix="_first"
    )
    second = await installed_agent(h, admin, suffix="_second")
    app = _console(h)
    digest = made.digest

    async def listed(*filters: str) -> dict[str, Any]:
        page = await skill_library(
            _request(app), await _asking(h, admin), ListAsked(filters=filters)
        )
        return {one.digest: one for one in page.items}

    async def counted(table: Any, *where: Any) -> int:
        async with h.sessions() as session:
            return int(
                (
                    await session.execute(select(func.count()).select_from(table).where(*where))
                ).scalar_one()
            )

    with structlog.contextvars.bound_contextvars(trace_id=h.trace_id):
        # M27.11.8: assigned, with the tools it reaches checked against the agent's ceiling.
        assigned = _body(
            await assign_skill(
                _request(app), digest, AssignAsked(agent_id=first), await _asking(h, admin)
            )
        )
        if assigned.get("reach") != [LOCAL_TOOL]:
            raise CheckFailedError(
                "an assignment did not say which tools it reaches through the agent"
            )
        # M27.11.8: searched and filtered, with the assignment counted.
        found = await listed(f"name{FILTER_SEPARATOR}{name}")
        if list(found) != [digest] or found[digest].agents_running != 1:
            raise CheckFailedError("the library did not find the skill by name with its agent")
        if digest in await listed(
            f"name{FILTER_SEPARATOR}{name}", f"retired{FILTER_SEPARATOR}true"
        ):
            raise CheckFailedError("a version nobody retired was listed among the retired")

        # M27.15.56: retired, naming the holder and detaching nobody.
        retired = await retire_skill(_request(app), digest, await _asking(h, admin))
        if [one.agent_id for one in retired.holding] != [first]:
            raise CheckFailedError("retiring a version did not name the agent still running it")
        found = await listed(f"name{FILTER_SEPARATOR}{name}", f"retired{FILTER_SEPARATOR}true")
        if digest not in found or found[digest].agents_running != 1:
            raise CheckFailedError("retiring a version detached the agent running it")
        try:
            await assign_skill(
                _request(app), digest, AssignAsked(agent_id=second), await _asking(h, admin)
            )
        except Absent:
            pass
        else:
            raise CheckFailedError("a retired version was assigned to another agent")

        # M27.15.55: detached, and the assignment is derived from the later row.
        await detach_skill(
            _request(app), digest, AssignAsked(agent_id=first), await _asking(h, admin)
        )
        if (await listed(f"name{FILTER_SEPARATOR}{name}"))[digest].agents_running != 0:
            raise CheckFailedError("a detached skill was still counted as running on its agent")
        await reinstate_skill(_request(app), digest, await _asking(h, admin))
        if (await listed(f"name{FILTER_SEPARATOR}{name}"))[digest].retired:
            raise CheckFailedError("a reinstated version was still listed as retired")

    retirements = await counted(SkillRetirementRow, SkillRetirementRow.digest == digest)
    detachments = await counted(
        SkillDetachmentRow,
        SkillDetachmentRow.digest == digest,
        SkillDetachmentRow.agent_id == first,
    )
    assignments = await counted(
        SkillAssignmentRow,
        SkillAssignmentRow.digest == digest,
        SkillAssignmentRow.agent_id == first,
    )
    if (retirements, detachments, assignments) != (2, 1, 1):
        raise CheckFailedError("a library act changed or removed a row rather than adding one")


# ---------------------------------------- 2. a widened publish and its second person
@check(
    leaves=("M27.15.31",),
    sentence=(
        "A new agent that reads the price list, published by its author, waits in the Approvals "
        "queue of a second builder who reads it too and not in that of a builder who does not; "
        "its author may not approve it, and the second person's approval publishes the agent."
    ),
)
async def a_widened_publish_waits_for_a_second_person_who_publishes_it(h: Harness) -> None:
    import structlog

    from brain.agent_builder_routes import (
        WAITS_FOR_A_SECOND_PERSON,
        DraftPublishAsked,
        DraftRevisionAsked,
        DraftSaveAsked,
        DraftStartAsked,
        agent_drafts,
        approve_agent_draft,
        check_agent_draft,
        publish_agent_draft,
        save_agent_draft,
        start_agent_draft,
    )
    from brain.agent_routes import one_agent
    from brain.agents.creation import AGENT_INSTALL_CAPABILITY
    from brain.ops.acceptance_workspace import LOCAL_READ, LOCAL_TOOL, _everywhere, _planes

    await h.found_departments()
    builds = AGENT_INSTALL_CAPABILITY.value
    author, second = h.principal(A, "author"), h.principal(A, "second")
    narrow = h.principal(A, "narrow")
    for one in (author, second):
        await h.person(one, department=A, grants=_everywhere(builds, LOCAL_READ, *_planes()))
    await h.person(narrow, department=A, grants=((builds, Scope.department(B)),))
    app = _console(h)

    with structlog.contextvars.bound_contextvars(trace_id=h.trace_id):
        started = _body(
            await start_agent_draft(
                _request(app), DraftStartAsked(template_id=None), await _asking(h, author)
            )
        )
        draft_id = str(started["draft_id"])
        document = dict(started["document"])
        document["persona"] = "Answers one price list question for an install acceptance check."
        document["authority"] = {
            **document["authority"],
            "capabilities": [{"value": LOCAL_READ}],
            "allowed_tools": [LOCAL_TOOL],
        }
        saved = _body(
            await save_agent_draft(
                _request(app),
                draft_id,
                DraftSaveAsked(document=document, base=int(started["revision"])),
                await _asking(h, author),
            )
        )
        revision = int(saved["revision"])
        checked = _body(
            await check_agent_draft(
                _request(app),
                draft_id,
                DraftRevisionAsked(revision=revision),
                await _asking(h, author),
            )
        )
        if not checked.get("passed"):
            raise CheckFailedError("a draft reading the price list did not pass its own check")
        waiting = await publish_agent_draft(
            _request(app),
            draft_id,
            DraftPublishAsked(revision=revision, for_department=False),
            await _asking(h, author),
        )
        if (
            waiting.status_code != 202
            or _body(waiting).get("sentence") != WAITS_FOR_A_SECOND_PERSON
        ):
            raise CheckFailedError(
                "a publish reaching the price list did not wait for a second person"
            )

        async def queue(reader: str) -> list[str]:
            page = await agent_drafts(_request(app), await _asking(h, reader))
            return [one.draft_id for one in page.waiting_for_you]

        if draft_id not in await queue(second):
            raise CheckFailedError(
                "a waiting publish was not in a second builder's Approvals queue"
            )
        if draft_id in await queue(narrow):
            raise CheckFailedError("a waiting publish was queued for a builder who cannot read it")
        own = await approve_agent_draft(
            _request(app), draft_id, DraftRevisionAsked(revision=revision), await _asking(h, author)
        )
        if own.status_code < 400:
            raise CheckFailedError("the author of a widened publish approved it themselves")
        approved = await approve_agent_draft(
            _request(app), draft_id, DraftRevisionAsked(revision=revision), await _asking(h, second)
        )
        if approved.status_code != 201:
            raise CheckFailedError("the second person's approval did not publish the agent")
        agent_id = str(_body(approved).get("agent_id", ""))

    async with h.sessions() as session:
        stored = (await session.execute(one_agent(agent_id))).scalar_one_or_none()
    if stored is None:
        raise CheckFailedError("an approved publish left no agent on the install")
    if draft_id in await queue(second):
        raise CheckFailedError("a published draft was still waiting in the Approvals queue")
