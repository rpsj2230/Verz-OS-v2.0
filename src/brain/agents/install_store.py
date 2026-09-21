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

**What calls this, said plainly.** No route. The flow's inputs are a signing key, a draft carried
across the wizard's steps, the audience the installer chooses and this process's registries, and no
setting holds an install's template signing key and no screen carries a draft. Installing is the
console's next surface, and this is the call it will make; until then the tests drive it with a key
of their own.

Task ids: M13.3.6, M13.3.7, M38.2.2.4
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agents.install import Installation, InstallDraft, complete
from brain.agents.model import AgentAudience, AgentRecord
from brain.agents.template import SignedManifest, TemplateError
from brain.connectors.registry import ConnectorRegistry
from brain.tables.agent import AgentRow
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
        "created_by": record.created_by,
        "disabled_at": record.disabled_at,
        "archived_at": record.archived_at,
    }


def same_version(found: Mapping[str, Any], signed: SignedManifest) -> bool:
    """Whether a version row on file is this signed body."""
    return (found["content_digest"], found["signature"]) == (
        signed.content_digest,
        signed.signature,
    )


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
    ) -> Finished:
        """Complete the draft and write the version, the instance and the agent, or nothing.

        `complete` runs first and outside the transaction, so a draft whose signature does not
        verify, whose overlay touches a sealed path or whose persona is blank is refused by the
        domain before a connection is opened.
        """
        installation = complete(
            draft, key=key, audience=audience, registry=registry, tools=tools, at=at
        )
        signed = draft.offer.signed
        async with self._sessions() as session, session.begin():
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
