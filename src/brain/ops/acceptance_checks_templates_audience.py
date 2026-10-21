"""The install acceptance checks for authoring a template from an agent, for a template's schema
version and overview, and for offering an agent beyond its level.

Every check writes only inside the check's rolled-back transaction, as reserved people of the two
reserved departments.

**What they prove.** A draft kept in the database is the author's alone, reviewed with each value
hoisted out, refused publication while any item is undecided and installable only once its author
publishes it (M13.8.15). A template signed under the first schema still verifies as it always did, a
second-schema one carries a signed overview that can name only a path no prompt is built from, and
the table refuses the rest (M13.8.17). A department or a person named beside an agent's level finds
it in the roster and gains nothing to read through it (M13.8.19).

**What they do not.** No route serves the draft yet, so these call the store the route would, and
the console draws none of it. The roster is the one surface read for the offer: other pages that
open an agent by address still answer from its level alone.

Task ids: M13.8.15, M13.8.17, M13.8.19
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime
from typing import Any, Final

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 1750

A, B = RESERVED_DEPARTMENTS

#: A value of the company's own, which a template must not carry out of the install.
THE_EMAIL: Final = "bob@acme.example"


async def _refused(h: Harness, who: str, statement: str, **values: object) -> bool:
    """Whether the database refused this statement as the application role in `who`'s name, in a
    savepoint that is then undone. An UPDATE the row policy hides from the role changes no row and
    raises nothing, so that counts as refused too."""
    async with h.sessions() as session:
        await session.execute(
            text("SELECT set_config('app.principal_id', :who, true)"), {"who": who}
        )
        nested = await session.begin_nested()
        try:
            done = await session.execute(text(statement), values)
        except DBAPIError:
            return True
        else:
            if statement.lstrip().upper().startswith("UPDATE") and done.rowcount == 0:  # type: ignore[attr-defined]
                return True
        finally:
            await nested.rollback()
    return False


def _manifest(template_id: str, author: str, *, persona: str, summary: str = "A summary.") -> Any:
    from brain.agents.template import ManifestIdentity, TemplateManifest

    return TemplateManifest(
        identity=ManifestIdentity(
            template_id=template_id,
            version=1,
            published_by=author,
            display_name="Acceptance template",
            summary=summary,
        ),
        persona=persona,
    )


# ------------------------------------------------- 1. a template draft that survives (M13.8.15)
@check(
    leaves=("M13.8.15", "M27.11.7"),
    sentence=(
        "An agent saved as a template is kept as a draft only its author reads, shown for review "
        "with every value hoisted out, refused publication while any item is undecided, written "
        "as an installable version only when its author publishes it, and then not published or "
        "decided again."
    ),
)
async def a_template_draft_is_installable_only_once_its_author_publishes(h: Harness) -> None:
    from sqlalchemy import select

    from brain.agents.authoring import (
        AuthoredDraft,
        Decision,
        Disposition,
        UndispositionedError,
    )
    from brain.agents.template_draft_store import (
        decide_item,
        load_draft,
        publish_draft,
        review,
        save_draft,
    )
    from brain.tables.template import TemplateVersionRow
    from brain.tables.template_draft import DraftState

    await h.found_departments()
    author, other = h.principal(A, "author"), h.principal(A, "other")
    await h.person(author, department=A)
    await h.person(other, department=A)
    template_id = f"acceptance_{h.run}_authored"
    persona = f"Answer questions about the Acme account and write to {THE_EMAIL} when stuck."
    draft = AuthoredDraft(
        author_id=author, manifest=_manifest(template_id, author, persona=persona)
    )
    key = secrets.token_hex(32)
    at = datetime.now(UTC)

    async with h.sessions() as session:
        draft_id = await save_draft(session, draft, source_agent_id=f"acceptance_{h.run}_agent")
        await session.commit()

    # A restart: a fresh session knows nothing but the table.
    async with h.sessions() as session:
        kept = await load_draft(session, draft_id, by=author)
        stranger = await load_draft(session, draft_id, by=other)
        shown = await review(session, draft_id, by=author)
        elsewhere = await review(session, draft_id, by=other)
    if kept is None or kept.document != draft.document:
        raise CheckFailedError("a draft did not come back the same after a restart")
    if stranger is not None or elsewhere is not None:
        raise CheckFailedError("a draft was read by somebody other than its author")
    if shown is None or not shown.items or shown.undecided != len(shown.items):
        raise CheckFailedError("a draft was not shown with every item waiting on a decision")
    if THE_EMAIL in json.dumps(shown.document):
        raise CheckFailedError("a draft shown for review still held the value it asks about")
    if any(THE_EMAIL in str(one) for one in shown.items):
        raise CheckFailedError("a review item carried the text it asks about")

    async def versions() -> list[str]:
        async with h.sessions() as session:
            found = await session.execute(
                select(TemplateVersionRow.template_id).where(
                    TemplateVersionRow.template_id == template_id
                )
            )
            return list(found.scalars())

    async with h.sessions() as session:
        try:
            await publish_draft(session, draft_id, key=key, by=author, at=at)
        except UndispositionedError:
            pass
        else:
            raise CheckFailedError("a draft with undecided items was published")
    if await versions():
        raise CheckFailedError("a draft that was not published could be installed")

    async with h.sessions() as session:
        for one in shown.items:
            # Only the address is redacted: the slugs and the prose are accepted, because a
            # redacted value cannot sit where a grammar names the shape.
            kind = Disposition.REDACT if one.kind.value == "email" else Disposition.ACCEPT
            decision = Decision(disposition=kind, by=author, at=at)
            if not await decide_item(session, draft_id, one.item_id, decision, by=author):
                raise CheckFailedError("an author's own decision was refused")
            if await decide_item(session, draft_id, one.item_id, decision, by=other):
                raise CheckFailedError("a decision was taken on a draft by somebody else")
        await session.commit()
    async with h.sessions() as session:
        if await publish_draft(session, draft_id, key=key, by=other, at=at) is not None:
            raise CheckFailedError("a draft was published by somebody other than its author")
        signed = await publish_draft(session, draft_id, key=key, by=author, at=at)
        again = await publish_draft(session, draft_id, key=key, by=author, at=at)
        await session.commit()
    async with h.sessions() as session:
        done = await review(session, draft_id, by=author)
    if signed is None or again is not None:
        raise CheckFailedError("a draft was not published once, by its author")
    if await versions() != [template_id]:
        raise CheckFailedError("a published draft did not become one installable version")
    if THE_EMAIL in json.dumps(dict(signed.manifest.document())):
        raise CheckFailedError("a published template still carried the value that was redacted")
    if done is None or done.state is not DraftState.PUBLISHED:
        raise CheckFailedError("a published draft did not say it was published")
    reopen = "UPDATE agent.template_draft SET state = 'draft' WHERE id = :id"
    if not await _refused(h, author, reopen, id=str(draft_id)):
        raise CheckFailedError("a published draft was put back to a draft")


# ----------------------------------- 2. the schema version and the overview (M13.8.17)
@check(
    leaves=("M13.8.17",),
    sentence=(
        "A template signed under the first schema verifies exactly as it did, one signed under the "
        "second carries a signed overview path that only the display name or the summary may be, "
        "the overview is in no manifest path a prompt is built from, and the table refuses an "
        "overview on the first schema or on any other path."
    ),
)
async def a_template_keeps_its_schema_and_its_overview_is_for_people(h: Harness) -> None:
    from brain.agents.install_store import version_values
    from brain.agents.template import (
        MANIFEST_PATHS,
        MANIFEST_SCHEMA,
        OVERVIEW_PATHS,
        SignedManifest,
        TemplateError,
        canonical,
        content_digest,
        publish,
        verify,
    )
    from brain.tables.template import TemplateVersionRow

    await h.found_departments()
    author = h.principal(A, "author")
    await h.person(author, department=A)
    key = secrets.token_hex(32)
    at = datetime.now(UTC)
    word = h.word()

    old = _manifest(f"acceptance_{h.run}_old", author, persona="Answers one thing.")
    first = publish(old, key=key, signed_by=author, at=at)
    expected = hashlib.sha256(
        f"{len(MANIFEST_SCHEMA)}:{MANIFEST_SCHEMA}".encode()
        + f"{len(canonical(old.document()))}:{canonical(old.document())}".encode()
    ).hexdigest()
    if first.schema_version != 1 or first.overview_path or first.content_digest != expected:
        raise CheckFailedError("a template published as before was not the first schema as it was")
    verify(first, key=key)

    new = _manifest(
        f"acceptance_{h.run}_new", author, persona="Answers another.", summary=f"Overview {word}."
    )
    second = publish(new, key=key, signed_by=author, at=at, overview_path="identity.summary")
    if second.schema_version != 2 or second.overview_path != "identity.summary":
        raise CheckFailedError("a template that names an overview was not the second schema")
    verify(second, key=key)
    if content_digest(new) == second.content_digest:
        raise CheckFailedError("the second schema's digest did not cover its overview")
    for path in ("persona", "guardrails.leash", "golden_set", "skills"):
        try:
            publish(new, key=key, signed_by=author, at=at, overview_path=path)
        except TemplateError:
            continue
        raise CheckFailedError("a template named a path a prompt is built from as its overview")
    try:
        verify(second.model_copy(update={"signature": first.signature}), key=key)
    except TemplateError:
        pass
    else:
        raise CheckFailedError(
            "a second-schema template verified under the first schema's signature"
        )

    if set(OVERVIEW_PATHS) - set(MANIFEST_PATHS) or "persona" in OVERVIEW_PATHS:
        raise CheckFailedError(
            "an overview may be a path that is not a manifest path or is the persona"
        )

    # What is stored loads and verifies, for both schemas, as the roster reads it back.
    third = publish(
        _manifest(f"acceptance_{h.run}_third", author, persona="Answers a third thing."),
        key=key,
        signed_by=author,
        at=at,
        overview_path="identity.display_name",
    )
    async with h.sessions() as session:
        for signed in (first, second, third):
            session.add(TemplateVersionRow(**version_values(signed)))
        # The positive sibling of the refusals below: the other permitted path is accepted.
        await session.flush()
        await session.commit()
    for signed in (first, second):
        row = await _stored(h, signed.manifest.identity.template_id)
        loaded = SignedManifest(
            manifest=signed.manifest,
            content_digest=row.content_digest,
            signature=row.signature,
            signed_by=row.signed_by,
            signed_at=row.signed_at,
            schema_version=row.schema_version,
            overview_path=row.overview_path or "",
        )
        verify(loaded, key=key)
    if (await _stored(h, new.identity.template_id)).overview_path != "identity.summary":
        raise CheckFailedError("a stored overview was not the path that was signed")

    holding = [path for path, value in new.document().items() if word in json.dumps(value)]
    if holding != ["identity.summary"] or set(new.document()) != set(MANIFEST_PATHS):
        raise CheckFailedError("the overview was in a manifest path other than the one it names")
    if word in new.persona or any("overview" in path for path in new.document()):
        raise CheckFailedError("the overview reached the text a prompt is built from")

    insert = (
        "INSERT INTO agent.template_version (template_id, version, content_digest, signature, "
        "signed_by, signed_at, document, schema_version, overview_path) "
        "SELECT :id, 7, content_digest, signature, signed_by, signed_at, document, :schema, :path "
        "FROM agent.template_version WHERE template_id = :source"
    )
    base = {"source": new.identity.template_id}
    if not await _refused(
        h, author, insert, id=f"{h.run}_a", schema=1, path="identity.summary", **base
    ):
        raise CheckFailedError("the database accepted an overview on the first schema")
    if not await _refused(h, author, insert, id=f"{h.run}_b", schema=2, path="persona", **base):
        raise CheckFailedError("the database accepted an overview that is the persona")


async def _stored(h: Harness, template_id: str) -> Any:
    from sqlalchemy import select

    from brain.tables.template import TemplateVersionRow

    async with h.sessions() as session:
        return (
            await session.execute(
                select(TemplateVersionRow).where(TemplateVersionRow.template_id == template_id)
            )
        ).scalar_one()


# ------------------------------------------ 3. offered beyond its level (M13.8.19)
@check(
    leaves=("M13.8.19",),
    sentence=(
        "A department and a person named beside an agent's level find it in the roster and nobody "
        "else does, the added audience changes no predicate a run is narrowed by and no ceiling, "
        "a withdrawn offer stops finding it, and the table refuses a row in another's name."
    ),
)
async def an_agent_offered_beyond_its_level_is_found_and_reaches_no_more(h: Harness) -> None:
    from brain.agent_routes import agents
    from brain.agents.audience_store import add_extra, extras_of, remove_extra
    from brain.agents.model import AgentAudience, audience_scope
    from brain.knowledge.visibility import Visibility
    from brain.listing import ListAsked
    from brain.ops.acceptance_checks_agents import _app, _request
    from brain.ops.acceptance_checks_templates import _asking
    from brain.ops.acceptance_workspace import installed_agent
    from brain.tables.audience_extra import ExtraKind

    await h.found_departments()
    steward, member = h.principal(A, "steward"), h.principal(A, "member")
    outsider, named, bystander = (h.principal(B, role) for role in ("outsider", "named", "by"))
    for one, department in ((steward, A), (member, A), (outsider, B), (named, B), (bystander, B)):
        await h.person(one, department=department)
    audience = AgentAudience(level=Visibility.DEPARTMENT, owner_id=steward, department=A)
    agent = await installed_agent(h, steward, suffix="offered", audience=audience)
    app = _app(h)
    mine = ListAsked(search=f"acceptance_{h.run}", limit=50)

    async def found_by(reader: str) -> bool:
        page = await agents(_request(app), await _asking(h, reader), mine)
        return agent in {one.agent_id for one in page.items}

    if not await found_by(member) or await found_by(outsider) or await found_by(named):
        raise CheckFailedError("an agent was not found by exactly the department its level names")

    async with h.sessions() as session:
        await add_extra(session, agent_id=agent, kind=ExtraKind.DEPARTMENT, value=B, by=steward)
        again = await add_extra(
            session, agent_id=agent, kind=ExtraKind.DEPARTMENT, value=B, by=steward
        )
        await add_extra(session, agent_id=agent, kind=ExtraKind.PERSON, value=member, by=steward)
        await session.commit()
        offered = (await extras_of(session)).get(agent)
    if offered is None or offered.departments != (B,) or offered.people != (member,) or not again:
        raise CheckFailedError("an offer was not kept once, as a department and a person")
    if not await found_by(outsider) or not await found_by(named) or not await found_by(member):
        raise CheckFailedError("an agent offered to a department was not found by its members")

    widened = AgentAudience(
        level=Visibility.DEPARTMENT,
        owner_id=steward,
        department=A,
        extra_departments=(B,),
        extra_people=(member,),
    )
    if audience_scope(widened) != audience_scope(audience):
        raise CheckFailedError("an added audience changed the predicate an agent is narrowed by")
    before = await _reach_of(h, agent, outsider)
    async with h.sessions() as session:
        await remove_extra(session, agent_id=agent, kind=ExtraKind.DEPARTMENT, value=B, by=steward)
        gone = await remove_extra(
            session, agent_id=agent, kind=ExtraKind.DEPARTMENT, value=B, by=steward
        )
        await session.commit()
    if gone or await found_by(outsider):
        raise CheckFailedError("a withdrawn offer still found the agent, or was withdrawn twice")
    if await _reach_of(h, agent, outsider) != before:
        raise CheckFailedError("offering an agent changed what its caller could reach through it")

    insert = (
        "INSERT INTO agent.audience_extra (agent_id, kind, value, added_by) "
        "VALUES (:agent, 'person', :value, :by)"
    )
    if not await _refused(h, steward, insert, agent=agent, value=bystander, by=outsider):
        raise CheckFailedError("the database accepted an offer in another person's name")
    if await _refused(h, steward, insert, agent=agent, value=bystander, by=steward):
        raise CheckFailedError("the database refused an offer in the session's own name")
    rewrite = "UPDATE agent.audience_extra SET value = :value WHERE agent_id = :agent"
    if not await _refused(h, steward, rewrite, agent=agent, value=bystander):
        raise CheckFailedError("the database allowed an offer to be rewritten")


async def _reach_of(h: Harness, agent: str, caller: str) -> Any:
    """What a run of this agent could reach for this caller: the one intersection, in the shape the
    check compares. Never touched by the offer, which is what the check asserts."""
    from sqlalchemy import select

    from brain.agent_routes import record_of
    from brain.console.reach_view import run_reach
    from brain.tables.agent import AgentRow

    async with h.sessions() as session:
        row = (await session.execute(select(AgentRow).where(AgentRow.id == agent))).scalar_one()
    record = record_of(row)
    if record is None:
        raise CheckFailedError("an agent made for the check did not construct")
    return sorted(
        (one.capability.value, one.scope.model_dump_json())
        for one in run_reach(await h.reach(caller), record).grants
    )
