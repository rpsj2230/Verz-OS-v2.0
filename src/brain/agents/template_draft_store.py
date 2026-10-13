"""An agent saved as a template, kept as a draft until its author publishes it (M13.8.15).

`brain.agents.authoring` decides everything about authoring a template (what a leak report asks,
what a decision may be, when a publish is allowed) and holds nothing. This holds a draft in
`agent.template_draft` (`0223`) so that the author can leave, the process can restart, and the
report is still there to be worked through one item at a time.

**A draft is its author's alone.** Every function takes the person acting and reads and writes as
them: the row's policies admit only the author, so a draft saved by one person is not a draft
another can read, decide or publish, and `load` answers `None` for both a draft that is not there
and one that is not theirs.

**The review is the document with every value hoisted out of it.** `review` returns
`authoring.hoisted_document`: the body with each literal the report asks about replaced by a token
naming its item, and beside it each item's kind and where it sits and no text. What a reviewer
reads has none of the agent's values in the places a decision is about. The decision itself is
taken against the item, one at a time, by `authoring.decide`, which refuses a hoist that answers its
own question; this only keeps the result.

**Publishing is the one door to an installable template.** `publish` signs the draft through
`authoring.publish_authored`, which refuses while any item is undecided, writes the
`agent.template_version` row an installation reads (`install_store.version_values`), and marks the
draft published with the version it became. Nothing else here writes a version, so a draft that is
not published is not a template anybody can install.

Task ids: M13.8.15
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from pydantic import JsonValue
from sqlalchemy import insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from brain.agents.authoring import (
    AuthoredDraft,
    Decision,
    LiteralKind,
    decide,
    hoisted_document,
    publish_authored,
)
from brain.agents.install_store import version_values
from brain.agents.template import SignedManifest, manifest_from_document
from brain.tables.template import TemplateVersionRow
from brain.tables.template_draft import DraftState, TemplateDraftRow


@dataclass(frozen=True)
class ReviewedItem:
    """One thing the author has to decide, with no text from the agent."""

    item_id: str
    kind: LiteralKind
    locations: tuple[str, ...]
    decided: str


@dataclass(frozen=True)
class Review:
    """A draft as it is shown for review: the hoisted body, the items and where each stands."""

    draft_id: uuid.UUID
    state: DraftState
    document: dict[str, JsonValue]
    items: tuple[ReviewedItem, ...]

    @property
    def undecided(self) -> int:
        return sum(1 for one in self.items if not one.decided)


async def _as(session: AsyncSession, principal: str) -> None:
    await session.execute(
        text("SELECT set_config('app.principal_id', :who, true)"), {"who": principal}
    )


async def save_draft(
    session: AsyncSession, draft: AuthoredDraft, *, source_agent_id: str | None = None
) -> uuid.UUID:
    """Keep an authored draft, in its author's own name, with no decision taken."""
    await _as(session, draft.author_id)
    made = TemplateDraftRow(
        author=draft.author_id,
        source_agent_id=source_agent_id,
        document=dict(draft.document),
        decisions={},
    )
    session.add(made)
    await session.flush()
    return made.id


async def _row(
    session: AsyncSession, draft_id: uuid.UUID, by: str, *, lock: bool = True
) -> TemplateDraftRow | None:
    """The draft if it is `by`'s. A lock is what a change takes. A published draft has none to
    give, because the update policy only reaches a draft, so reading one back does not ask."""
    await _as(session, by)
    query = select(TemplateDraftRow).where(
        TemplateDraftRow.id == draft_id, TemplateDraftRow.author == by
    )
    return (await session.execute(query.with_for_update() if lock else query)).scalar_one_or_none()


def _draft_of(row: TemplateDraftRow) -> AuthoredDraft:
    return AuthoredDraft(
        author_id=row.author,
        manifest=manifest_from_document(row.document),
        decisions={key: Decision.model_validate(value) for key, value in row.decisions.items()},
    )


async def load_draft(
    session: AsyncSession, draft_id: uuid.UUID, *, by: str
) -> AuthoredDraft | None:
    """The draft as the authoring module holds it, or None when it is not there or not `by`'s."""
    row = await _row(session, draft_id, by, lock=False)
    return None if row is None else _draft_of(row)


async def review(session: AsyncSession, draft_id: uuid.UUID, *, by: str) -> Review | None:
    """The draft shown for review, or None. See the module docstring."""
    row = await _row(session, draft_id, by, lock=False)
    if row is None:
        return None
    draft = _draft_of(row)
    return Review(
        draft_id=row.id,
        state=DraftState(row.state),
        document=hoisted_document(draft),
        items=tuple(
            ReviewedItem(
                item_id=item.item_id,
                kind=item.kind,
                locations=item.locations,
                decided=draft.decisions[item.item_id].disposition.value
                if item.item_id in draft.decisions
                else "",
            )
            for item in draft.report.items
        ),
    )


async def decide_item(
    session: AsyncSession, draft_id: uuid.UUID, item_id: str, decision: Decision, *, by: str
) -> bool:
    """Keep one decision about one item. False when the draft is not `by`'s or is published.

    `authoring.decide` refuses an item that is not on the report and a hoist that answers its own
    question, and those refusals are raised as they are.
    """
    row = await _row(session, draft_id, by)
    if row is None or row.state != DraftState.DRAFT.value:
        return False
    moved = decide(_draft_of(row), item_id, decision)
    await session.execute(
        update(TemplateDraftRow)
        .where(TemplateDraftRow.id == draft_id)
        .values(
            decisions={
                key: value.model_dump(mode="json") for key, value in moved.decisions.items()
            },
            updated_at=text("statement_timestamp()"),
        )
    )
    return True


async def publish_draft(
    session: AsyncSession, draft_id: uuid.UUID, *, key: str, by: str, at: datetime
) -> SignedManifest | None:
    """Sign the draft, write the version an install reads, and mark the draft published.

    None when the draft is not `by`'s or is already published. Raises
    `brain.agents.authoring.UndispositionedError` while any item has no decision, before anything
    is written.
    """
    row = await _row(session, draft_id, by)
    if row is None or row.state != DraftState.DRAFT.value:
        return None
    published = publish_authored(_draft_of(row), key=key, at=at)
    signed = published.signed
    await session.execute(insert(TemplateVersionRow).values(**version_values(signed)))
    await session.execute(
        update(TemplateDraftRow)
        .where(TemplateDraftRow.id == draft_id)
        .values(
            state=DraftState.PUBLISHED.value,
            published_version=signed.manifest.identity.version,
            published_at=at,
            updated_at=text("statement_timestamp()"),
        )
    )
    return signed
