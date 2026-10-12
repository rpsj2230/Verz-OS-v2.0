"""Install acceptance check for an agent's manifest taken out as a document and brought back in.

A builder of acceptance_a publishes an agent whose instructions carry a company's address, exports
its manifest through the route the Profile's menu calls, and brings the document back as a new
agent's draft through the route the Drafts page calls. **The export is the agent without the
company's details**: every shaped literal is redacted and named by kind and place, never by value,
and the install's own answers to a template's questions are not reachable from the export at all.
**The import lands as a draft and publishes nothing**: the leak scan is run over the document and
its findings come back with the draft, so a detail in a document from somewhere else is in front of
the person who is about to publish it.

Everything written is in the check's rolled-back transaction, for reserved people of acceptance_a.

Task ids: M27.15.28
"""

from __future__ import annotations

import secrets
from typing import Any, Final

from sqlalchemy import select

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_checks_builder import (
    _body,
    _builder,
    _document,
    _draft,
    _publish,
    _saved_and_checked,
)
from brain.ops.acceptance_checks_templates import _asking, _gallery, _request
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1350

A, _ = RESERVED_DEPARTMENTS


@check(
    leaves=("M27.15.28",),
    sentence=(
        "An agent whose instructions name an email address exports its manifest without the "
        "address, naming that one was taken out and never what it was; brought back in, the "
        "exported document lands as a new unpublished draft with nothing to flag, the original "
        "document lands with the address flagged, and a person who may not build is refused both."
    ),
)
async def a_manifest_leaves_without_company_details_and_returns_as_a_draft(
    h: Harness,
) -> None:
    from brain.agent_builder_routes import (
        ManifestImportAsked,
        export_agent_manifest,
        import_agent_manifest,
    )
    from brain.core.errors import Absent
    from brain.tables.agent import AgentRow

    builder = await _builder(h, "exporter")
    outsider = h.principal(A, "outsider")
    await h.person(outsider, department=A)
    app = _gallery(h, secrets.token_hex(32))
    address = f"{h.word().lower()}@acceptance.invalid"
    persona = f"Answers an install acceptance check and sends anything else to {address}."
    draft = await _draft(h, app, builder)
    agent_id = str(draft["agent_id"])
    original = _document(agent_id, persona=persona)
    revision = await _saved_and_checked(h, app, builder, draft, original)
    status, _ = await _publish(h, app, builder, draft["draft_id"], revision)
    if status != 201:
        raise CheckFailedError("the check's agent could not be published to export")

    exported = _body(
        await export_agent_manifest(_request(app), agent_id, await _asking(h, builder))
    )
    document: dict[str, Any] = exported["document"]
    if address in repr(document) or not document.get("persona"):
        raise CheckFailedError("an export kept a company's address, or lost the instructions")
    if [(one["kind"], one["places"]) for one in exported["redacted"]] != [("email", ["persona"])]:
        raise CheckFailedError("an export did not name what it took out by kind and place only")
    if address in repr(exported["redacted"]):
        raise CheckFailedError("the list of what an export took out carried the value")

    importing = ManifestImportAsked(document=document)
    brought = _body(
        await import_agent_manifest(_request(app), importing, await _asking(h, builder))
    )
    if brought["kind"] != "new" or brought["agent_id"] == agent_id:
        raise CheckFailedError("an imported document did not land as a new agent's draft")
    if brought["company_details"]:
        raise CheckFailedError("an exported document was flagged with details it no longer holds")
    flagged = _body(
        await import_agent_manifest(
            _request(app), ManifestImportAsked(document=original), await _asking(h, builder)
        )
    )
    if [one["kind"] for one in flagged["company_details"]] != ["email"]:
        raise CheckFailedError("an imported document's company detail was not found by the scan")
    made = (
        await h.execute(
            select(AgentRow.id).where(AgentRow.id.in_([brought["agent_id"], flagged["agent_id"]]))
        )
    ).all()
    if made:
        raise CheckFailedError("importing a document made an agent rather than a draft")

    try:
        await export_agent_manifest(_request(app), agent_id, await _asking(h, outsider))
    except Absent:
        pass
    else:
        raise CheckFailedError("a person who may not build was given an agent's manifest")
    try:
        await import_agent_manifest(_request(app), importing, await _asking(h, outsider))
    except Absent:
        pass
    else:
        raise CheckFailedError("a person who may not build could bring a document in")
