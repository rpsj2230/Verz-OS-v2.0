"""The install acceptance check for the six role templates: sources, skills, tools, and an install
that can answer.

`brain.ops.acceptance_checks_templates` proves every built-in template is on file as shipped and
installs at Shadow, and a template that does that can still be useless: it can name an entity no
source registers, or a skill the install does not hold, and install, enabled and supervised, into
an agent that reads nothing. The maintenance, SEO, sales, finance, support and project management
agents are the ones the owner named (M13.7.9, M13.8.7, M13.8.8), so this holds them to the
sentence those leaves say, on this install's own registries.

**Four things are asked of each, and each is asked of what this install holds.** The version on
file is the one this release ships, by the digest a signature is taken over. Each connector it
declares is one this release ships, so the install is waiting for a binding somebody can make.
Each skill it pins is pinned at the digest of the starter skill this release furnishes, so the
library an install is furnished with is the one the template was written against. And every tool
it declares binds to a tool the install registers, **with the website check registered the way the
application registers it**, because a registry built without it would report the maintenance and
SEO agents' check as unbound on an install that has it.

**Then it is installed, from the gallery's own route, and made to start a run.** Installed as a
reserved administrator of acceptance_a over a copy signed with a key made for the check, which is
the other half of `acceptance_checks_templates`: the agent exists, is disabled until what it needs
is connected and sits at Shadow, its connectors are the ones declared and the skills its instance
carries are the ones pinned. And finished again over a registry in which its connectors serve, so
the install is complete and the real gate starts a run for somebody who holds its whole ceiling,
which is the leaf's "installs into an agent that answers" and the closest a check can come without
asking a model. A connector actually connected is not assumed and is not needed: an install that
has not connected Freshdesk still proves its agents would answer once it is.

**Not run only where there is nothing to read.** No vault and nothing on file is not run, and a
vault with nothing on file is a failure, as in the check this one stands beside.

Task ids: M13.7.9, M13.8.7, M13.8.8
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

from sqlalchemy import insert, select

from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_checks_templates import _administrator, _copy, _install, _on_file
from brain.ops.acceptance_run import Harness

if TYPE_CHECKING:
    from fastapi import FastAPI

    from brain.agents.template import TemplateManifest
    from brain.connectors.registry import ConnectorRegistry

A, _ = RESERVED_DEPARTMENTS

#: Where this module's check stands on the Install page, beside the built-in templates' own. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 401

NOTHING_ON_FILE_WITH_A_VAULT: Final = (
    "this install keeps a vault and holds no role template, so its start signed nothing"
)
NOTHING_ON_FILE_AND_NO_VAULT: Final = (
    "this install has no vault, so it holds no signing key and no built-in template; the gallery "
    "says installing is unavailable"
)
MISSING: Final = "a role template this release ships is not on file"
NOT_AS_SHIPPED: Final = "a role template on file is not the one this release ships"
NOT_A_CONNECTOR_OF_THIS_RELEASE: Final = (
    "a role template declares a connector this release does not ship, so no binding can serve it"
)
NOT_THE_SKILL_FURNISHED: Final = (
    "a role template pins a skill at a digest this release's starter pack does not furnish"
)
A_TOOL_BINDS_NOTHING: Final = (
    "a tool a role template declares binds to no tool this install registers"
)
NOT_INSTALLED: Final = "a role template could not be installed from the gallery"
NOT_AT_SHADOW: Final = "an installed role agent was not disabled at Shadow on every target"
NOT_ITS_CONNECTORS: Final = "an installed role agent does not name the connectors its template does"
NOT_ITS_SKILLS: Final = "an installed role agent does not carry the skills its template pins"
NOT_COMPLETE_WITH_ITS_CONNECTORS: Final = (
    "a role template is not complete on this install's registries even with its connectors serving"
)
NOT_STARTED: Final = (
    "the gate did not start a run through an installed role agent for somebody holding its ceiling"
)


def _app(h: Harness, key: str) -> FastAPI:
    """What the template routes read: the check's transaction, its own key and the registry the
    application builds, website check included."""
    from fastapi import FastAPI

    from brain.knowledge.row_store import SessionRowSource
    from brain.ops.webhook_delivery import SystemResolver
    from brain.ops.website_probe import HttpsProber
    from brain.tools.startup import build_registry
    from brain.tools.website_check import WebsiteCheckTool

    app = FastAPI()
    app.state.db_sessions = h.sessions
    app.state.template_key = key
    app.state.tools = build_registry(
        source=h.settings.tool_source,
        records=SessionRowSource(h.sessions),
        website=WebsiteCheckTool(resolver=SystemResolver(), prober=HttpsProber()),
    )
    return app


def _serving(names: tuple[str, ...], at: datetime) -> ConnectorRegistry:
    """Every named connector installed and switched on, so a connector is never the reason an
    install below is incomplete. Synthetic, because the question is whether the template would
    answer once its sources are connected, which an install that has connected none still asks."""
    from brain.connectors.contract import ConnectorScope, CredentialBinding, TransportKind
    from brain.connectors.manifest import (
        ChangeSignal,
        ConnectorManifest,
        FieldShape,
        HotUse,
        ProjectedEntity,
        ProjectedField,
        ToolDeclaration,
    )
    from brain.connectors.registry import INSTALL_AUTHORITY, ConnectorRegistry
    from brain.core.entitlement import EntitlementSet, Grant
    from brain.core.scope import Scope
    from brain.ops.secrets import SecretRef, VaultRole

    admin = EntitlementSet(
        principal_id="svc_connector_install",
        grants=(Grant(capability=INSTALL_AUTHORITY, scope=Scope.unrestricted()),),
    )
    registry = ConnectorRegistry()
    for name in names:
        registry.register(
            ConnectorManifest(
                name=name,
                version="1.0.0",
                transport=TransportKind.REST,
                scope=ConnectorScope(resource_kind="view", selectors=("records",)),
                credential=CredentialBinding(
                    ref=SecretRef(path=f"kv/{name}", role=VaultRole.APPLICATION)
                ),
                tools=(
                    ToolDeclaration(
                        name=f"{name}.read_record", description="One record.", entity="record"
                    ),
                ),
                projections=(
                    ProjectedEntity(
                        entity="record",
                        fields=(
                            ProjectedField(
                                name="id", shape=FieldShape.IDENTIFIER, uses=(HotUse.IDENTIFY,)
                            ),
                            ProjectedField(
                                name="status", shape=FieldShape.STATUS, uses=(HotUse.FILTER,)
                            ),
                        ),
                        change_signal=ChangeSignal.WEBHOOK,
                        visibility=Scope.department(A),
                    ),
                ),
            ),
            installer=admin,
            now=at,
        )
        registry.enable(name, installer=admin, now=at)
    return registry


def _answers(manifest: TemplateManifest, app: FastAPI, at: datetime) -> bool:
    """Whether the real gate starts a run through an install of this manifest, over this install's
    tool registry and connectors that serve, for somebody holding the agent's whole ceiling."""
    from brain.agents.install import Offer, begin, complete, rehearse
    from brain.agents.model import AgentAudience, entitlement_ceiling
    from brain.agents.template import publish
    from brain.core.entitlement import EntitlementSet
    from brain.gate.injection import RiskAssessment
    from brain.knowledge.visibility import Visibility

    key = secrets.token_hex(32)
    tools = app.state.tools
    signed = publish(manifest, key=key, signed_by="system", at=at)
    audience = AgentAudience(level=Visibility.PERSONAL, owner_id="acceptance_installer")
    draft = begin(
        Offer(signed=signed, audience=audience),
        instance_id=manifest.identity.template_id,
        installer="acceptance_installer",
    )
    installed = complete(
        draft,
        key=key,
        audience=audience,
        registry=_serving(manifest.connectors, at),
        tools=tools,
        at=at,
    )
    if not installed.completeness.is_ready:
        raise CheckFailedError(NOT_COMPLETE_WITH_ITS_CONNECTORS)
    holder = EntitlementSet(
        principal_id="acceptance_holder", grants=entitlement_ceiling(installed.record).grants
    )
    return rehearse(
        installed,
        registry=tools,
        entitlement=holder,
        assessment=RiskAssessment(score=0, matched=()),
        now=at,
    ).started


# --------------------------------------------- M13.7.9, M13.8.7, M13.8.8 the six role templates
@check(
    leaves=("M13.7.9", "M13.8.7", "M13.8.8"),
    sentence=(
        "The maintenance, SEO, sales, finance, support and project management templates are on "
        "file as shipped, declare connectors and starter skills this release ships, and bind "
        "every tool to one this install registers; each installs as a disabled agent of "
        "acceptance_a at Shadow naming its connectors and skills, and with its sources serving "
        "the gate starts a run through it."
    ),
)
async def the_role_templates_declare_their_sources_and_would_answer(h: Harness) -> None:
    from brain.agents.catalogue import ROLE_TEMPLATES, catalogue_by_id
    from brain.agents.install import bind_tools
    from brain.agents.install_store import version_values
    from brain.agents.template import content_digest, publish
    from brain.connectors.declaration import shipped
    from brain.tables.agent import AgentRow
    from brain.tables.template import TemplateInstanceRow, TemplateVersionRow
    from brain.tools.skills import skill_from_markdown
    from brain.tools.starter_skills import STARTER_SKILLS

    manifests = tuple(catalogue_by_id()[one] for one in ROLE_TEMPLATES)
    on_file = await _on_file(h, manifests)
    if not on_file:
        if h.settings.vault_address:
            raise CheckFailedError(NOTHING_ON_FILE_WITH_A_VAULT)
        raise CheckNotRunError(NOTHING_ON_FILE_AND_NO_VAULT)
    furnished = {one.name: skill_from_markdown(one.markdown).digest() for one in STARTER_SKILLS}
    connectors = shipped()
    key = secrets.token_hex(32)
    app = _app(h, key)
    for manifest in manifests:
        stored = on_file.get(manifest.identity.template_id)
        if stored is None:
            raise CheckFailedError(MISSING)
        if stored != content_digest(manifest):
            raise CheckFailedError(NOT_AS_SHIPPED)
        if not set(manifest.connectors) <= set(connectors):
            raise CheckFailedError(NOT_A_CONNECTOR_OF_THIS_RELEASE)
        for pinned in manifest.skills:
            if furnished.get(pinned.name) != pinned.digest:
                raise CheckFailedError(NOT_THE_SKILL_FURNISHED)
        if not all(
            binding.ready
            for binding in bind_tools(manifest.authority.allowed_tools, app.state.tools)
        ):
            raise CheckFailedError(A_TOOL_BINDS_NOTHING)

    administrator = await _administrator(h)
    for manifest in manifests:
        signed = publish(
            _copy(manifest, f"acceptance_{h.run}_{manifest.identity.template_id}"),
            key=key,
            signed_by=administrator,
            at=h.now,
        )
        await h.execute(
            *h.attributed(administrator),
            insert(TemplateVersionRow).values(**version_values(signed)),
        )
        made = await _install(h, app, administrator, signed)
        agent_id = made["agent"]["agent_id"]
        row = (
            await h.execute(select(AgentRow).where(AgentRow.id == agent_id))
        ).scalar_one_or_none()
        if row is None:
            raise CheckFailedError(NOT_INSTALLED)
        if row.disabled_at is None or {one["rung"] for one in made["leash"]} - {"shadow"}:
            raise CheckFailedError(NOT_AT_SHADOW)
        if sorted(row.connectors) != sorted(manifest.connectors):
            raise CheckFailedError(NOT_ITS_CONNECTORS)
        instance = (
            await h.execute(select(TemplateInstanceRow).where(TemplateInstanceRow.id == agent_id))
        ).scalar_one()
        pinned_names = sorted(
            str(one.get("name")) for one in (instance.effective_document.get("skills") or [])
        )
        if pinned_names != sorted(one.name for one in manifest.skills):
            raise CheckFailedError(NOT_ITS_SKILLS)
        if not _answers(manifest, app, datetime.now(UTC)):
            raise CheckFailedError(NOT_STARTED)
