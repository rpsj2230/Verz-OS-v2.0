"""The Resolution review screen, proved on an install through its API, called as its readers.

Records are written the way a sync leaves them, registered and matched by the worker's own run
(`registry_store`, `matching_store`), and the routes in `brain.resolution_routes` are then called
directly as three reserved people: a reviewer who reaches both kinds of record, a reviewer who
reaches only HubSpot's, and somebody without the reviewer's capability. Everything is inside the
check's transaction and nothing is committed.

**Each reader is given only grants the product's own rules name.** The reviewer's capability is
`resolution_routes.ENTITY_MERGE_CAPABILITY`, and what a record needs is read off its connector's
compiled classification (`brain.knowledge.connector_rows.CONNECTOR_ROW_ENTITIES`), so the check
holds the screen to the same reach Ask has rather than to grants written for the check.

Task ids: M14.6.4, M14.8.5
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Final, cast

from sqlalchemy import insert, text

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness
from brain.resolution.canonical import SourceRef
from brain.resolution.matching_store import StoredMatching
from brain.resolution.registry_store import StoredRegistry
from brain.tables.projection import ProjectedRecordRow

if TYPE_CHECKING:
    from fastapi import FastAPI

#: Where this module's check sits on the acceptance page.
CHECK_ORDER: Final = 436

A: Final = RESERVED_DEPARTMENTS[0]
HUBSPOT: Final = ("hubspot", "hubspot_company")
XERO: Final = ("xero", "contact")

NOT_ON_THE_SCREEN: Final = "a pair waiting for a person was not on the reviewer's screen"
NOT_IN_WORDS: Final = "a card's evidence was not a list of sentences without figures"
HALF_SHOWN: Final = "a reviewer who reaches one record of a pair was shown the pair"
NOT_ONE_404: Final = "a pair a reviewer may not see did not answer as one that does not exist"
SHOWN_WITHOUT_AUTHORITY: Final = "the queue was shown to somebody without the reviewer's capability"
NOT_MERGED: Final = "a reviewer's merge was not stored and audited in their name"
NOT_REJECTED: Final = "a reviewer's rejection was not stored, or merged something"
DECIDED_TWICE: Final = "a pair already decided was decided again, or merged after it was rejected"


def _capabilities(*sources: tuple[str, str]) -> tuple[str, ...]:
    """Every capability the records of these entities' field rules name, read off the product."""
    from brain.knowledge.connector_rows import CONNECTOR_ROW_ENTITIES

    found: set[str] = set()
    for source, entity in sources:
        for one in CONNECTOR_ROW_ENTITIES[source]:
            if one.entity == entity:
                found |= {rule.required_capability.value for rule in one.rules}
    return tuple(sorted(found))


async def _reader(h: Harness, role: str, *grants: str) -> Any:
    from brain.gate.admission import Assurance, admit
    from brain.gate.context import Channel
    from brain.identity.principal_store import StoredPrincipals

    made = h.principal(A, role)
    await h.person(made, department=A, grants=[(one, Scope.unrestricted()) for one in grants])
    person = await StoredPrincipals(h.sessions).live_principal(made)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    reach = admit(await h.reach(made), Channel.CONSOLE, Assurance.STRONG)
    # A cast at the routes' boundary, as `acceptance_checks_templates._asking` makes it.
    return cast(
        Any,
        SimpleNamespace(
            caller=SimpleNamespace(principal=person), reach=reach, now=datetime.now(UTC)
        ),
    )


def _app(h: Harness) -> FastAPI:
    from fastapi import FastAPI

    app = FastAPI()
    app.state.db_sessions = h.sessions
    return app


def _request(app: FastAPI) -> Any:
    from starlette.requests import Request

    return Request({"type": "http", "app": app, "headers": [], "method": "GET"})


async def _pairs(h: Harness) -> tuple[SourceRef, ...]:
    """A bare pair across HubSpot and Xero, and a close pair within HubSpot, both waiting."""
    word = h.word()
    named = (
        (HUBSPOT, {"name": f"Fabrikam Studio {word}"}),
        (XERO, {"name": f"Fabrikam Studio {word}"}),
        (HUBSPOT, {"name": f"Contoso Pharmaceuticals {word}"}),
        (HUBSPOT, {"name": f"Contosso Pharmaceuticals {word}"}),
    )
    refs = []
    for (source, entity), fields in named:
        source_id = f"acceptance-{h.run}-{secrets.token_hex(6)}"
        await h.execute(
            *h.attributed(),
            insert(ProjectedRecordRow).values(
                source=source, entity=entity, source_id=source_id, last_seen_at=h.now, fields=fields
            ),
        )
        refs.append(SourceRef(source=source, entity=entity, source_id=source_id))
    pepper = secrets.token_hex(32)
    await StoredRegistry(h.sessions).register(refs, pepper=pepper, now=h.now, by=h.actor)
    await StoredMatching(h.sessions).match(refs, pepper=pepper, now=h.now)
    return tuple(refs)


async def _item_of(h: Harness, one: SourceRef, two: SourceRef) -> str | None:
    found = await h.execute(
        text(
            "SELECT item_id FROM er.review_item WHERE left_source_id = ANY(:ids)"
            " AND right_source_id = ANY(:ids)"
        ).bindparams(ids=[one.source_id, two.source_id])
    )
    row = found.first()
    return None if row is None else str(row[0])


@check(
    leaves=("M14.6.4", "M14.8.5"),
    sentence=(
        "Two waiting pairs appear on the Resolution review screen to a reviewer reaching both "
        "records, with evidence in sentences; a reviewer reaching one half is shown neither that "
        "pair nor its page; the reviewer's merge and rejection are stored and the merge audited."
    ),
)
async def a_waiting_pair_is_reviewed_and_decided_in_the_reviewers_name(
    h: Harness,
) -> None:
    from brain.core.errors import Absent
    from brain.resolution_routes import (
        ENTITY_MERGE_CAPABILITY,
        ReviewDecisionAsked,
        decide_review_item,
        review_item_view,
        review_queue_view,
    )

    bare_left, bare_right, close_left, close_right = await _pairs(h)
    app = _app(h)
    await h.found_departments()
    both = await _reader(
        h, "reviewer", ENTITY_MERGE_CAPABILITY.value, *_capabilities(HUBSPOT, XERO)
    )
    narrow = await _reader(h, "narrow", ENTITY_MERGE_CAPABILITY.value, *_capabilities(HUBSPOT))
    nobody = await _reader(h, "nobody", *_capabilities(HUBSPOT, XERO))

    queue = await review_queue_view(_request(app), both)
    bare_item = await _item_of(h, bare_left, bare_right)
    close_item = await _item_of(h, close_left, close_right)
    shown = {card.item_id: card for card in queue.cards}
    if bare_item not in shown or close_item not in shown:
        raise CheckFailedError(NOT_ON_THE_SCREEN)
    lines = shown[close_item].lines
    if not lines or any(any(ch.isdigit() for ch in line) for line in lines):
        raise CheckFailedError(NOT_IN_WORDS)

    narrowed = await review_queue_view(_request(app), narrow)
    if bare_item in {card.item_id for card in narrowed.cards}:
        raise CheckFailedError(HALF_SHOWN)
    refusals = []
    for item_id in (bare_item, f"rev_{secrets.token_hex(16)}"):
        try:
            await review_item_view(_request(app), item_id, narrow)
        except Absent as refused:
            refusals.append(refused.public_message)
    if len(refusals) != 2 or len(set(refusals)) != 1:
        raise CheckFailedError(NOT_ONE_404)
    try:
        await review_queue_view(_request(app), nobody)
    except Absent:
        pass
    else:
        raise CheckFailedError(SHOWN_WITHOUT_AUTHORITY)

    reviewer = both.caller.principal.id
    merged = await decide_review_item(
        _request(app),
        str(close_item),
        ReviewDecisionAsked(decision="merge", reason="the same client, spelled twice"),
        both,
    )
    row = (
        await h.execute(
            text(
                "SELECT m.decided_by, m.review_ref, i.state, i.decided_by FROM er.merge m"
                " JOIN er.review_item i ON i.item_id = m.review_ref WHERE m.review_ref = :item"
            ).bindparams(item=close_item)
        )
    ).first()
    ledger = await h.execute(
        text(
            "SELECT count(*) FROM obs.audit_entry WHERE action = 'entity_merge'"
            " AND actor_id = :reviewer"
        ).bindparams(reviewer=reviewer)
    )
    audited = ledger.scalar_one()
    if (
        getattr(merged, "merged", False) is not True
        or row is None
        or tuple(row) != (reviewer, close_item, "merged", reviewer)
        or audited < 1
    ):
        raise CheckFailedError(NOT_MERGED)

    rejected = await decide_review_item(
        _request(app),
        str(bare_item),
        ReviewDecisionAsked(decision="reject", reason="two different clients"),
        both,
    )
    state = (
        await h.execute(
            text("SELECT state, decided_by FROM er.review_item WHERE item_id = :item").bindparams(
                item=bare_item
            )
        )
    ).first()
    if getattr(rejected, "merged", True) or state is None or tuple(state) != ("rejected", reviewer):
        raise CheckFailedError(NOT_REJECTED)
    again = await decide_review_item(
        _request(app),
        str(bare_item),
        ReviewDecisionAsked(decision="merge", reason="changed my mind"),
        both,
    )
    joined = await h.execute(
        text("SELECT count(*) FROM er.merge WHERE review_ref = :item").bindparams(item=bare_item)
    )
    if getattr(again, "status_code", None) != 409 or joined.scalar_one():
        raise CheckFailedError(DECIDED_TWICE)
