"""One agent's publish history, read from the versions it was published as and the acts that did it.

`brain.builder.publish.publication_history` is the record of every publish, computed from the
stored versions rather than kept beside them (`THE_PUBLISH_RECORD_IS_READ_FROM_THE_VERSIONS`).
This is where those versions and the approvals behind them are read.

**A version is matched to the draft that published it by the instant both were written.** The
builder's publish signs the version and records the draft's `published` act in one request, at
that request's instant, whether it went out on its author's word or on an approver's. So the
approvers of a version are the people who recorded an `approved` act on the draft whose
`published` act carries the version's signing instant. Rejected: matching on the draft's
revision number, which numbers revisions of a draft and not versions of an agent, so two drafts
of one agent share revision 2.

**Read as the application role, under the tables' own policies.** `agent.template_version` and
the draft tables admit the application role to read, and the route that serves this has already
decided the reader may see the agent.

**The permission canaries' last word is read here too** (M20.4.1). `canary_run` is a scheduled
control and every attempt of it is a row of `ops.control_run`, so whether the install's permission
canaries are red is that control's newest finished run, and no second record of it is kept. An
install that has never finished a run is not red: a publish gate that refuses everything until a
scheduled control has fired once would stop the builder on the first day, and an absence of
evidence is not a failure. See `A_RED_CANARY_RUN_STOPS_A_PUBLISH_AND_NO_RUN_DOES_NOT`.

Task ids: M20.4.6, M20.4.1
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.builder.draft_words import DraftAct
from brain.builder.publish import PublishedVersion, PublishRecord, publication_history
from brain.tables.manifest_draft import ManifestActRow, ManifestDraftRow
from brain.tables.schedule import ControlRunRow
from brain.tables.template import TemplateVersionRow

#: The control whose runs say whether the permission canaries pass.
CANARY_CONTROL: Final = "canary_run"

#: Why a red run stops a publish and a missing one does not.
A_RED_CANARY_RUN_STOPS_A_PUBLISH_AND_NO_RUN_DOES_NOT: Final = (
    "A publish puts a ceiling into the world, and the permission canaries are the only check that "
    "the gate still refuses what it refused yesterday, so while the newest finished run of them is "
    "red nothing is published. An install that has not yet finished a run has no evidence either "
    "way and is not stopped, because a gate that refuses everything until a schedule has fired "
    "would stop every builder on the first day."
)


async def canaries_are_red(sessions: async_sessionmaker[AsyncSession]) -> bool:
    """Whether the newest finished run of the permission canaries failed."""
    async with sessions() as session:
        newest = (
            await session.execute(
                select(ControlRunRow.outcome)
                .where(ControlRunRow.name == CANARY_CONTROL, ControlRunRow.outcome.is_not(None))
                .order_by(ControlRunRow.started_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    return newest == "failed"


class StoredPublications:
    """The publish history of one agent over its version and draft tables."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def history(self, agent_id: str) -> tuple[PublishRecord, ...]:
        async with self._sessions() as session:
            versions = (
                await session.execute(
                    select(
                        TemplateVersionRow.version,
                        TemplateVersionRow.signed_by,
                        TemplateVersionRow.signed_at,
                        TemplateVersionRow.document,
                    ).where(TemplateVersionRow.template_id == agent_id)
                )
            ).all()
            acts = (
                await session.execute(
                    select(
                        ManifestActRow.draft_id,
                        ManifestActRow.act,
                        ManifestActRow.actor_id,
                        ManifestActRow.at,
                    )
                    .join(ManifestDraftRow, ManifestDraftRow.id == ManifestActRow.draft_id)
                    .where(ManifestDraftRow.agent_id == agent_id)
                )
            ).all()
        published_at: dict[object, datetime] = {}
        approved_by: dict[object, list[str]] = defaultdict(list)
        for draft_id, act, actor_id, at in acts:
            if act == DraftAct.PUBLISHED.value:
                published_at[draft_id] = at
            elif act == DraftAct.APPROVED.value:
                approved_by[draft_id].append(str(actor_id))
        by_instant = {at: sorted(approved_by[draft_id]) for draft_id, at in published_at.items()}
        kept = [
            PublishedVersion(
                version=int(version),
                published_by=str(signed_by),
                published_at=signed_at,
                document=dict(document),
            )
            for version, signed_by, signed_at, document in versions
        ]
        approvers = {one.version: by_instant.get(one.published_at, []) for one in kept}
        return publication_history(agent_id, kept, approvers)
