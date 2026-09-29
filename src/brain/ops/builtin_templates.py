"""The templates this product ships, signed with the install's own key when it is furnished.

`brain.agents.catalogue` holds the built-in templates as manifests in code, and until this module
none of them could become an agent: `brain.agents.template.install` verifies a version's signature
with the install's key before anything is pinned to it, the built-in manifests carried none, and
`brain.ops.starter_store.NO_TEMPLATE_IS_SIGNED_BEFORE_THE_INSTALL_HOLDS_A_KEY_OF_ITS_OWN` said so on
the Settings screen. `brain.ops.template_key` gave every install a key of its own on 2026-09-29,
minted once into a write-once vault slot and held by the application at start. This is the other
half of M13.8.10: each start that holds the key puts every built-in template on file as a version
signed with it, so the gallery offers them to install and `install` verifies them like any other.

**Signed as the product, by the key the install already holds, and by nobody else.** The signer
is `brain.agents.template.SYSTEM_PUBLISHER`, the id the blank template is published under, because
nobody at this install authored these documents and a person's id on them would put a name against
a decision nobody made. The key is the one the application read from its slot, never one minted
here: a second key would make a version this install cannot verify, and a key kept anywhere else
is `brain.ops.template_key.THE_TEMPLATE_KEY_NEVER_LEAVES_THE_VAULT_BUT_INTO_THIS_PROCESS` broken.
A process that holds no key signs nothing and says why; see `NO_KEY_SIGNS_NOTHING`.

**What is on file is never replaced, and a start after the first writes nothing.** A version is
`(template_id, version)` and a pinned agent materialises against that row, so each insert is
`ON CONFLICT DO NOTHING` on the key and a version already on file stays exactly as it is, whatever
this release ships under the same number. That is
`brain.agents.install_store.A_VERSION_NUMBER_NAMES_ONE_SIGNED_BODY` applied to the product's own
versions: a release that changes a built-in template raises its version, and the next start puts
the new version beside the old. Several application processes start together, and the conflict
clause is what makes that safe without a lock: the first insert wins and the rest write nothing,
which is `brain.ops.starter_store`'s measured argument against the lock it took out.

**Each version written reaches the ledger as a publish by first run.** `0104`'s trigger on
`agent.template_version` appends `publish` for every row inserted and none for a conflict, and the
writer is attributed as `brain.firstrun.GRANTED_BY` under the start's reconciliation trace, the
actor `brain.ops.starter_store.furnish` writes as, because signing the shipped templates is what
first run would have done had the key existed then.

**Still the product's in the gallery.** A version on file whose content is exactly the manifest
this release ships under that id and number is the built-in one, signed here; `is_built_in` is the
test, and the gallery labels it built in rather than published, so "what the product offers" and
"what we have made" stay apart as `brain.agent_routes.Origin` requires. Matched on the content
digest rather than on the signer, because a signer is a column and a digest is the document.

Rejected: signing in the installer's furnish step alone. An install set up before this module
would never get its templates, and the application already holds the key at every start, which is
`brain.ops.starter_store.EVERY_START_FURNISHES_BECAUSE_NOTHING_FURNISHED_IS_AN_ANSWER`'s argument.
Rejected: installing the standard agents as well. An agent is a template somebody chose to run with
an audience, a steward and connectors, and an install that ran twenty-three of them unasked would
be choosing for the company; the templates are offered and nothing is installed.

Task ids: M13.8.10
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Final

import structlog
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from brain.agents.catalogue import CATALOGUE
from brain.agents.template import (
    SYSTEM_PUBLISHER,
    SignedManifest,
    TemplateManifest,
    content_digest,
    publish,
)
from brain.tables.audit import attributed_to
from brain.tables.template import TemplateVersionRow

log = structlog.get_logger(__name__)

# ------------------------------------------------------------------ written-down reasons
#: Why the shipped templates are signed at start and by the product.
THE_PRODUCT_SIGNS_WHAT_IT_SHIPS_WITH_THE_INSTALL_S_OWN_KEY: Final = (
    "Every start that holds the install's template signing key puts each built-in template on "
    "file as a version signed with that key under the product's own name, so the gallery can "
    "offer it and an install verifies it like any other. Nothing already on file is replaced, "
    "nothing is installed, and a process with no key signs nothing."
)

#: Said by a process that holds no key.
NO_KEY_SIGNS_NOTHING: Final = (
    "this process holds no template signing key, so no built-in template was signed: an install "
    "with no vault has nowhere a write-once key can live, and one whose vault had not answered "
    "signs them at its next start"
)


# --------------------------------------------------------------------------- the pure half
def signed_built_ins(
    key: str, at: datetime, catalogue: Sequence[TemplateManifest] = CATALOGUE
) -> tuple[SignedManifest, ...]:
    """Every shipped template, signed with `key` under the product's name at `at`."""
    return tuple(publish(one, key=key, signed_by=SYSTEM_PUBLISHER, at=at) for one in catalogue)


def is_built_in(
    manifest: TemplateManifest, catalogue: Sequence[TemplateManifest] = CATALOGUE
) -> bool:
    """Whether this manifest is exactly the built-in template of its id and version.

    The content digest of both, so a template somebody published under a built-in's id, or a
    later version of it, is theirs and not the product's.
    """
    identity = manifest.identity
    return any(
        one.identity.template_id == identity.template_id
        and one.identity.version == identity.version
        and content_digest(one) == content_digest(manifest)
        for one in catalogue
    )


# ------------------------------------------------------------------------- the writing half
async def sign_built_ins(
    sessions: async_sessionmaker[AsyncSession],
    *,
    key: str | None,
    at: datetime,
    actor: str,
    trace_id: str,
    catalogue: Sequence[TemplateManifest] = CATALOGUE,
) -> tuple[str, ...]:
    """Put every built-in template on file signed with `key`; the ids written now, sorted.

    One transaction as the application role, attributed to `actor` under `trace_id`. A version
    already on file is left as it is, so a start after the first returns nothing. Raises for a
    database that refuses; the caller decides what that costs.
    """
    if not key:
        log.info("built-in templates not signed", why=NO_KEY_SIGNS_NOTHING)
        return ()
    from brain.agents.install_store import version_values

    written: list[str] = []
    async with sessions() as session, session.begin():
        for statement in attributed_to(actor_id=actor, ent_hash="", trace_id=trace_id):
            await session.execute(statement)
        for signed in signed_built_ins(key, at, catalogue):
            inserted = (
                await session.execute(
                    insert(TemplateVersionRow)
                    .values(**version_values(signed))
                    .on_conflict_do_nothing(
                        index_elements=[TemplateVersionRow.template_id, TemplateVersionRow.version]
                    )
                    .returning(TemplateVersionRow.template_id)
                )
            ).scalar_one_or_none()
            if inserted is not None:
                written.append(str(inserted))
    return tuple(sorted(written))
