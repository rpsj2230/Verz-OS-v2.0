"""The install acceptance checks for the built-in agent templates: on file as shipped, installable.

`brain.agents.catalogue` is the catalogue this release ships, and `brain.ops.builtin_templates`
signs it onto the install at start with the install's own key, from the vault. Each of those
templates is a leaf of its own (M13.5.x), and what each leaf asks is that the template exists on
the install: there, as written, and something a person can make an agent from.

**What is on file is compared with what this release ships, by content digest.** The digest is
`brain.agents.template.content_digest`, the value a signature is taken over, so a stored version
whose persona, ceiling or leash differs from the catalogue's differs here whatever its signature
says. Rejected: verifying the stored signatures, which needs the install's signing key, and the
worker that runs these checks is deliberately given none (`ops/openbao/credential-slots.md`: the
worker neither signs nor verifies). See `THE_WORKER_HOLDS_NO_SIGNING_KEY`.

**Installing is asked of the template install route, as a reserved administrator of
acceptance_a, over a copy of each shipped manifest signed with a key made for the check.** The
copy is the shipped manifest with a template id of the check's own, so the route verifies a
signature it can verify, installs through `StoredAgentInstalls` exactly as the gallery's button
does, and what it makes is an agent of acceptance_a that is disabled and supervised at Shadow on
every target, with the ceiling the template declares. Everything is written inside the check's
transaction and rolled back.

**A template the work breakdown states a constraint for is held to it.** The accountant and SEM
agents are Shadow-pinned (M13.5.19, M13.5.21): installed at Shadow like every template, and the
installed agent's leash cannot be changed afterwards, because the database refuses an overlay
that names it. The SEM agent's "a human commits budget changes" is its ceiling of drafting and
never writing, which the installed agent must carry.

**What a version is, and what an install keeps of it, is the second check (M13.2.1, M13.2.3,
M13.2.6, M13.4.1).** A version signed by another key is refused by the gallery's own route; a
stored version cannot be changed by the application and a second version stands beside the
first; the agent installed from the first names that version and its digest, and publishing the
second changes nothing about it; and the database refuses each of the five sealed paths in an
installed agent's overlay while accepting a settable one, so the seal is not a refusal of
everything. Rejected: proving the seal on `brain.agents.template` alone, which is the rule written
twice; the install's own constraint is the one an overlay meets.

**No key and nothing on file is not run, and a key with nothing on file is a failure.** An
install without a vault cannot sign its catalogue and says so on the gallery (M13.8.18); an
install with a vault that holds no built-in template has a start that did not do its job.

Task ids: M13.5.1, M13.5.2, M13.5.3, M13.5.4, M13.5.5, M13.5.6, M13.5.7, M13.5.8, M13.5.9
Task ids: M13.5.10, M13.5.11, M13.5.12, M13.5.13, M13.5.14, M13.5.15, M13.5.16, M13.5.17
Task ids: M13.5.19, M13.5.20, M13.5.21, M13.5.22, M13.5.23, M13.2.1, M13.2.3, M13.2.6, M13.4.1
"""

from __future__ import annotations

import secrets
from collections.abc import Sequence
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Final, cast

from sqlalchemy import insert, select

from brain.core.scope import Scope
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI

    from brain.agents.template import SignedManifest, TemplateManifest

A, _ = RESERVED_DEPARTMENTS

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 400

#: Why the stored signatures are not verified here.
THE_WORKER_HOLDS_NO_SIGNING_KEY: Final = (
    "The template signing key is read by the application and nobody else: the worker that runs "
    "these checks neither signs nor verifies, by the vault's own policy. So what is on file is "
    "compared with what this release ships by the digest a signature is taken over, which a "
    "changed persona, ceiling or leash moves, and installing is proved over a copy signed with a "
    "key made for the check."
)

#: The templates whose leaf is not proved here, and why. M13.5.18 asks for a thirty-day pin
#: review, which is not an install; it is installed with the rest and claims nothing.
NOT_CLAIMED: Final[frozenset[str]] = frozenset({"ar_and_renewal_chaser"})

#: The Shadow-pinned templates and the SEM agent, whose constraint is its ceiling.
SHADOW_PINNED: Final[frozenset[str]] = frozenset({"accountant_agent", "sem_agent"})
DRAFTS_AND_NEVER_WRITES: Final = "sem_agent"

NOTHING_ON_FILE_WITH_A_VAULT: Final = (
    "this install keeps a vault and holds no built-in template, so its start signed nothing"
)
NOTHING_ON_FILE_AND_NO_VAULT: Final = (
    "this install has no vault, so it holds no signing key and no built-in template; the gallery "
    "says installing is unavailable"
)
NOT_AS_SHIPPED: Final = "a built-in template on file is not the one this release ships"
MISSING: Final = "a built-in template this release ships is not on file"
NOT_INSTALLED: Final = "a built-in template could not be installed from the gallery"
NOT_AT_SHADOW: Final = "an installed template agent was not disabled at Shadow on every target"
NOT_ITS_CEILING: Final = (
    "an installed template agent does not carry the ceiling its template declares"
)
NOT_IN_ITS_DEPARTMENT: Final = (
    "an installed template agent was not made for its installer's department"
)
SEM_WRITES: Final = "the SEM agent was installed able to commit a change rather than draft one"
NOT_PINNED_AT_SHADOW: Final = (
    "a Shadow-pinned template agent's leash could be changed after install"
)

#: The sealed path a pin rests on: an overlay may never set the leash.
LEASH_PATH: Final = "guardrails.leash"


async def _administrator(h: Harness) -> str:
    """A reserved principal of acceptance_a holding the gallery's read and the install authority
    over acceptance_a, which is what the gallery's install button asks of its reader."""
    from brain.agent_routes import TEMPLATE_SCREEN
    from brain.agents.creation import AGENT_INSTALL_CAPABILITY
    from brain.console.reads import plane_capability_for
    from brain.console.screens import screen

    read = screen(TEMPLATE_SCREEN).read
    made = h.principal(A, "templates")
    await h.person(
        made,
        department=A,
        grants=(
            (read.requires.value, Scope.unrestricted()),
            (plane_capability_for(read, read.plane).value, Scope.unrestricted()),
            (AGENT_INSTALL_CAPABILITY.value, Scope.department(A)),
        ),
    )
    return made


def _request(app: FastAPI) -> Any:
    from starlette.requests import Request

    return Request({"type": "http", "app": app, "headers": [], "method": "POST"})


async def _asking(h: Harness, principal_id: str) -> Any:
    """What the routes read of a signed-in person: the principal, the reach, the instant."""
    from brain.gate.admission import Assurance, admit
    from brain.gate.context import Channel
    from brain.identity.principal_store import StoredPrincipals

    person = await StoredPrincipals(h.sessions).live_principal(principal_id)
    if person is None:
        raise CheckFailedError("a reserved person was not live in the directory")
    reach = admit(await h.reach(principal_id), Channel.CONSOLE, Assurance.STRONG)
    # A cast at the routes' boundary, as `brain.ops.acceptance_threads` makes it: they read these
    # three, and a `Caller` is minted only from a verified token.
    return cast(
        Any,
        SimpleNamespace(
            caller=SimpleNamespace(principal=person), reach=reach, now=datetime.now(UTC)
        ),
    )


def _gallery(h: Harness, key: str) -> FastAPI:
    """What the template routes read: the check's transaction, its own key and the registry."""
    from fastapi import FastAPI

    from brain.knowledge.row_store import SessionRowSource
    from brain.tools.startup import build_registry

    app = FastAPI()
    app.state.db_sessions = h.sessions
    app.state.template_key = key
    app.state.tools = build_registry(
        source=h.settings.tool_source, records=SessionRowSource(h.sessions)
    )
    return app


async def _on_file(h: Harness, shipped: Sequence[TemplateManifest]) -> dict[str, str]:
    """Each shipped template's stored content digest at the version shipped, by template id."""
    from brain.tables.template import TemplateVersionRow

    rows = (
        await h.execute(
            select(
                TemplateVersionRow.template_id,
                TemplateVersionRow.version,
                TemplateVersionRow.content_digest,
            ).where(
                TemplateVersionRow.template_id.in_([one.identity.template_id for one in shipped])
            )
        )
    ).all()
    wanted = {one.identity.template_id: one.identity.version for one in shipped}
    return {
        str(template_id): str(digest)
        for template_id, version, digest in rows
        if wanted.get(str(template_id)) == version
    }


def _copy(manifest: TemplateManifest, template_id: str) -> TemplateManifest:
    """The shipped manifest under a template id of the check's own."""
    identity = manifest.identity.model_copy(update={"template_id": template_id})
    return manifest.model_copy(update={"identity": identity})


async def _install(
    h: Harness, app: FastAPI, administrator: str, signed: SignedManifest
) -> dict[str, Any]:
    """The gallery's install button for one version, for the installer's department."""
    import json

    from brain.agent_lifecycle_routes import TemplateInstallAsked, install_version

    identity = signed.manifest.identity
    answered = await install_version(
        _request(app),
        identity.template_id,
        identity.version,
        TemplateInstallAsked(
            expected_digest=signed.content_digest, for_department=True, channels=("console",)
        ),
        await _asking(h, administrator),
    )
    if answered.status_code != 201:
        raise CheckFailedError(NOT_INSTALLED)
    return cast(dict[str, Any], json.loads(bytes(answered.body)))


# ------------------------------------------------------------- M13.5 the built-in templates
@check(
    leaves=(
        "M13.5.1",
        "M13.5.2",
        "M13.5.3",
        "M13.5.4",
        "M13.5.5",
        "M13.5.6",
        "M13.5.7",
        "M13.5.8",
        "M13.5.9",
        "M13.5.10",
        "M13.5.11",
        "M13.5.12",
        "M13.5.13",
        "M13.5.14",
        "M13.5.15",
        "M13.5.16",
        "M13.5.17",
        "M13.5.19",
        "M13.5.20",
        "M13.5.21",
        "M13.5.22",
        "M13.5.23",
    ),
    sentence=(
        "Every built-in template is on file exactly as this release ships it, and each, installed "
        "from the gallery by an administrator of acceptance_a, becomes an agent of acceptance_a, "
        "disabled at Shadow on every target with the ceiling its template declares; the "
        "accountant and SEM agents are Shadow-pinned, and the SEM agent can draft a budget change "
        "and never commit one."
    ),
)
async def every_built_in_template_is_on_file_and_installs_at_shadow(h: Harness) -> None:
    from sqlalchemy import update

    from brain.agents.catalogue import CATALOGUE
    from brain.agents.install_store import version_values
    from brain.agents.template import content_digest, publish
    from brain.core.envelope import SideEffect
    from brain.tables.agent import AgentRow
    from brain.tables.template import TemplateInstanceRow, TemplateVersionRow

    on_file = await _on_file(h, CATALOGUE)
    if not on_file:
        if h.settings.vault_address:
            raise CheckFailedError(NOTHING_ON_FILE_WITH_A_VAULT)
        raise CheckNotRunError(NOTHING_ON_FILE_AND_NO_VAULT)
    for manifest in CATALOGUE:
        stored = on_file.get(manifest.identity.template_id)
        if stored is None:
            raise CheckFailedError(MISSING)
        if stored != content_digest(manifest):
            raise CheckFailedError(NOT_AS_SHIPPED)

    administrator = await _administrator(h)
    key = secrets.token_hex(32)
    app = _gallery(h, key)
    for manifest in CATALOGUE:
        shipped_id = manifest.identity.template_id
        signed = publish(
            _copy(manifest, f"acceptance_{h.run}_{shipped_id}"),
            key=key,
            signed_by=administrator,
            at=h.now,
        )
        await h.execute(
            *h.attributed(administrator),
            insert(TemplateVersionRow).values(**version_values(signed)),
        )
        made = await _install(h, app, administrator, signed)
        row = (
            await h.execute(select(AgentRow).where(AgentRow.id == made["agent"]["agent_id"]))
        ).scalar_one_or_none()
        if row is None:
            raise CheckFailedError(NOT_INSTALLED)
        if row.department != A:
            raise CheckFailedError(NOT_IN_ITS_DEPARTMENT)
        rungs = {one["rung"] for one in made["leash"]}
        if row.disabled_at is None or (rungs and rungs != {"shadow"}):
            raise CheckFailedError(NOT_AT_SHADOW)
        authority, guardrails = manifest.authority, manifest.guardrails
        # The capabilities and the side-effect ceiling, as declared. Not the tool names: an
        # install binds a template's verbs to the tools this install has registered
        # (`brain.agents.install.bind_tool`), so the names differ by design.
        if (
            sorted(row.capabilities) != sorted(one.value for one in authority.capabilities)
            or row.max_side_effect != guardrails.max_side_effect.value
        ):
            raise CheckFailedError(NOT_ITS_CEILING)
        if shipped_id in SHADOW_PINNED and not await _refused(
            h,
            administrator,
            update(TemplateInstanceRow)
            .where(TemplateInstanceRow.id == row.id)
            .values(overlay=TemplateInstanceRow.overlay.op("||")(sa_json({LEASH_PATH: []}))),
        ):
            raise CheckFailedError(NOT_PINNED_AT_SHADOW)
        if shipped_id == DRAFTS_AND_NEVER_WRITES and row.max_side_effect != SideEffect.DRAFT.value:
            raise CheckFailedError(SEM_WRITES)


# ------------------------------------------------- M13.2 and M13.4 what a template version is
NOT_SIGNED: Final = "a template version signed by another key was installed from the gallery"
NOT_IMMUTABLE: Final = "a published template version could be changed in place"
NOT_PINNED: Final = "an installed agent's instance does not name the version it was installed from"
MOVED_BY_A_NEW_VERSION: Final = "publishing a new version changed an agent already installed"
NOT_SEALED: Final = "an installed agent's overlay could change a sealed path"
SEALED_TOO_WIDELY: Final = "an installed agent's overlay could not change a settable path"

#: The settable path the check changes to show the seal is not a refusal of everything.
SETTABLE_PROBE: Final = "persona"


async def _refused(h: Harness, actor: str, statement: Any) -> bool:
    """Whether the database refuses one statement, in a savepoint of the check's transaction."""
    from sqlalchemy.exc import DBAPIError

    try:
        await h.execute(*h.attributed(actor), statement)
    except DBAPIError:
        return True
    return False


@check(
    leaves=("M13.2.1", "M13.2.3", "M13.2.6", "M13.4.1"),
    sentence=(
        "A template version signed by another key is refused by the gallery's install; a stored "
        "version cannot be changed and a second stands beside it; an agent installed from the "
        "first names that version and its digest, publishing the second changes nothing about "
        "it, and its overlay is refused each of the five sealed paths and accepted a settable one."
    ),
)
async def a_template_version_is_signed_kept_and_pins_what_was_installed(h: Harness) -> None:
    from sqlalchemy import update

    from brain.agents.catalogue import business_analyst
    from brain.agents.install_store import version_values
    from brain.agents.template import SEALED_PATHS, publish
    from brain.tables.agent import AgentRow
    from brain.tables.template import TemplateInstanceRow, TemplateVersionRow

    administrator = await _administrator(h)
    key = secrets.token_hex(32)
    app = _gallery(h, key)
    template_id = f"acceptance_{h.run}_pinned"
    shipped = _copy(business_analyst(), template_id)

    def signed_at(version: int, persona: str, with_key: str) -> SignedManifest:
        identity = shipped.identity.model_copy(update={"version": version})
        return publish(
            shipped.model_copy(update={"identity": identity, "persona": persona}),
            key=with_key,
            signed_by=administrator,
            at=h.now,
        )

    first = signed_at(1, shipped.persona, key)
    await h.execute(
        *h.attributed(administrator), insert(TemplateVersionRow).values(**version_values(first))
    )
    made = await _install(h, app, administrator, first)
    agent_id = made["agent"]["agent_id"]

    async def pinned() -> tuple[Any, Any]:
        instance = (
            await h.execute(select(TemplateInstanceRow).where(TemplateInstanceRow.id == agent_id))
        ).scalar_one_or_none()
        agent = (
            await h.execute(select(AgentRow).where(AgentRow.id == agent_id))
        ).scalar_one_or_none()
        if instance is None or agent is None:
            raise CheckFailedError(NOT_PINNED)
        return (
            (instance.template_id, instance.template_version, instance.content_digest),
            (instance.effective_hash, agent.persona),
        )

    reference, before = await pinned()
    if reference != (template_id, 1, first.content_digest):
        raise CheckFailedError(NOT_PINNED)

    second = signed_at(2, shipped.persona + " The second version.", key)
    await h.execute(
        *h.attributed(administrator), insert(TemplateVersionRow).values(**version_values(second))
    )
    if await pinned() != (reference, before):
        raise CheckFailedError(MOVED_BY_A_NEW_VERSION)
    if not await _refused(
        h,
        administrator,
        update(TemplateVersionRow)
        .where(TemplateVersionRow.template_id == template_id, TemplateVersionRow.version == 1)
        .values(signed_by=h.actor),
    ):
        raise CheckFailedError(NOT_IMMUTABLE)

    forged = signed_at(3, shipped.persona, secrets.token_hex(32))
    await h.execute(
        *h.attributed(administrator), insert(TemplateVersionRow).values(**version_values(forged))
    )
    try:
        await _install(h, app, administrator, forged)
    except CheckFailedError:
        pass
    else:
        raise CheckFailedError(NOT_SIGNED)

    row = TemplateInstanceRow.id == agent_id
    for path in SEALED_PATHS:
        overlay = TemplateInstanceRow.overlay.op("||")(sa_json({path: "changed"}))
        if not await _refused(
            h, administrator, update(TemplateInstanceRow).where(row).values(overlay=overlay)
        ):
            raise CheckFailedError(NOT_SEALED)
    settable = TemplateInstanceRow.overlay.op("||")(sa_json({SETTABLE_PROBE: "changed"}))
    if await _refused(
        h, administrator, update(TemplateInstanceRow).where(row).values(overlay=settable)
    ):
        raise CheckFailedError(SEALED_TOO_WIDELY)


def sa_json(value: dict[str, Any]) -> Any:
    """A JSONB literal for `||`, bound rather than spliced."""
    from sqlalchemy import cast as sql_cast
    from sqlalchemy import literal
    from sqlalchemy.dialects.postgresql import JSONB

    return sql_cast(literal(value, type_=JSONB), JSONB)
