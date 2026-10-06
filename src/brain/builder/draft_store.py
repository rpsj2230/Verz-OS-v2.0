"""An agent's drafts kept in PostgreSQL, and a published draft written as the agent it makes.

`brain.builder.agent_drafts` decides what a draft is and what it may become; this module keeps it
and writes it, and decides nothing. **Every write is one transaction, told who is writing,** at what
reach and for which request (`brain.tables.audit.attributed_to`), and as whom the row may say it was
written (`app.principal_id`, which `0149`'s insert policies compare with the row's owner, saver or
actor), so a row naming somebody else is refused by the database and every row reaches the ledger
from `0149`'s triggers with the person who pressed.

**A publish writes the agent and the act that says so together, or nothing.** A new agent is the
three rows `brain.agents.install_store.StoredAgentInstalls.finish` writes (the signed version, the
instance that pins it, the agent) and the `published` act, in one transaction; the instance insert
does nothing on a conflict, so two presses race to one agent and the second is told it moved. An
edit adds the next signed version of the agent's own template, re-pins the instance to it and
rewrites the agent's configuration columns, each by compare-and-set against what the draft started
from: an instance whose configuration digest has moved since, or an agent archived since, matches
nothing, and the whole transaction is rolled back rather than half a publish being kept. See
`A_PUBLISH_IS_THE_AGENT_AND_ITS_RECORD_OR_NOTHING`.

**An edit keeps what the draft does not describe.** The steward, the audience, the builder, the
model pin and whether the agent is switched on are the agent's and not its manifest's, so none of
them is written, except that an agent the install now finds incomplete is switched off, which is
`brain.agents.install.AN_INCOMPLETE_INSTALL_IS_DISABLED_RATHER_THAN_SELECTABLE` applied to a change.

Task ids: M27.11.6
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Protocol, runtime_checkable

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agent_lifecycle_routes import FoundAgent
from brain.agent_routes import record_of
from brain.agents.install import Installation
from brain.agents.install_store import agent_values, instance_values, version_values
from brain.agents.model import AgentRecord
from brain.agents.template import SignedManifest, TemplateError, TemplateManifest, canonical_value
from brain.builder.agent_drafts import (
    Act,
    AgentDraft,
)
from brain.builder.draft_words import DraftAct, DraftKind
from brain.builder.drafts import ManifestDraft, Revision
from brain.identity.principal_store import PRINCIPAL_SETTING, StoredPrincipals
from brain.prompt_routes import every_agent_with_install, installed, signed_of
from brain.tables.agent import AgentRow
from brain.tables.audit import attributed_to
from brain.tables.manifest_draft import ManifestActRow, ManifestDraftRow, ManifestRevisionRow
from brain.tables.template import TemplateInstanceRow, TemplateVersionRow

#: Why a publish is written whole or not at all.
A_PUBLISH_IS_THE_AGENT_AND_ITS_RECORD_OR_NOTHING: Final = (
    "A published draft is the agent it makes and the act that says so, written in one "
    "transaction. An agent without its act is a change the draft does not show, and an act without "
    "its agent says something was published that was not, so a publish that finds the agent moved "
    "since the draft started is rolled back whole."
)

#: How many of a person's drafts one reading brings back, newest first.
MAX_DRAFTS: Final = 200


@dataclass(frozen=True)
class Attribution:
    """Who is writing, at what reach, for which request."""

    actor_id: str
    ent_hash: str
    trace_id: str


class _MovedError(Exception):
    """A compare-and-set matched nothing, so the transaction is rolled back."""


@runtime_checkable
class AgentDraftStore(Protocol):
    """What the builder's routes need of the tables. `StoredAgentDrafts` implements it."""

    async def draft(self, draft_id: str) -> AgentDraft | None: ...

    async def drafts_owned_by(self, owner_id: str) -> tuple[AgentDraft, ...]: ...

    async def waiting(self) -> tuple[AgentDraft, ...]: ...

    async def agent(self, agent_id: str) -> FoundAgent | None: ...

    async def versions_of(self, template_id: str) -> tuple[int, ...]: ...

    async def start(self, draft: AgentDraft, first: Revision, *, by: Attribution) -> None: ...

    async def append(self, revision: Revision, *, by: Attribution) -> bool: ...

    async def record(self, draft_id: str, act: Act, *, by: Attribution) -> bool: ...

    async def publish_new(
        self,
        draft_id: str,
        acts: Sequence[Act],
        signed: SignedManifest,
        installation: Installation,
        *,
        by: Attribution,
    ) -> bool: ...

    async def publish_edit(
        self,
        draft_id: str,
        acts: Sequence[Act],
        signed: SignedManifest,
        installation: Installation,
        *,
        base_hash: str,
        disabled_at: datetime | None,
        by: Attribution,
    ) -> bool: ...

    async def department_of(self, principal_id: str) -> str | None: ...

    async def newest_published(self, template_id: str) -> TemplateManifest | None: ...


def revision_of(row: ManifestRevisionRow) -> Revision:
    """A stored revision as the domain's, its body in the canonical text a save keeps."""
    return Revision(
        draft_id=str(row.draft_id),
        number=row.number,
        body=canonical_value(row.body),
        saved_by=row.saved_by,
        saved_at=row.saved_at,
    )


def act_of(row: ManifestActRow) -> Act:
    return Act(
        revision=row.revision,
        act=DraftAct(row.act),
        actor_id=row.actor_id,
        at=row.at,
        widened=row.widened,
        for_department=row.for_department,
    )


def draft_of(
    row: ManifestDraftRow,
    revisions: Iterable[ManifestRevisionRow],
    acts: Iterable[ManifestActRow],
) -> AgentDraft:
    return AgentDraft(
        draft=ManifestDraft(draft_id=str(row.id), owner_id=row.owner_id, created_at=row.created_at),
        agent_id=row.agent_id,
        kind=DraftKind(row.kind),
        base_hash=row.base_hash,
        revisions=tuple(revision_of(one) for one in sorted(revisions, key=lambda r: r.number)),
        acts=tuple(act_of(one) for one in sorted(acts, key=lambda a: (a.revision, a.at))),
    )


def act_values(draft_id: str, act: Act) -> dict[str, Any]:
    return {
        "draft_id": uuid.UUID(draft_id),
        "revision": act.revision,
        "act": act.act.value,
        "actor_id": act.actor_id,
        "widened": act.widened,
        "for_department": act.for_department,
        "at": act.at,
    }


def _as(name: str, value: str) -> Any:
    return text("SELECT set_config(:name, :value, true)").bindparams(name=name, value=value)


async def _acting(session: AsyncSession, by: Attribution) -> None:
    """Tell the triggers who is writing, and the insert policies whose name the rows may carry."""
    for statement in attributed_to(
        actor_id=by.actor_id, ent_hash=by.ent_hash, trace_id=by.trace_id
    ):
        await session.execute(statement)
    await session.execute(_as(PRINCIPAL_SETTING, by.actor_id))


class StoredAgentDrafts:
    """`AgentDraftStore` over `0149`'s tables and the agent's own."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def _drafts(self, rows: Sequence[ManifestDraftRow]) -> tuple[AgentDraft, ...]:
        if not rows:
            return ()
        ids = [one.id for one in rows]
        async with self._sessions() as session:
            revisions = (
                (
                    await session.execute(
                        select(ManifestRevisionRow).where(ManifestRevisionRow.draft_id.in_(ids))
                    )
                )
                .scalars()
                .all()
            )
            acts = (
                (
                    await session.execute(
                        select(ManifestActRow).where(ManifestActRow.draft_id.in_(ids))
                    )
                )
                .scalars()
                .all()
            )
        return tuple(
            draft_of(
                row,
                (one for one in revisions if one.draft_id == row.id),
                (one for one in acts if one.draft_id == row.id),
            )
            for row in rows
        )

    async def draft(self, draft_id: str) -> AgentDraft | None:
        try:
            key = uuid.UUID(draft_id)
        except ValueError:
            return None
        async with self._sessions() as session:
            row = (
                await session.execute(select(ManifestDraftRow).where(ManifestDraftRow.id == key))
            ).scalar_one_or_none()
        if row is None:
            return None
        found = await self._drafts((row,))
        return found[0]

    async def drafts_owned_by(self, owner_id: str) -> tuple[AgentDraft, ...]:
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(ManifestDraftRow)
                        .where(ManifestDraftRow.owner_id == owner_id)
                        .order_by(ManifestDraftRow.created_at.desc())
                        .limit(MAX_DRAFTS)
                    )
                )
                .scalars()
                .all()
            )
        return await self._drafts(rows)

    async def waiting(self) -> tuple[AgentDraft, ...]:
        """Every draft with a request on it; which of them still wait is the domain's to say."""
        async with self._sessions() as session:
            asked = select(ManifestActRow.draft_id).where(
                ManifestActRow.act == DraftAct.REQUESTED.value
            )
            rows = (
                (
                    await session.execute(
                        select(ManifestDraftRow)
                        .where(ManifestDraftRow.id.in_(asked))
                        .order_by(ManifestDraftRow.created_at.desc())
                        .limit(MAX_DRAFTS)
                    )
                )
                .scalars()
                .all()
            )
        return await self._drafts(rows)

    async def agent(self, agent_id: str) -> FoundAgent | None:
        async with self._sessions() as session:
            found = (
                await session.execute(every_agent_with_install().where(AgentRow.id == agent_id))
            ).one_or_none()
        if found is None:
            return None
        agent_row, instance_row, version_row = found
        record = record_of(agent_row)
        if record is None:
            return None
        return FoundAgent(
            record=record,
            install=installed(instance_row, version_row),
            effective_hash=None if instance_row is None else instance_row.effective_hash,
        )

    async def versions_of(self, template_id: str) -> tuple[int, ...]:
        async with self._sessions() as session:
            found = (
                (
                    await session.execute(
                        select(TemplateVersionRow.version).where(
                            TemplateVersionRow.template_id == template_id
                        )
                    )
                )
                .scalars()
                .all()
            )
        return tuple(sorted(found))

    async def start(self, draft: AgentDraft, first: Revision, *, by: Attribution) -> None:
        async with self._sessions() as session, session.begin():
            await _acting(session, by)
            await session.execute(
                insert(ManifestDraftRow).values(
                    id=uuid.UUID(draft.draft_id),
                    agent_id=draft.agent_id,
                    kind=draft.kind.value,
                    owner_id=draft.owner_id,
                    base_hash=draft.base_hash,
                    created_at=draft.draft.created_at,
                )
            )
            await session.execute(insert(ManifestRevisionRow).values(**_revision_values(first)))

    async def append(self, revision: Revision, *, by: Attribution) -> bool:
        """Append a revision, or False when its number is taken: somebody saved first."""
        async with self._sessions() as session, session.begin():
            await _acting(session, by)
            written = (
                await session.execute(
                    insert(ManifestRevisionRow)
                    .values(**_revision_values(revision))
                    .on_conflict_do_nothing()
                    .returning(ManifestRevisionRow.number)
                )
            ).scalar_one_or_none()
        return written is not None

    async def record(self, draft_id: str, act: Act, *, by: Attribution) -> bool:
        """Record one act, or False when that revision already carries it."""
        async with self._sessions() as session, session.begin():
            await _acting(session, by)
            written = (
                await session.execute(
                    insert(ManifestActRow)
                    .values(**act_values(draft_id, act))
                    .on_conflict_do_nothing()
                    .returning(ManifestActRow.act)
                )
            ).scalar_one_or_none()
        return written is not None

    async def publish_new(
        self,
        draft_id: str,
        acts: Sequence[Act],
        signed: SignedManifest,
        installation: Installation,
        *,
        by: Attribution,
    ) -> bool:
        """The version, the instance, the agent and the acts, or nothing and False."""
        try:
            async with self._sessions() as session, session.begin():
                await _acting(session, by)
                await session.execute(insert(TemplateVersionRow).values(**version_values(signed)))
                pinned = (
                    await session.execute(
                        insert(TemplateInstanceRow)
                        .values(**instance_values(installation))
                        .on_conflict_do_nothing(index_elements=[TemplateInstanceRow.id])
                        .returning(TemplateInstanceRow.id)
                    )
                ).scalar_one_or_none()
                if pinned is None:
                    raise _MovedError
                await session.execute(insert(AgentRow).values(**agent_values(installation.record)))
                for act in acts:
                    await session.execute(
                        insert(ManifestActRow).values(**act_values(draft_id, act))
                    )
        except _MovedError:
            return False
        return True

    async def publish_edit(
        self,
        draft_id: str,
        acts: Sequence[Act],
        signed: SignedManifest,
        installation: Installation,
        *,
        base_hash: str,
        disabled_at: datetime | None,
        by: Attribution,
    ) -> bool:
        """The next version, the instance re-pinned and the agent rewritten; or nothing, False."""
        record = installation.record
        effective = installation.effective
        identity = signed.manifest.identity
        try:
            async with self._sessions() as session, session.begin():
                await _acting(session, by)
                await session.execute(insert(TemplateVersionRow).values(**version_values(signed)))
                pinned = (
                    await session.execute(
                        update(TemplateInstanceRow)
                        .where(
                            TemplateInstanceRow.id == record.agent_id,
                            TemplateInstanceRow.effective_hash == base_hash,
                        )
                        .values(
                            template_id=identity.template_id,
                            template_version=identity.version,
                            content_digest=signed.content_digest,
                            overlay={},
                            field_owners={},
                            effective_document=dict(effective.document),
                            effective_hash=effective.config_hash,
                        )
                        .returning(TemplateInstanceRow.id)
                    )
                ).scalar_one_or_none()
                if pinned is None:
                    raise _MovedError
                written = (
                    await session.execute(
                        update(AgentRow)
                        .where(AgentRow.id == record.agent_id, AgentRow.archived_at.is_(None))
                        .values(**_configuration(record), disabled_at=disabled_at)
                        .returning(AgentRow.id)
                    )
                ).scalar_one_or_none()
                if written is None:
                    raise _MovedError
                for act in acts:
                    await session.execute(
                        insert(ManifestActRow).values(**act_values(draft_id, act))
                    )
        except _MovedError:
            return False
        return True

    async def department_of(self, principal_id: str) -> str | None:
        """The primary department of somebody here and active, or None."""
        found = await StoredPrincipals(self._sessions).live_principal(principal_id)
        return None if found is None else (found.primary_department or None)

    async def newest_published(self, template_id: str) -> TemplateManifest | None:
        """The newest version of a template this install published, or None."""
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(TemplateVersionRow)
                    .where(TemplateVersionRow.template_id == template_id)
                    .order_by(TemplateVersionRow.version.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        if row is None:
            return None
        try:
            return signed_of(row).manifest
        except (KeyError, ValueError, TemplateError):
            return None


def _revision_values(revision: Revision) -> dict[str, Any]:
    return {
        "draft_id": uuid.UUID(revision.draft_id),
        "number": revision.number,
        "body": revision.document(),
        "saved_by": revision.saved_by,
        "saved_at": revision.saved_at,
    }


#: The agent columns a manifest decides. Everything else on the row is the agent's own.
CONFIGURATION_COLUMNS: Final[tuple[str, ...]] = (
    "display_name",
    "persona",
    "tier",
    "scope",
    "capabilities",
    "allowed_tools",
    "required_tools",
    "max_side_effect",
    "connectors",
)


def _configuration(record: AgentRecord) -> dict[str, Any]:
    """The configuration columns of an agent row, as `agent_values` writes them."""
    values = agent_values(record)
    return {name: values[name] for name in CONFIGURATION_COLUMNS}
