"""Finishing an agent install: `brain.agents.install.complete`, and the three rows it becomes.

`brain.agents.install` is the wizard: `begin` opens a draft from an offer, `answer` and `provide`
fill it in, and `complete` settles it against this install's connectors and tools into an
`Installation`. Nothing in `src` called `complete`, so no running installation could turn a template
into an agent, and the wave-three milestone said so. This is the end of that flow: `finish` calls
`complete` and writes what it returns.

**Three rows in one transaction, or none.** The signed template version, the instance that pins it,
and the agent the instance materialises into. `brain.agent_routes.install_for` joins the first two
on the pin and `record_of` reads the third, so an agent written without its instance would answer
with no lineage, and an instance written without its version would be a pin to nothing. See
`AN_AGENT_IS_WRITTEN_WITH_WHAT_IT_WAS_INSTALLED_FROM`.

**The agent row is `Installation.record`, never `effective.record`.** `install.settle` binds the
template's declared tools to this install's registered ones and disables the record when anything is
missing, and that is the record to store and to select on, for the reason `Installation` gives.

**A version already on file must be the same signed body.** The version table is insert-only and a
template id and version name one body for ever, so a second install of the same version writes no
version row, and one whose digest or signature differs from the row on file is refused before
anything is written: it is a republish or a forgery under a number somebody already installed. See
`A_VERSION_NUMBER_NAMES_ONE_SIGNED_BODY`.

**A second finish of the same instance writes nothing and says which agent is already there.** The
instance id is the agent's id, the insert does nothing on a conflict, and the agent row is written
only when the instance row was, so two presses of one Finish race to one agent.

**Every agent this writes starts disabled, whatever its badge says.** `complete` disables an install
with something missing and leaves a finished one selectable, which is right for the domain's
question, whether the install is complete. It is the wrong answer to whether anybody decided the
agent should answer yet: an agent installed from the console would be live in every picker its
audience covers on the press of Install, before anybody read what it was assembled from. So the row
is written through `brain.agents.lifecycle.disable`, and enabling it is a person's second act, which
the ledger records separately. See `AN_INSTALLED_AGENT_IS_WRITTEN_DISABLED`.

**And at Shadow on every target, or not at all.** The leash is the sealed path `guardrails.leash`,
an install cannot overlay it, and nothing stores a per-agent rung yet (the lowering row is W3.8), so
the only way an installed agent can start at Shadow everywhere is for the version it pins to say so.
A version whose leash names any rung above Shadow is refused before a connection is opened, with the
targets named. Every template this product ships says Shadow on every target
(`brain.agents.catalogue.EVERY_AGENT_STARTS_SUPERVISED`), so the refusal reaches only a version
somebody published with a raised rung, which is the version that should not hand a new agent
autonomy it has not earned. See `AN_INSTALL_STARTS_AT_SHADOW_ON_EVERY_TARGET`.

**Who installed it reaches the ledger with the request.** `0137`'s trigger records the agent's
insert as `created` with the row's own `created_by`, and the transaction is told the reach digest
and the trace first, through `brain.tables.audit.attributed_to`, so the entry names the request and
not the transaction.

**What calls this, said plainly.** `brain.agent_lifecycle_routes`, for an install of a published
version and for a duplicate, which is an install of the same version with another agent's overlay.
Both need this install's template signing key, which the application reads at start from its
write-once vault slot (`brain.ops.template_key`); a process holding none says so, and the tests
drive it with a key of their own.

Task ids: M13.3.6, M13.3.7, M38.2.2.4, M27.11.6, M27.11.7, M13.7.4
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agents.install import Installation, InstallDraft, complete
from brain.agents.lifecycle import disable
from brain.agents.model import AgentAudience, AgentRecord, answering_on
from brain.agents.template import SignedManifest, TemplateError
from brain.connectors.registry import ConnectorRegistry
from brain.gate.injection import AutonomyTier
from brain.tables.agent import AgentRow
from brain.tables.audit import attributed_to
from brain.tables.template import TemplateInstanceRow, TemplateVersionRow
from brain.tools.registry import ToolRegistry

#: Why the three rows are one transaction.
AN_AGENT_IS_WRITTEN_WITH_WHAT_IT_WAS_INSTALLED_FROM: Final = (
    "An agent, the instance that pins its template and the signed version it pins are written "
    "together. An agent without its instance answers with no lineage and no composition, and an "
    "instance without its version is a pin to nothing, so either half alone is an install the "
    "console cannot explain."
)

#: Why a version on file is compared rather than overwritten.
A_VERSION_NUMBER_NAMES_ONE_SIGNED_BODY: Final = (
    "A template id and a version name one signed body, for ever: the version table is insert-only "
    "and every instance pins the digest. A second install of the same version writes no version "
    "row, and one carrying a different digest or signature under that number is refused before "
    "anything is written, because it is a republish or a forgery of something already installed."
)


#: Why an installed agent is written switched off.
AN_INSTALLED_AGENT_IS_WRITTEN_DISABLED: Final = (
    "Installing decides that an agent exists; it does not decide that the agent should answer. A "
    "finished install written selectable is live in every picker its audience covers on the press "
    "of Install, before anybody has read what it is assembled from, so every install is written "
    "disabled and enabling it is a second act by a person, recorded as its own entry."
)

#: Why a version whose leash starts above Shadow is refused rather than installed.
AN_INSTALL_STARTS_AT_SHADOW_ON_EVERY_TARGET: Final = (
    "A new agent has no runs, so it has no evidence for any rung above Shadow. The leash is a "
    "sealed path an install cannot overlay and no per-agent rung is stored yet, so a version whose "
    "leash names a higher rung would hand every agent installed from it autonomy that was earned, "
    "if at all, by another agent. Such a version is refused, naming the targets, and nothing is "
    "written."
)

#: The rung every target of an installed agent starts on.
INSTALLED_RUNG: Final = AutonomyTier.SHADOW


class InstallStoreError(TemplateError):
    """An install could not be written as the draft described it."""


@dataclass(frozen=True)
class Finished:
    """What finishing an install did: the installation `complete` produced, and whether this wrote
    it.

    `created` is False when the instance was already on file; nothing was written then, and the
    installation is what this draft would have produced, not a reading of the stored agent.
    """

    installation: Installation
    created: bool


def version_values(signed: SignedManifest) -> dict[str, Any]:
    """The template version row: the signed body as the flat document `manifest_of` reads back."""
    identity = signed.manifest.identity
    return {
        "template_id": identity.template_id,
        "version": identity.version,
        "content_digest": signed.content_digest,
        "signature": signed.signature,
        "signed_by": signed.signed_by,
        "signed_at": signed.signed_at,
        "document": dict(signed.manifest.document()),
    }


def instance_values(installation: Installation) -> dict[str, Any]:
    """The instance row: the pin, the overlay with its owners, and the effective document cached."""
    instance = installation.instance
    return {
        "id": instance.instance_id,
        "template_id": instance.template_id,
        "template_version": instance.template_version,
        "content_digest": instance.content_digest,
        "overlay": dict(instance.overlay),
        "field_owners": {
            path: owner.model_dump(mode="json") for path, owner in instance.overlay_owners.items()
        },
        "effective_document": dict(installation.effective.document),
        "effective_hash": installation.effective.config_hash,
        "created_by": instance.created_by,
    }


def agent_values(record: AgentRecord) -> dict[str, Any]:
    """The agent row, as `brain.agent_routes.record_of` reads one back."""
    return {
        "id": record.agent_id,
        "display_name": record.display_name,
        "persona": record.persona,
        "tier": record.tier.value,
        "model_pin_provider": None if record.model_pin is None else record.model_pin.provider,
        "model_pin_model": None if record.model_pin is None else record.model_pin.model,
        "visibility": record.audience.level.value,
        "owner_id": record.audience.owner_id,
        "department": record.audience.department or None,
        "scope": record.authority.scope.model_dump(mode="json"),
        "capabilities": [one.value for one in record.authority.capabilities],
        "allowed_tools": sorted(record.authority.allowed_tools),
        "required_tools": sorted(record.authority.required_tools),
        "max_side_effect": record.authority.max_side_effect.value,
        "connectors": list(record.authority.connectors),
        "created_by": record.created_by,
        "disabled_at": record.disabled_at,
        "archived_at": record.archived_at,
        "channels": list(record.channels),
        "max_turns": record.max_turns,
        "max_tool_calls": record.max_tool_calls,
    }


def rungs_above_the_start(signed: SignedManifest) -> tuple[str, ...]:
    """The targets whose sealed rung is above `INSTALLED_RUNG`, sorted, or nothing.

    Read off the signed manifest rather than off `Installation.leash`, because the manifest's leash
    is what the instance pins and what every later materialisation reads; the installation's is
    pinned to Shadow only while a connector is missing, which is a fact about today that nothing
    stores. See `AN_INSTALL_STARTS_AT_SHADOW_ON_EVERY_TARGET`.
    """
    leash = signed.manifest.guardrails.leash
    return tuple(sorted({one.target for one in leash if one.rung > INSTALLED_RUNG}))


def same_version(found: Mapping[str, Any], signed: SignedManifest) -> bool:
    """Whether a version row on file is this signed body."""
    return (found["content_digest"], found["signature"]) == (
        signed.content_digest,
        signed.signature,
    )


def prepared(
    draft: InstallDraft,
    *,
    key: str,
    audience: AgentAudience,
    registry: ConnectorRegistry,
    tools: ToolRegistry,
    at: datetime,
    channels: Iterable[str] = (),
) -> Installation:
    """The installation `StoredAgentInstalls.finish` writes, decided before any connection.

    `channels` are the ones the person installing ticked (M13.7.4), set on the record here and in
    no other place, so the template install, the builder's publish and a duplicate all enable a
    new agent the same way. They are the agent's own, like the audience, and never the template's:
    a manifest naming channels would change every signed template's digest. Empty, the default,
    answers nowhere, per `brain.agents.model.AN_AGENT_ANSWERS_ONLY_ON_THE_CHANNELS_ENABLED_FOR_IT`.

    A version whose leash starts above Shadow is refused first, per
    `AN_INSTALL_STARTS_AT_SHADOW_ON_EVERY_TARGET`. Then `complete` runs, so a draft whose signature
    does not verify, whose overlay touches a sealed path or whose persona is blank is refused by
    the domain. The record handed back is disabled, per `AN_INSTALLED_AGENT_IS_WRITTEN_DISABLED`,
    and it is the record written, so what a caller reads is what was stored.

    A function of its own rather than the first half of `finish`, so a caller holding no database,
    a route test among them, is handed the installation the store would write rather than a copy
    of these three steps that agrees with them today.
    """
    signed = draft.offer.signed
    raised = rungs_above_the_start(signed)
    if raised:
        msg = (
            f"version {signed.manifest.identity.version} of "
            f"{signed.manifest.identity.template_id!r} starts {list(raised)} above Shadow, "
            f"and nothing was installed. {AN_INSTALL_STARTS_AT_SHADOW_ON_EVERY_TARGET}"
        )
        raise InstallStoreError(msg)
    completed = complete(draft, key=key, audience=audience, registry=registry, tools=tools, at=at)
    enabled = answering_on(completed.record, channels)
    return replace(completed, record=disable(enabled, now=at))


class StoredAgentInstalls:
    """The end of the install flow over this install's database."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def finish(
        self,
        draft: InstallDraft,
        *,
        key: str,
        audience: AgentAudience,
        registry: ConnectorRegistry,
        tools: ToolRegistry,
        at: datetime,
        ent_hash: str,
        trace_id: str,
        channels: Iterable[str] = (),
    ) -> Finished:
        """Write the version, the instance and the agent `prepared` decides, or nothing.

        `prepared` runs first and outside the transaction, so every refusal it makes is made before
        a connection is opened. `ent_hash` and `trace_id` are the request's, for `0137`'s trigger;
        neither has a default, so a caller that has no request has to say so.
        """
        signed = draft.offer.signed
        installation = prepared(
            draft,
            key=key,
            audience=audience,
            registry=registry,
            tools=tools,
            at=at,
            channels=channels,
        )
        async with self._sessions() as session, session.begin():
            for statement in attributed_to(
                actor_id=draft.installer, ent_hash=ent_hash, trace_id=trace_id
            ):
                await session.execute(statement)
            on_file = (
                (
                    await session.execute(
                        select(
                            TemplateVersionRow.content_digest, TemplateVersionRow.signature
                        ).where(
                            TemplateVersionRow.template_id == signed.manifest.identity.template_id,
                            TemplateVersionRow.version == signed.manifest.identity.version,
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
            if on_file is None:
                await session.execute(insert(TemplateVersionRow).values(**version_values(signed)))
            elif not same_version(dict(on_file), signed):
                msg = (
                    f"{signed.manifest.identity.template_id!r} version "
                    f"{signed.manifest.identity.version} is on file with another body. "
                    f"{A_VERSION_NUMBER_NAMES_ONE_SIGNED_BODY}"
                )
                raise InstallStoreError(msg)
            written = (
                await session.execute(
                    insert(TemplateInstanceRow)
                    .values(**instance_values(installation))
                    .on_conflict_do_nothing(index_elements=[TemplateInstanceRow.id])
                    .returning(TemplateInstanceRow.id)
                )
            ).scalar_one_or_none()
            if written is None:
                return Finished(installation=installation, created=False)
            await session.execute(insert(AgentRow).values(**agent_values(installation.record)))
        return Finished(installation=installation, created=True)
