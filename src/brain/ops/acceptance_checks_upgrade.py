"""The install acceptance check for an agent's upgrade: a newer version of its template, read,
declined, accepted, and never accepted at a higher rung.

`brain.agent_upgrade_routes` is the review, accept and decline, and this asks it as reserved
administrators of acceptance_a and acceptance_b, through its own route functions, the way the
console does. The template signing key is the check's own, for the reason
`brain.ops.acceptance_checks_templates.THE_WORKER_HOLDS_NO_SIGNING_KEY` gives: the worker is given
none, so what is proved is the route's behaviour over a key it can verify, and everything is
written inside the check's transaction and rolled back.

**The agent is made as the product makes one and then left behind its template.** Version one is
signed, installed with a local persona claimed by a person, and the agent's row written as an
install writes it; version two is signed with the same key and shelved as a published version is.
Nothing here moves the pin by hand, so what the check reads back is only what the routes wrote.

**What it holds, in order.** The review names the version on offer and the one path this install
claimed; a reader holding the authority over another department is told nothing, which is the one
404; a decline is a row and the badge says declined while the review still shows what was turned
down; an acceptance resolving the claimed path to the template's words moves the pin, the agent's
persona and the install's hash together, and the review afterwards is current; and a version that
holds a target at a higher rung than the agent is on cannot be accepted, leaves the pin where it
was, and can still be declined. See `brain.agents.upgrade.AN_UPGRADE_NEVER_RAISES_A_RUNG`.

Task ids: M13.4.2, M13.4.3, M13.4.4, M13.4.5
"""

from __future__ import annotations

import json
import secrets
from typing import TYPE_CHECKING, Any, Final, cast

from sqlalchemy import insert, select

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks_skills import _changes
from brain.ops.acceptance_checks_templates import _asking, _gallery, _request
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI

A, B = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 404

NO_REVIEW: Final = "an agent behind its template was not shown the version on offer"
NOT_A_CONFLICT: Final = "a persona this install claimed was not shown as a conflict to decide"
OUTSIDER_TOLD: Final = "a reader holding the authority over another department was told something"
NO_DECLINE: Final = "a decline was not recorded, or did not quiet the badge"
DECLINE_HID_IT: Final = "a declined version could no longer be read"
NOT_ACCEPTED: Final = "an administrator could not accept the version on offer"
NOT_MOVED: Final = "an accepted version did not move the pin, the persona and the hash together"
STILL_OFFERED: Final = "the version was still on offer after it was accepted"
RUNG_RAISED: Final = "a version holding a higher rung than the agent is on was accepted"
RUNG_NOT_SAID: Final = "the review did not say a version holding a higher rung cannot be accepted"
NOT_DECLINABLE: Final = "a version that cannot be accepted could not be declined"
NOT_ON_THE_LEDGER: Final = "a decline or an acceptance did not reach the ledger naming the person"

#: The persona version one is installed with, the one an administrator claimed for this install,
#: and the one version two publishes.
FIRST: Final = "Answers an install acceptance check and nobody else."
LOCAL: Final = "Answers an install acceptance check, in this company's own words."
SECOND: Final = "Answers an install acceptance check, briefly, and nobody else."

#: A target the third version holds at a rung the agent is not on.
TARGET: Final = "acceptance.read_note"


def _body(answered: Any) -> dict[str, Any]:
    """A route's JSON body, whichever way it answered."""
    if hasattr(answered, "body"):
        return cast(dict[str, Any], json.loads(bytes(answered.body)))
    return cast(dict[str, Any], answered.model_dump(mode="json"))


async def _administrator(h: Harness, role: str, department: str) -> str:
    """A reserved principal holding the agent lifecycle authority over one department."""
    from brain.agents.lifecycle import AGENT_LIFECYCLE_CAPABILITY

    made = h.principal(department, role)
    await h.person(
        made,
        department=department,
        grants=((AGENT_LIFECYCLE_CAPABILITY.value, Scope.department(department)),),
    )
    return made


async def _shelved(h: Harness, owner: str, *versions: Any) -> None:
    """Version rows, as a published version is kept: signed, and inserted for good."""
    from brain.agents.install_store import version_values
    from brain.tables.template import TemplateVersionRow

    await h.execute(
        *h.attributed(owner),
        *(insert(TemplateVersionRow).values(**version_values(one)) for one in versions),
    )


def _manifest(agent_id: str, owner: str, version: int, persona: str, *, rung: Any = None) -> Any:
    from brain.agents.template import (
        LeashRung,
        ManifestAuthority,
        ManifestGuardrails,
        ManifestIdentity,
        TemplateManifest,
    )

    leash = () if rung is None else (LeashRung(target=TARGET, rung=rung),)
    return TemplateManifest(
        identity=ManifestIdentity(
            template_id=agent_id,
            version=version,
            published_by=owner,
            display_name="Acceptance check agent",
        ),
        persona=persona,
        authority=ManifestAuthority(scope=Scope.department(A)),
        guardrails=ManifestGuardrails(leash=leash),
    )


async def _an_agent_behind_its_template(h: Harness, owner: str, key: str) -> tuple[str, Any]:
    """An agent installed from version one with a persona of its own, and version two shelved."""
    from brain.agents.install_store import agent_values
    from brain.agents.model import AgentAudience, answering_on
    from brain.agents.template import install, materialise, publish, set_field
    from brain.gate.context import Channel
    from brain.knowledge.visibility import Visibility
    from brain.tables.agent import AgentRow
    from brain.tables.template import TemplateInstanceRow

    agent_id = f"acceptance_{h.run}_behind"
    first = publish(_manifest(agent_id, owner, 1, FIRST), key=key, signed_by=owner, at=h.now)
    second = publish(_manifest(agent_id, owner, 2, SECOND), key=key, signed_by=owner, at=h.now)
    instance = set_field(
        install(first, key=key, instance_id=agent_id, created_by=owner, at=h.now),
        "persona",
        LOCAL,
        by=owner,
        at=h.now,
    )
    audience = AgentAudience(level=Visibility.DEPARTMENT, owner_id=owner, department=A)
    effective = materialise(first, instance, audience=audience)
    await _shelved(h, owner, first)
    await h.execute(
        *h.attributed(owner),
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
        insert(AgentRow).values(
            **agent_values(answering_on(effective.record, (Channel.CONSOLE.value,)))
        ),
    )
    await _shelved(h, owner, second)
    return agent_id, second


async def _review(h: Harness, app: FastAPI, who: str, agent_id: str) -> dict[str, Any]:
    from brain.agent_upgrade_routes import agent_upgrade

    return _body(await agent_upgrade(_request(app), agent_id, await _asking(h, who)))


@check(
    leaves=("M13.4.2", "M13.4.3", "M13.4.4", "M13.4.5"),
    sentence=(
        "An agent of acceptance_a with a persona of its own is shown the newer version of its "
        "template as one conflict to decide, to nobody of acceptance_b; a decline is recorded and "
        "can still be read past; accepting moves the pin, persona and hash together; both reach "
        "the ledger; a higher rung than the agent is on cannot be accepted but can be declined."
    ),
)
async def a_newer_version_is_reviewed_and_never_raises_a_rung(
    h: Harness,
) -> None:
    from brain.agent_upgrade_routes import (
        UpgradeAccepted,
        UpgradeDeclined,
        accept_agent_upgrade,
        decline_agent_upgrade,
    )
    from brain.agents.template import publish
    from brain.core.errors import Absent
    from brain.gate.injection import AutonomyTier
    from brain.tables.agent import AgentRow
    from brain.tables.template import TemplateInstanceRow
    from brain.tables.upgrade import UpgradeDeclineRow

    await h.found_departments()
    key = secrets.token_hex(32)
    app = _gallery(h, key)
    admin = await _administrator(h, "upgrader", A)
    outsider = await _administrator(h, "outsider", B)
    agent_id, _ = await _an_agent_behind_its_template(h, admin, key)

    review = await _review(h, app, admin, agent_id)
    if review["badge"] != "available" or review["to_version"] != 2 or review["from_version"] != 1:
        raise CheckFailedError(NO_REVIEW)
    if [one["path"] for one in review["conflicts"]] != ["persona"]:
        raise CheckFailedError(NOT_A_CONFLICT)
    try:
        await _review(h, app, outsider, agent_id)
    except Absent:
        pass
    else:
        raise CheckFailedError(OUTSIDER_TOLD)

    asking = await _asking(h, admin)
    drawn = {"to_version": review["to_version"], "expected_hash": review["expected_hash"]}
    declined = await decline_agent_upgrade(
        _request(app), agent_id, UpgradeDeclined(**drawn), asking
    )
    recorded = (
        await h.execute(
            select(UpgradeDeclineRow.declined_by).where(UpgradeDeclineRow.instance_id == agent_id)
        )
    ).scalar_one_or_none()
    after_decline = await _review(h, app, admin, agent_id)
    if declined.status_code != 200 or recorded != admin or after_decline["badge"] != "declined":
        raise CheckFailedError(NO_DECLINE)
    if len(after_decline["conflicts"]) != 1:
        raise CheckFailedError(DECLINE_HID_IT)
    declined_by = [
        actor
        for actor, details in await _changes(h, f"agent:{agent_id}", "agent")
        if details.get("change") == "upgrade_declined"
    ]
    if declined_by != [admin]:
        raise CheckFailedError(NOT_ON_THE_LEDGER)

    answered = await accept_agent_upgrade(
        _request(app),
        agent_id,
        UpgradeAccepted(**drawn, resolutions={"persona": "take_template"}),
        asking,
    )
    if answered.status_code != 200:
        raise CheckFailedError(NOT_ACCEPTED)
    moved = (
        await h.execute(select(TemplateInstanceRow).where(TemplateInstanceRow.id == agent_id))
    ).scalar_one()
    persona = (
        await h.execute(select(AgentRow.persona).where(AgentRow.id == agent_id))
    ).scalar_one()
    if (
        moved.template_version != 2
        or moved.effective_hash == review["expected_hash"]
        or "persona" in moved.overlay
        or persona != SECOND
    ):
        raise CheckFailedError(NOT_MOVED)
    if (await _review(h, app, admin, agent_id))["badge"] != "current":
        raise CheckFailedError(STILL_OFFERED)
    upgraded_by = [
        actor
        for actor, details in await _changes(h, f"agent:{agent_id}", "agent")
        if details.get("change") == "upgraded"
    ]
    if upgraded_by != [admin]:
        raise CheckFailedError(NOT_ON_THE_LEDGER)

    # Version three holds a target at a rung the agent is not on: shown, not accepted, declined.
    third = publish(
        _manifest(agent_id, admin, 3, SECOND, rung=AutonomyTier.ASSISTED),
        key=key,
        signed_by=admin,
        at=h.now,
    )
    await _shelved(h, admin, third)
    offered = await _review(h, app, admin, agent_id)
    if not offered["accept_unavailable"] or offered["to_version"] != 3:
        raise CheckFailedError(RUNG_NOT_SAID)
    drawn = {"to_version": offered["to_version"], "expected_hash": offered["expected_hash"]}
    refused = await accept_agent_upgrade(
        _request(app), agent_id, UpgradeAccepted(**drawn, resolutions={}), asking
    )
    pinned = (
        await h.execute(
            select(TemplateInstanceRow.template_version).where(TemplateInstanceRow.id == agent_id)
        )
    ).scalar_one()
    if refused.status_code != 409 or pinned != 2:
        raise CheckFailedError(RUNG_RAISED)
    turned_away = await decline_agent_upgrade(
        _request(app), agent_id, UpgradeDeclined(**drawn), asking
    )
    if turned_away.status_code != 200:
        raise CheckFailedError(NOT_DECLINABLE)
