"""Install acceptance checks for what an agent's own page tells a reader, and what moving it leaves.

Each check calls the route the console page calls, as the reader that page serves, over the
check's own transaction, in the shape `brain.ops.acceptance_agent_console` sets out. **Every row
written is in the transaction the run rolls back, for a reserved person of acceptance_a, and
nothing reaches a person**: the template is signed with a key made for the check, so the
installed agent is made as a gallery press makes one and by nobody's real key.

**The lifecycle check goes through the routes, and reads the ledger back through the Audit
screen's route filtered by the agent.** The domain's refusals (a stale press, an archived agent
that somebody tries to enable, a steward who cannot take the agent) are held beside the moves
that succeed, so a check that passed only because every press was accepted would fail here.

Task ids: M27.11.15, M27.11.6, M27.15.29
"""

from __future__ import annotations

import json
import secrets
from typing import Any, Final, cast

from sqlalchemy import insert, text

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1300

A, B = RESERVED_DEPARTMENTS

#: What the ledger says of an agent, by the word `0137` and `0105` give the change.
LIFECYCLE_WORDS: Final = ("created", "enabled", "disabled", "archived", "published")


# --------------------------------------------------------------- 1. the Profile (M27.11.15)
@check(
    leaves=("M27.11.15",),
    sentence=(
        "An installed agent's Settings reader is told its steward, template and version, whether "
        "it is switched on, its tier, who may find it, what it may reach in words and its leash "
        "ceiling, sees it switched off at once, and a reader without the tab is sent no Profile."
    ),
)
async def an_agents_profile_says_what_the_reference_page_does_not(h: Harness) -> None:
    from brain.agent_lifecycle_routes import LifecycleStateAsked, disable_agent
    from brain.agent_routes import agent_workspace
    from brain.ops.acceptance_agent_console import _asking, _console, _readers, _request
    from brain.ops.acceptance_workspace import installed_agent

    await h.found_departments()
    steward, outsider = h.principal(A, "steward"), h.principal(A, "outsider")
    from brain.agents.lifecycle import AGENT_LIFECYCLE_CAPABILITY

    await h.person(
        steward,
        department=A,
        grants=_readers(),
    )
    await h.grant(steward, AGENT_LIFECYCLE_CAPABILITY.value, Scope.department(A))
    await h.person(outsider, department=A, grants=())
    agent_id = await installed_agent(h, steward, capabilities=("read:note.body",))
    app = _console(h)

    answer = await agent_workspace(_request(app), agent_id, await _asking(h, steward))
    header = answer.agent
    if header.owner_id != steward:
        raise CheckFailedError("the Profile's header did not name the agent's steward")
    if not header.template_id or header.template_version != 1:
        raise CheckFailedError("the Profile's header did not name the template and its version")
    if header.state not in {"enabled", "disabled"}:
        raise CheckFailedError("the Profile's header did not say whether the agent is switched on")
    profile = answer.profile
    if profile is None:
        raise CheckFailedError("a reader of the Settings tab was sent no Profile")
    if not profile.tier or profile.audience_level != "department":
        raise CheckFailedError("the Profile did not say the model tier and who may find the agent")
    if not profile.ceiling.rows and not profile.ceiling.reads and not profile.ceiling.tools:
        raise CheckFailedError("the Profile did not say, in words, what the agent may reach")
    if header.leash_up_to is not None and not profile.leash:
        raise CheckFailedError("the Profile named a leash ceiling and listed no leash row")

    moved = await disable_agent(
        _request(app),
        agent_id,
        LifecycleStateAsked(expected_state=cast("Any", header.state)),
        await _strong(h, steward),
    )
    if moved.status_code == 409 and header.state == "disabled":
        pass
    elif moved.status_code != 200:
        raise CheckFailedError("the agent's steward could not switch their own agent off")
    again = await agent_workspace(_request(app), agent_id, await _asking(h, steward))
    if again.agent.state != "disabled":
        raise CheckFailedError("the Profile did not show the agent as switched off after it was")

    # Not the same answer for somebody who may not open Settings: nothing says what was withheld.
    hidden = await agent_workspace(_request(app), agent_id, await _asking(h, outsider))
    if hidden.profile is not None or hidden.agent.state is not None:
        raise CheckFailedError("a reader without the Settings tab was sent the agent's Profile")


async def _strong(h: Harness, principal_id: str) -> Any:
    """What the gate hands a route for a person signed in with a second factor."""
    from brain.ops.acceptance_agent_console import _asking

    return await _asking(h, principal_id, strong=True)


# ----------------------------- 2. the lifecycle, handing over and the ledger (M27.11.6, M27.15.29)
@check(
    leaves=("M27.11.6", "M27.15.29"),
    sentence=(
        "An installed agent is enabled, switched off and on, handed on, duplicated, published by a "
        "second person and retired; a stale press, enabling a retired agent and a steward who is "
        "not there are refused in words, and the Audit route asked for the agent lists each move "
        "under its maker and nothing of another agent."
    ),
)
async def an_agent_moves_through_its_life_and_the_ledger_filters_by_it(
    h: Harness,
) -> None:
    from brain.agent_lifecycle_routes import (
        DuplicateAsked,
        LifecycleStateAsked,
        PublicationAsked,
        TransferAsked,
        agent_lifecycle,
        archive_agent,
        disable_agent,
        duplicate_agent,
        enable_agent,
        publish_agent,
        transfer_agent,
    )
    from brain.agents.catalogue import CATALOGUE
    from brain.agents.install_store import version_values
    from brain.agents.lifecycle import AGENT_LIFECYCLE_CAPABILITY, AGENT_PUBLICATION_CAPABILITY
    from brain.agents.template import publish
    from brain.audit_routes import audit_page
    from brain.ops.acceptance_checks_company_views import _audit_over
    from brain.ops.acceptance_checks_governance import _asking as audited
    from brain.ops.acceptance_checks_governance import _traced
    from brain.ops.acceptance_checks_templates import (
        _administrator,
        _asking,
        _copy,
        _gallery,
        _install,
        _request,
    )
    from brain.ops.acceptance_checks_w3 import KNOWLEDGE_AGENT
    from brain.tables.template import TemplateVersionRow

    _traced(h)
    await h.found_departments()
    administrator = await _administrator(h)
    await h.grant(administrator, AGENT_LIFECYCLE_CAPABILITY.value, Scope.department(A))
    heir, publisher, auditor = (h.principal(A, role) for role in ("heir", "publisher", "auditor"))
    await h.person(heir, department=A)
    await h.person(
        publisher,
        department=A,
        grants=(
            (AGENT_PUBLICATION_CAPABILITY.value, Scope.unrestricted()),
            (AGENT_LIFECYCLE_CAPABILITY.value, Scope.unrestricted()),
        ),
    )
    await h.person(auditor, department=B, grants=_audit_over(Scope.unrestricted()))

    shipped = next(one for one in CATALOGUE if one.identity.template_id == KNOWLEDGE_AGENT)
    key = secrets.token_hex(32)
    gallery = _gallery(h, key)
    signed = publish(
        _copy(shipped, f"acceptance_{h.run}_lifecycle"), key=key, signed_by=administrator, at=h.now
    )
    await h.execute(
        *h.attributed(administrator),
        insert(TemplateVersionRow).values(**version_values(signed)),
    )
    request = _request(gallery)

    async def body(answered: Any) -> dict[str, Any]:
        return cast("dict[str, Any]", json.loads(bytes(answered.body)))

    async def pressed(move: Any, who: str, expected: str, *, want: int = 200) -> dict[str, Any]:
        answered = await move(
            request,
            agent_id,
            LifecycleStateAsked(expected_state=cast("Any", expected)),
            await _asking(h, who),
        )
        if answered.status_code != want:
            raise CheckFailedError("a press on the agent was not answered as the page expects")
        return await body(answered)

    agent_id = (await _install(h, gallery, administrator, signed))["agent"]["agent_id"]

    # 1. Installed disabled; enabling it is one press, and the same press with the page's old
    # state is refused in words and changes nothing.
    if (await pressed(enable_agent, administrator, "disabled"))["state"] != "enabled":
        raise CheckFailedError("a disabled agent was not enabled")
    stale = await pressed(enable_agent, administrator, "disabled", want=409)
    if stale.get("outcome") != "moved":
        raise CheckFailedError("a press made on a stale page was not refused as stale")
    if (await pressed(disable_agent, administrator, "enabled"))["state"] != "disabled":
        raise CheckFailedError("an enabled agent was not switched off")
    if (await pressed(enable_agent, administrator, "disabled"))["state"] != "enabled":
        raise CheckFailedError("a switched-off agent was not switched on again")

    # 2. Handing it on: to somebody who works here, and not to a name nobody holds.
    nobody = await transfer_agent(
        request,
        agent_id,
        TransferAsked(to_owner=f"{heir}.nobody", expected_owner=administrator),
        await _asking(h, administrator),
    )
    if nobody.status_code != 409:
        raise CheckFailedError("an agent was handed to a steward who does not exist")
    handed = await transfer_agent(
        request,
        agent_id,
        TransferAsked(to_owner=heir, expected_owner=administrator),
        await _asking(h, administrator),
    )
    if handed.status_code != 200 or (await body(handed))["owner_id"] != heir:
        raise CheckFailedError("an agent was not handed to the steward who was asked to take it")

    # 3. A duplicate is a new agent, switched off, naming the configuration the page drew.
    seen = await agent_lifecycle(request, agent_id, await _asking(h, administrator))
    if not seen.effective_hash:
        raise CheckFailedError("the agent's page was not given the configuration to duplicate")
    copied = await duplicate_agent(
        request,
        agent_id,
        DuplicateAsked(
            display_name="Acceptance copy", expected_hash=seen.effective_hash, for_department=True
        ),
        await _asking(h, administrator),
    )
    if copied.status_code != 201:
        raise CheckFailedError("an agent could not be duplicated")
    copy = (await body(copied))["agent"]
    if copy["agent_id"] == agent_id or copy["state"] != "disabled":
        raise CheckFailedError("a duplicate was not a new agent, switched off")

    # 4. Published to the company by a second person: the steward's own press and a stranger's
    # are not it.
    published = await publish_agent(
        request,
        agent_id,
        PublicationAsked(expected_level="department"),
        await _asking(h, publisher),
    )
    if published.status_code != 200 or (await body(published))["level"] != "company":
        raise CheckFailedError("a second person could not publish the agent to the company")

    # 5. Retired for good, and a retired agent cannot be switched on again.
    retired = await pressed(archive_agent, publisher, "enabled")
    if retired["state"] != "archived":
        raise CheckFailedError("an agent was not retired")
    refused = await pressed(enable_agent, publisher, "archived", want=409)
    if refused.get("outcome") != "refused" or not refused.get("sentence"):
        raise CheckFailedError("a retired agent was enabled, or refused without a sentence")

    # 6. The ledger, asked for this agent through the Audit screen's route.
    reader = await audited(h, auditor)
    mine = await audit_page(
        _request(gallery), reader, subject_kind="agent", subject_id=agent_id, limit=100
    )
    kinds = {one.details.get("change") for one in mine.items if one.action.value == "agent"}
    if not set(LIFECYCLE_WORDS) - {"created"} <= kinds:
        raise CheckFailedError("the agent's ledger entries did not name each move it was given")
    if any(one.subject_id != agent_id or one.subject_kind != "agent" for one in mine.items):
        raise CheckFailedError(
            "the ledger filtered by an agent listed an entry about something else"
        )
    actors = {one.actor_id for one in mine.items if one.details.get("change") == "published"}
    if actors != {publisher}:
        raise CheckFailedError("the publication was not recorded under the publisher's name")
    # The hand-over is `0105`'s `agent_owner` entry. It is counted in the ledger itself, because
    # the trigger keeps both stewards' ids as they are and the screen's view builds only an entry
    # whose details are field names: a reserved person's id is not one, and a real one may not be.
    handed_on = (
        await h.execute(
            text(
                "SELECT count(*) FROM obs.audit_entry WHERE action = 'agent_owner'"
                " AND subject = :subject AND actor_id = :actor"
            ).bindparams(subject=f"agent:{agent_id}", actor=administrator)
        )
    ).scalar_one()
    if handed_on != 1:
        raise CheckFailedError("the hand-over was not in the ledger under its maker's name")
    elsewhere = await audit_page(
        _request(gallery), reader, subject_kind="agent", subject_id=copy["agent_id"], limit=100
    )
    if any(one.subject_id == agent_id for one in elsewhere.items) or not elsewhere.items:
        raise CheckFailedError("the duplicate's own ledger was not its own")
