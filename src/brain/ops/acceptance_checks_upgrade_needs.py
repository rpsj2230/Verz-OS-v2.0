"""The install acceptance check for what accepting a template version needs: the checks an install
meets, asked before and after, and an agent that is not left running on what is only declared.

`brain.ops.acceptance_checks_upgrade` proves a newer version is read, declined and accepted. This
proves the half M13.8.11 adds: that accepting runs the same binding and completeness checks as
installing, so a version declaring a tool nothing here provides, a connector nothing here serves
and a question nobody has answered is **named by the review before anybody presses accept**, and
the acceptance that follows leaves the agent **disabled with the same list**, instead of running
on names that bind to nothing.

**Nothing about the install is assumed, and every missing thing is one it cannot hold.** The tool
is on an entity no source registers and the connector is a name no connection can carry, so the
list is the same on an install with every source connected and on one with none; and the question
is one the version before did not ask, which is unanswered on every install because nobody was
asked. A version that declares and asks nothing new is the positive half: nothing is named, the
acceptance leaves the agent switched on, so the guard is not satisfied by refusing everything.

**Through the route functions the console calls, as reserved administrators of acceptance_a**, over
the check's own signing key and inside the check's transaction, rolled back.

Task ids: M13.8.11
"""

from __future__ import annotations

import json
import secrets
from typing import TYPE_CHECKING, Any, Final, cast

from sqlalchemy import insert, select

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks_templates import _asking, _gallery, _request
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI

A, _ = RESERVED_DEPARTMENTS

#: Where this module's check stands on the Install page, beside the upgrade check's own. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 405

NOT_NAMED: Final = (
    "a version declaring a tool, a connector and a question this install cannot hold was not "
    "shown as needing all three before it was accepted"
)
NEEDS_WHEN_NOTHING_IS_NEEDED: Final = (
    "a version needing nothing here was shown as needing something"
)
NOT_ACCEPTED: Final = "an administrator could not accept a version that needs something"
LEFT_RUNNING: Final = "an agent upgraded to a version it cannot run on was left switched on"
NOT_TOLD: Final = "the acceptance did not name what the upgraded agent still needs"
SWITCHED_OFF_WITHOUT_NEED: Final = "a version needing nothing here switched the agent off"
NOT_MOVED: Final = "an accepted version did not move the agent to it"

#: The question version two asks and version one did not, a tool on an entity nothing registers and
#: a connector no connection can carry.
QUESTION: Final = "acceptance_new_question"
TOOL: Final = "acceptance_unregistered.read"
CONNECTOR: Final = "acceptance_unconnected"


def _body(answered: Any) -> dict[str, Any]:
    """A route's JSON body, whichever way it answered."""
    if hasattr(answered, "body"):
        return cast(dict[str, Any], json.loads(bytes(answered.body)))
    return cast(dict[str, Any], answered.model_dump(mode="json"))


async def _administrator(h: Harness) -> str:
    """A reserved principal holding the agent lifecycle authority over acceptance_a."""
    from brain.agents.lifecycle import AGENT_LIFECYCLE_CAPABILITY

    made = h.principal(A, "needs")
    await h.person(
        made,
        department=A,
        grants=((AGENT_LIFECYCLE_CAPABILITY.value, Scope.department(A)),),
    )
    return made


def _manifest(agent_id: str, owner: str, version: int, *, asks: bool) -> Any:
    """One version of the agent's template: a persona, and from version two, when `asks`, a tool,
    a connector and a required question the version before did not have."""
    from brain.agents.template import (
        ManifestAuthority,
        ManifestIdentity,
        Placeholder,
        TemplateManifest,
    )

    return TemplateManifest(
        identity=ManifestIdentity(
            template_id=agent_id,
            version=version,
            published_by=owner,
            display_name="Acceptance needs agent",
        ),
        persona="Answers an install acceptance check and nobody else.",
        authority=ManifestAuthority(
            scope=Scope.department(A), allowed_tools=(TOOL,) if asks and version > 1 else ()
        ),
        connectors=(CONNECTOR,) if asks and version > 1 else (),
        placeholders=(Placeholder(key=QUESTION, prompt="Which?"),) if asks and version > 1 else (),
    )


async def _an_agent_with_a_newer_version(
    h: Harness, owner: str, key: str, *, name: str, asks: bool
) -> str:
    """An agent installed from version one, enabled, with version two shelved."""
    from brain.agents.install_store import agent_values, version_values
    from brain.agents.model import AgentAudience, answering_on
    from brain.agents.template import install, materialise, publish
    from brain.gate.context import Channel
    from brain.knowledge.visibility import Visibility
    from brain.tables.agent import AgentRow
    from brain.tables.template import TemplateInstanceRow, TemplateVersionRow

    agent_id = f"acceptance_{h.run}_{name}"
    first = publish(_manifest(agent_id, owner, 1, asks=asks), key=key, signed_by=owner, at=h.now)
    second = publish(_manifest(agent_id, owner, 2, asks=asks), key=key, signed_by=owner, at=h.now)
    instance = install(first, key=key, instance_id=agent_id, created_by=owner, at=h.now)
    audience = AgentAudience(level=Visibility.DEPARTMENT, owner_id=owner, department=A)
    effective = materialise(first, instance, audience=audience)
    await h.execute(
        *h.attributed(owner),
        insert(TemplateVersionRow).values(**version_values(first)),
        insert(TemplateInstanceRow).values(
            id=agent_id,
            template_id=instance.template_id,
            template_version=instance.template_version,
            content_digest=instance.content_digest,
            overlay=dict(instance.overlay),
            field_owners={},
            effective_document=dict(effective.document),
            effective_hash=effective.config_hash,
            created_by=owner,
        ),
        insert(AgentRow).values(
            **agent_values(answering_on(effective.record, (Channel.CONSOLE.value,)))
        ),
    )
    await h.execute(
        *h.attributed(owner), insert(TemplateVersionRow).values(**version_values(second))
    )
    return agent_id


async def _review(h: Harness, app: FastAPI, who: str, agent_id: str) -> dict[str, Any]:
    from brain.agent_upgrade_routes import agent_upgrade

    return _body(await agent_upgrade(_request(app), agent_id, await _asking(h, who)))


@check(
    leaves=("M13.8.11",),
    sentence=(
        "A newer version declaring a tool, a connector and a question this install cannot hold is "
        "shown to an administrator of acceptance_a as needing all three before it is accepted, "
        "and accepting it names the same three and leaves the agent switched off; a version that "
        "needs nothing new names nothing and leaves the agent switched on."
    ),
)
async def accepting_a_version_runs_the_checks_an_install_runs(h: Harness) -> None:
    from brain.agent_upgrade_routes import UpgradeAccepted, accept_agent_upgrade
    from brain.tables.agent import AgentRow
    from brain.tables.template import TemplateInstanceRow

    await h.found_departments()
    key = secrets.token_hex(32)
    app = _gallery(h, key)
    admin = await _administrator(h)
    asking = await _asking(h, admin)

    asks = await _an_agent_with_a_newer_version(h, admin, key, name="asks", asks=True)
    review = await _review(h, app, admin, asks)
    named = {(one["kind"], one["name"]) for one in review["needs"]}
    if named != {("placeholder", QUESTION), ("connector", CONNECTOR), ("tool", TOOL)}:
        raise CheckFailedError(NOT_NAMED)
    drawn = {"to_version": review["to_version"], "expected_hash": review["expected_hash"]}
    answered = await accept_agent_upgrade(
        _request(app), asks, UpgradeAccepted(**drawn, resolutions={}), asking
    )
    if answered.status_code != 200:
        raise CheckFailedError(NOT_ACCEPTED)
    done = _body(answered)
    moved = (
        await h.execute(select(TemplateInstanceRow).where(TemplateInstanceRow.id == asks))
    ).scalar_one()
    switched_off = (
        await h.execute(select(AgentRow.disabled_at).where(AgentRow.id == asks))
    ).scalar_one()
    if moved.template_version != 2:
        raise CheckFailedError(NOT_MOVED)
    if switched_off is None or done["switched_off"] is not True:
        raise CheckFailedError(LEFT_RUNNING)
    if {(one["kind"], one["name"]) for one in done["needs"]} != named:
        raise CheckFailedError(NOT_TOLD)

    quiet = await _an_agent_with_a_newer_version(h, admin, key, name="quiet", asks=False)
    review = await _review(h, app, admin, quiet)
    if review["needs"]:
        raise CheckFailedError(NEEDS_WHEN_NOTHING_IS_NEEDED)
    drawn = {"to_version": review["to_version"], "expected_hash": review["expected_hash"]}
    answered = await accept_agent_upgrade(
        _request(app), quiet, UpgradeAccepted(**drawn, resolutions={}), asking
    )
    if answered.status_code != 200:
        raise CheckFailedError(NOT_ACCEPTED)
    still_on = (
        await h.execute(select(AgentRow.disabled_at).where(AgentRow.id == quiet))
    ).scalar_one()
    if still_on is not None or _body(answered)["switched_off"] is not False:
        raise CheckFailedError(SWITCHED_OFF_WITHOUT_NEED)
