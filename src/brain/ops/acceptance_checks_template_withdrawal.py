"""The install acceptance check for withdrawing a template version, and moving a template.

What an install shows is the product's own routes, asked as the pages call them, by three reserved
people of acceptance_a over a template the check signs with a key made for it: an administrator who
holds the install authority over the company and the switch, an installer who holds it over one
department, and a member who holds the gallery and nothing else. The agent installed from the
template first is the one a withdrawal must not touch.

**What is proved is the five things the leaf says.** A version is withdrawn and the withdrawal is
undone, each as a row beside the last (the table refuses an edit and a removal, and the ledger holds
an entry for each, naming who). A withdrawn version is not offered to a new install: the template's
page answers the version before it, the version's install page answers a version nobody published,
and an agent's upgrade review holds no offer of it. **An installed agent stays pinned**: the agent
made from the version, and the version it names, are as they were whether the version is withdrawn
or not. And a template leaves as a signed document and arrives as a version this install signs: read
first, with nothing written, then written once under the importer's name, after which it installs.

**The authority and the switch are asked both ways.** An installer over a department and a member
are refused in the words a missing version gets, and the switch is turned off and on through the
Features route and never assumed, because an install that already has it on is not the empty
state. A withdrawal and an export are refused with it off, and an undo is allowed.

**What is not proved here.** That another install's own document is accepted needs another install;
the document's signature is made by a key this check holds and is reported unchecked, which is what
a second install would say of any document. Who may trust whose signature is
`docs/needs-rupash.md` item 236.

Task ids: M27.15.35
"""

from __future__ import annotations

import json
import secrets
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Final, cast

from sqlalchemy import delete, insert, select, update

from brain.core.errors import Absent
from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_operations_console import (
    asking_as,
    console_for,
    screen_grants,
    traced,
)
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI

    from brain.agents.template import SignedManifest

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2635

A, _B = RESERVED_DEPARTMENTS

# What the check says, one sentence for each way the property can fail.
WITHDRAWN_BY_A_DEPARTMENTS_INSTALLER: Final = (
    "a person holding the install authority over one department only withdrew a version"
)
WITHDRAWN_BY_A_MEMBER: Final = "a person with the gallery and no authority withdrew a version"
REFUSED_WITH_A_DIFFERENT_FACE: Final = (
    "a caller without the authority was refused differently from one asking for a missing version"
)
WITHDRAWN_WITH_THE_SWITCH_OFF: Final = "a version was withdrawn while the switch was off"
EXPORTED_WITH_THE_SWITCH_OFF: Final = "a template was exported while the switch was off"
NOT_WITHDRAWN: Final = "an administrator's withdrawal of a version was not recorded"
A_WITHDRAWAL_WAS_REPEATED: Final = "a version already withdrawn was withdrawn a second time"
STILL_OFFERED: Final = "a withdrawn version was still offered to a new install"
OFFERED_TO_AN_UPGRADE: Final = "a withdrawn version was offered to an agent as an upgrade"
THE_OTHER_VERSION_WAS_HIDDEN: Final = "withdrawing one version hid the version before it"
AN_AGENT_WAS_MOVED: Final = "withdrawing the version an agent was installed from changed the agent"
THE_UNDO_WAS_REFUSED_WITH_THE_SWITCH_OFF: Final = (
    "undoing a withdrawal was refused while the switch was off"
)
NOT_OFFERED_AGAIN: Final = "an undone withdrawal did not offer the version again"
A_HISTORY_WAS_EDITED: Final = "a withdrawal could be edited or removed in place"
NOT_ONE_ROW_A_CHANGE: Final = "a withdrawal and its undoing were not two rows"
NOT_IN_THE_LEDGER: Final = "a withdrawal or its undoing left no entry naming who made it"
NOT_EXPORTED: Final = "a template version was not exported as a signed document"
IMPORT_WROTE_ON_A_READING: Final = "reading a template document for import wrote something"
IMPORT_NOT_WRITTEN: Final = "a template document confirmed for import was not added"
IMPORT_NOT_SIGNED_HERE: Final = "an imported template was not signed by this install's key"
IMPORT_NOT_IN_ITS_NAME: Final = "an imported template was not published in the importer's name"
IMPORT_NOT_IN_THE_LEDGER: Final = (
    "an imported template left no publication entry naming the importer"
)
IMPORT_WRITTEN_TWICE: Final = "importing a template twice wrote two versions"
SHIPPED_ID_TAKEN: Final = "a document naming an id this release ships was imported"
NOT_INSTALLABLE_AFTER_IMPORT: Final = "an imported template could not be installed from"


def _copy(template_id: str) -> Any:
    from brain.agents.catalogue import business_analyst
    from brain.ops.acceptance_checks_templates import _copy as copied

    return copied(business_analyst(), template_id)


async def _person(h: Harness, role: str, grants: tuple[tuple[str, Scope], ...]) -> str:
    made = h.principal(A, role)
    await h.person(made, department=A, grants=grants)
    return made


def _said(answered: Any) -> dict[str, Any]:
    """What a route answered, as data: a refusal's body or a view's fields."""
    if hasattr(answered, "body"):
        return cast("dict[str, Any]", json.loads(bytes(answered.body)))
    return cast("dict[str, Any]", answered.model_dump(mode="json"))


async def _absent(call: Any) -> str | None:
    """What a route refused as a version nobody published, in its own words, or None if answered."""
    try:
        await call
    except Absent as refusal:
        return str(refusal.public_message)
    return None


async def _refused_by_the_database(h: Harness, actor: str, statement: Any) -> bool:
    from sqlalchemy.exc import DBAPIError

    try:
        await h.execute(*h.attributed(actor), statement)
    except DBAPIError:
        return True
    return False


@check(
    leaves=("M27.15.35",),
    sentence=(
        "An administrator withdraws a template version with a reason and undoes it, each a row and "
        "a ledger entry naming who; a withdrawn version is not offered to a new install or as an "
        "upgrade and the agent installed from it stays as it was; a department's installer and a "
        "member are refused; the switch gates a withdrawal and never an undo; an exported "
        "template is imported once, signed here."
    ),
)
async def a_withdrawn_version_is_not_offered_and_agents_stay_pinned(
    h: Harness,
) -> None:
    from brain.agent_lifecycle_routes import template_version
    from brain.agent_routes import TEMPLATE_SCREEN, agent_template
    from brain.agent_upgrade_routes import StoredAgentUpgrades
    from brain.agents.creation import AGENT_INSTALL_CAPABILITY
    from brain.agents.install_store import version_values
    from brain.agents.template import publish, verify
    from brain.agents.template_withdrawal import EXPORT_SCHEMA, export_document
    from brain.feature_routes import SwitchAsked, switch_feature
    from brain.ops.acceptance_checks_templates import _asking, _gallery, _install, _request
    from brain.ops.features_declared.template_withdrawal import TEMPLATE_WITHDRAWAL
    from brain.prompt_routes import signed_of
    from brain.tables.agent import AgentRow
    from brain.tables.audit import AuditEntryRow
    from brain.tables.template import TemplateInstanceRow, TemplateVersionRow
    from brain.tables.template_withdrawal import TemplateWithdrawalRow
    from brain.template_withdrawal_routes import (
        TemplateImportAsked,
        WithdrawAsked,
        export_template_version,
        import_template,
        template_withdrawal,
        undo_template_withdrawal,
        withdraw_template_version,
    )

    await h.found_departments()
    gallery = screen_grants(TEMPLATE_SCREEN)
    administrator = await _person(
        h,
        "templates",
        (
            *gallery,
            (AGENT_INSTALL_CAPABILITY.value, Scope.unrestricted()),
            ("admin:feature", Scope.unrestricted()),
        ),
    )
    installer = await _person(
        h, "installer", (*gallery, (AGENT_INSTALL_CAPABILITY.value, Scope.department(A)))
    )
    member = await _person(h, "member", gallery)
    key = secrets.token_hex(32)
    app: FastAPI = _gallery(h, key)
    template_id = f"acceptance_{h.run}_withdrawn"
    other_id = f"acceptance_{h.run}_never_made"

    def version(number: int, persona: str) -> SignedManifest:
        base = _copy(template_id)
        identity = base.identity.model_copy(update={"version": number})
        return publish(
            base.model_copy(update={"identity": identity, "persona": persona}),
            key=key,
            signed_by=administrator,
            at=h.now,
        )

    first, second = version(1, _copy(template_id).persona), version(2, "Answers the check, again.")
    for one in (first, second):
        await h.execute(
            *h.attributed(administrator), insert(TemplateVersionRow).values(**version_values(one))
        )
    agent = (await _install(h, app, administrator, first))["agent"]["agent_id"]

    async def switched(on: bool, n: int) -> None:
        async with traced(h, n):
            await switch_feature(
                console_for(h).request("POST"),
                TEMPLATE_WITHDRAWAL.name,
                SwitchAsked(on=on),
                await asking_as(h, administrator, strong=True),
            )

    async def withdraw(who: str, number: int, why: str, n: int) -> Any:
        async with traced(h, n):
            return await withdraw_template_version(
                _request(app), template_id, number, WithdrawAsked(reason=why), await _asking(h, who)
            )

    async def undo(who: str, number: int, n: int) -> Any:
        async with traced(h, n):
            return await undo_template_withdrawal(
                _request(app), template_id, number, await _asking(h, who)
            )

    async def page(who: str) -> int | None:
        try:
            shown = await agent_template(_request(app), template_id, await _asking(h, who))
        except Absent:
            return None
        return int(shown.entry.version)

    async def pinned() -> tuple[Any, ...]:
        instance = (
            await h.execute(select(TemplateInstanceRow).where(TemplateInstanceRow.id == agent))
        ).scalar_one()
        row = (await h.execute(select(AgentRow).where(AgentRow.id == agent))).scalar_one()
        return (
            instance.template_id,
            instance.template_version,
            instance.content_digest,
            instance.effective_hash,
            row.disabled_at,
            row.persona,
        )

    before = await pinned()
    if await page(member) != 2:
        raise CheckFailedError(STILL_OFFERED)

    # Who may, and who may not: the same refusal a missing version gets, with the switch on.
    await switched(False, 1)
    if _said(await withdraw(administrator, 2, "A made-up reason.", 2)).get("outcome") != "refused":
        raise CheckFailedError(WITHDRAWN_WITH_THE_SWITCH_OFF)
    exported_off = await _absent_or_said(
        export_template_version(_request(app), template_id, 1, await _asking(h, administrator))
    )
    if exported_off.get("outcome") != "refused":
        raise CheckFailedError(EXPORTED_WITH_THE_SWITCH_OFF)
    await switched(True, 3)
    missing = await _absent(
        template_withdrawal(_request(app), other_id, 1, await _asking(h, administrator))
    )
    by_an_installer = await _absent(withdraw(installer, 2, "A made-up reason.", 4))
    if by_an_installer is None:
        raise CheckFailedError(WITHDRAWN_BY_A_DEPARTMENTS_INSTALLER)
    by_a_member = await _absent(withdraw(member, 2, "A made-up reason.", 4))
    if by_a_member is None:
        raise CheckFailedError(WITHDRAWN_BY_A_MEMBER)
    if by_an_installer != missing or by_a_member != missing:
        raise CheckFailedError(REFUSED_WITH_A_DIFFERENT_FACE)

    # A withdrawal: recorded, not offered, nothing about an installed agent moved.
    done = _said(await withdraw(administrator, 2, "A made-up reason.", 5))
    if done.get("withdrawn") is not True or [one["set_by"] for one in done["changes"]] != [
        administrator
    ]:
        raise CheckFailedError(NOT_WITHDRAWN)
    repeated = _said(await withdraw(administrator, 2, "A made-up repeat.", 55))
    if repeated.get("outcome") != "refused":
        raise CheckFailedError(A_WITHDRAWAL_WAS_REPEATED)
    shown = await page(member)
    if shown is None:
        raise CheckFailedError(THE_OTHER_VERSION_WAS_HIDDEN)
    if shown != 1:
        raise CheckFailedError(STILL_OFFERED)
    refused_install = await _absent(
        template_version(_request(app), template_id, 2, await _asking(h, installer))
    )
    if refused_install is None:
        raise CheckFailedError(STILL_OFFERED)
    offered = await StoredAgentUpgrades(h.sessions).read(agent)
    if offered is None or offered.shelf.versions(template_id) != (1,):
        raise CheckFailedError(OFFERED_TO_AN_UPGRADE)

    # The pinned version withdrawn too: the template is gone for a new install and the agent is
    # exactly what it was.
    await withdraw(administrator, 1, "A made-up second reason.", 6)
    if await page(member) is not None:
        raise CheckFailedError(STILL_OFFERED)
    if await pinned() != before:
        raise CheckFailedError(AN_AGENT_WAS_MOVED)

    # With the switch off an undo is still allowed, and the version is offered again.
    await switched(False, 7)
    back = _said(await undo(administrator, 1, 8))
    await switched(True, 9)
    if back.get("withdrawn") is not False:
        raise CheckFailedError(THE_UNDO_WAS_REFUSED_WITH_THE_SWITCH_OFF)
    if await page(member) != 1:
        raise CheckFailedError(NOT_OFFERED_AGAIN)
    await undo(administrator, 2, 10)
    reading = await StoredAgentUpgrades(h.sessions).read(agent)
    if await page(member) != 2 or reading is None or reading.shelf.versions(template_id) != (1, 2):
        raise CheckFailedError(NOT_OFFERED_AGAIN)

    # Insert-only and audited: four rows beside each other, none editable, one entry each.
    rows = (
        await h.execute(
            select(TemplateWithdrawalRow.version, TemplateWithdrawalRow.withdrawn)
            .where(TemplateWithdrawalRow.template_id == template_id)
            .order_by(TemplateWithdrawalRow.seq)
        )
    ).all()
    if [(int(v), bool(w)) for v, w in rows] != [(2, True), (1, True), (1, False), (2, False)]:
        raise CheckFailedError(NOT_ONE_ROW_A_CHANGE)
    if not await _refused_by_the_database(
        h, administrator, update(TemplateWithdrawalRow).values(withdrawn=False)
    ) or not await _refused_by_the_database(h, administrator, delete(TemplateWithdrawalRow)):
        raise CheckFailedError(A_HISTORY_WAS_EDITED)
    entries = (
        await h.execute(
            select(AuditEntryRow.subject, AuditEntryRow.actor_id, AuditEntryRow.details)
            .where(
                AuditEntryRow.action == "publish",
                AuditEntryRow.subject.in_(
                    [f"artifact:{template_id}.v1", f"artifact:{template_id}.v2"]
                ),
            )
            .order_by(AuditEntryRow.seq)
        )
    ).all()
    changes = [(s, a, dict(d).get("change")) for s, a, d in entries if dict(d).get("change")]
    if changes != [
        (f"artifact:{template_id}.v2", administrator, "withdrawn"),
        (f"artifact:{template_id}.v1", administrator, "withdrawn"),
        (f"artifact:{template_id}.v1", administrator, "withdrawal_undone"),
        (f"artifact:{template_id}.v2", administrator, "withdrawal_undone"),
    ]:
        raise CheckFailedError(NOT_IN_THE_LEDGER)

    # A template leaves as a signed document and arrives as a version this install signs.
    exported = await export_template_version(
        _request(app), template_id, 1, await _asking(h, administrator)
    )
    if exported.document.get("schema") != EXPORT_SCHEMA or exported.document.get("signature") != (
        first.signature
    ):
        raise CheckFailedError(NOT_EXPORTED)
    arrived_id = f"acceptance_{h.run}_arrived"
    foreign = publish(
        _copy(arrived_id),
        key=secrets.token_hex(32),
        signed_by="elsewhere",
        at=h.now - timedelta(days=3),
    )
    document = export_document(foreign)

    async def importing(digest: str | None, who: str = administrator) -> Any:
        return await import_template(
            _request(app),
            TemplateImportAsked(document=document, expected_digest=digest),
            await _asking(h, who),
        )

    async def held() -> int:
        return len(
            (
                await h.execute(
                    select(TemplateVersionRow.version).where(
                        TemplateVersionRow.template_id == arrived_id
                    )
                )
            ).all()
        )

    read = _said(await importing(None))
    if await held() != 0 or read.get("imported") is not False:
        raise CheckFailedError(IMPORT_WROTE_ON_A_READING)
    if read.get("signed_by_this_install") is not False:
        raise CheckFailedError(IMPORT_NOT_SIGNED_HERE)
    written = _said(await importing(foreign.content_digest))
    if written.get("created") is not True or await held() != 1:
        raise CheckFailedError(IMPORT_NOT_WRITTEN)
    row = (
        await h.execute(
            select(TemplateVersionRow).where(TemplateVersionRow.template_id == arrived_id)
        )
    ).scalar_one()
    kept = signed_of(row)
    try:
        verify(kept, key=key)
    except Exception:
        raise CheckFailedError(IMPORT_NOT_SIGNED_HERE) from None
    if (kept.signed_by, kept.manifest.identity.published_by) != (administrator, administrator):
        raise CheckFailedError(IMPORT_NOT_IN_ITS_NAME)
    imported_entry = (
        await h.execute(
            select(AuditEntryRow.actor_id).where(
                AuditEntryRow.action == "publish",
                AuditEntryRow.subject == f"artifact:{arrived_id}.v1",
            )
        )
    ).scalar_one_or_none()
    if imported_entry != administrator:
        raise CheckFailedError(IMPORT_NOT_IN_THE_LEDGER)
    again = _said(await importing(foreign.content_digest))
    if again.get("created") is not False or await held() != 1:
        raise CheckFailedError(IMPORT_WRITTEN_TWICE)
    try:
        await _install(h, app, administrator, kept)
    except CheckFailedError:
        raise CheckFailedError(NOT_INSTALLABLE_AFTER_IMPORT) from None

    # A document naming an id this release ships is refused, whoever signed it.
    from brain.agents.catalogue import CATALOGUE

    shipped = publish(
        _copy(CATALOGUE[0].identity.template_id), key=key, signed_by=administrator, at=h.now
    )
    document = export_document(shipped)
    taken = _said(await importing(shipped.content_digest))
    if taken.get("outcome") != "refused":
        raise CheckFailedError(SHIPPED_ID_TAKEN)


async def _absent_or_said(call: Any) -> dict[str, Any]:
    """A route's refusal body, or its answer's fields. A missing version raises and is not this."""
    return _said(await call)
