"""The six role templates (maintenance, SEO, sales, finance, support, project management), held
to what an install can actually do with them.

`tests/unit/test_catalogue.py` holds every template to the properties the catalogue was written
for. These hold the six the owner named to a different one: that an install of each answers. A
template can materialise, sit on the bottom rung and still read nothing, because the entity it
names is one no source registers, and that is the defect version 2 of four of them fixes. So
every capability is held against the field rules of the connector that maps it, every tool
against the registry an install builds, every connector against the shipped declarations, and
every skill against the starter pack it pins.

Task ids: M13.7.9, M13.8.7, M13.8.8
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from brain.agents.catalogue import (
    STARTER_SKILL_DIGESTS,
    catalogue_by_id,
    maintenance_agent,
)
from brain.agents.install import MissingKind, bind_tools, rehearse
from brain.agents.model import entitlement_ceiling
from brain.connectors.declaration import shipped
from brain.core.entitlement import EntitlementSet
from brain.core.envelope import SideEffect
from brain.core.field_policy import Classification
from brain.knowledge.connector_rows import CONNECTOR_ROW_ENTITIES
from brain.knowledge.rows import RowQuery
from brain.ops.webhook_delivery import SystemResolver
from brain.ops.website_probe import HttpsProber
from brain.tools.skills import skill_from_markdown
from brain.tools.starter_skills import STARTER_SKILLS
from brain.tools.startup import build_registry
from tests.unit.test_catalogue import CLEAN, NOW, SOURCES, _installed

#: The six, by template id, and the leaf that asks for each.
ROLES: Mapping[str, str] = {
    "maintenance_agent": "M13.7.9",
    "seo_agent": "M13.8.7",
    "pre_sales": "M13.8.8",
    "accountant_agent": "M13.8.8",
    "support_ticket_agent": "M13.8.8",
    "project_manager": "M13.8.8",
}

#: The connectors each is written to read, which the leaves name.
CONNECTORS: Mapping[str, tuple[str, ...]] = {
    "maintenance_agent": ("freshdesk", "laravel"),
    "seo_agent": ("google_analytics", "search_console"),
    "pre_sales": ("hubspot",),
    "accountant_agent": ("xero",),
    "support_ticket_agent": ("freshdesk",),
    "project_manager": ("freshdesk", "laravel"),
}

#: The skills each carries. The finance agent carries none: no starter skill is about a ledger.
SKILLS: Mapping[str, frozenset[str]] = {
    "maintenance_agent": frozenset(
        {"ticket-analysis", "website-health-check", "website-troubleshooting"}
    ),
    "seo_agent": frozenset({"keyword-research", "monthly-seo-report", "seo-audit"}),
    "pre_sales": frozenset({"proposal-generation"}),
    "accountant_agent": frozenset(),
    "support_ticket_agent": frozenset({"ticket-analysis"}),
    "project_manager": frozenset({"ticket-analysis"}),
}

#: The role templates allowed to read a column classified above internal, and which columns.
#: Finance reads what an invoice is owed, which is the ledger's own restricted column.
SENSITIVE_BY_DESIGN: Mapping[str, frozenset[str]] = {
    "accountant_agent": frozenset({"read:xero_invoice.amount_due"}),
}

IDS = list(ROLES)


class _NoRows:
    """A row source with nothing in it: these tests ask which tools exist, not what they read."""

    async def rows(self, query: RowQuery) -> tuple[Mapping[str, object], ...]:
        del query
        return ()


def _registry(source: str):  # type: ignore[no-untyped-def]
    """The registry an install builds, with the website check the application registers."""
    from brain.tools.website_check import WebsiteCheckTool

    return build_registry(
        source=source,
        records=_NoRows(),
        website=WebsiteCheckTool(resolver=SystemResolver(), prober=HttpsProber()),
    )


def _field_rules() -> dict[str, Classification]:
    """Every field capability a shipped source's rows are classified by, with its classification."""
    from brain.knowledge.columns import PRICE_LIST

    found: dict[str, Classification] = {}
    for entities in CONNECTOR_ROW_ENTITIES.values():
        for one in entities:
            for rule in one.rules:
                found[rule.required_capability.value] = rule.classification
    for rule in PRICE_LIST.rules:
        found[rule.required_capability.value] = rule.classification
    return found


def test_the_six_role_templates_are_in_the_catalogue_under_the_ids_the_leaves_name() -> None:
    """Each of the six is a template an install is offered, and the maintenance agent is the
    one written for a leaf of its own.

    Delete this and a role template can be renamed or dropped while the catalogue still has
    twenty-odd entries and every other test in the file is green."""
    index = catalogue_by_id()

    assert set(ROLES) <= set(index)
    assert maintenance_agent().identity.template_id == "maintenance_agent"
    assert index["maintenance_agent"].identity.version == 1


def test_the_catalogues_list_of_role_templates_is_the_six_the_leaves_name() -> None:
    """The install check reads `ROLE_TEMPLATES`, so a template missing from it is one the check
    never asks about while every test here still passes.

    Delete this and a seventh or a dropped role template changes what the install proves without
    a line of this file noticing."""
    from brain.agents.catalogue import ROLE_TEMPLATES

    assert set(ROLE_TEMPLATES) == set(ROLES)
    assert len(ROLE_TEMPLATES) == len(set(ROLE_TEMPLATES))


@pytest.mark.parametrize("template_id", IDS)
def test_a_role_template_declares_the_connectors_its_leaf_names(template_id: str) -> None:
    """The ticket desk and the maintenance records for the maintenance agent, analytics and the
    search console for the SEO agent, and one source each for the others, every one a connector
    this release ships.

    Delete this and the maintenance agent can lose the ticket desk it exists to read, or the SEO
    agent can name a console that is not a connector, and the install waits for a binding
    nobody can make."""
    manifest = catalogue_by_id()[template_id]

    assert set(manifest.connectors) == set(CONNECTORS[template_id])
    assert set(manifest.connectors) <= set(shipped())


@pytest.mark.parametrize("template_id", IDS)
def test_a_role_template_carries_the_starter_skills_its_role_is_asked_through(
    template_id: str,
) -> None:
    """Each pins the skills of its role by name, and the finance agent pins none because none of
    the owner's eight is about a ledger.

    Delete this and a template can ship carrying no skill at all, or another role's, and the
    leaf that says it declares its skills is satisfied by nothing."""
    manifest = catalogue_by_id()[template_id]

    assert {one.name for one in manifest.skills} == SKILLS[template_id]


def test_every_skill_digest_a_template_pins_is_the_one_the_starter_pack_furnishes() -> None:
    """The literal digests in the catalogue equal the digests of the `SKILL.md` files this release
    furnishes, parsed by the same reader the library uses.

    They are literals so that a starter skill's wording cannot change six templates already on
    file under the same version: this goes red on the day the words change, and the person who
    changes them raises the templates' versions in the same commit.

    Delete this and a reworded starter skill leaves every pinned template naming a skill the
    install no longer holds, and nothing says so until an agent is asked to use it."""
    furnished = {one.name: skill_from_markdown(one.markdown).digest() for one in STARTER_SKILLS}

    assert dict(STARTER_SKILL_DIGESTS) == {name: furnished[name] for name in STARTER_SKILL_DIGESTS}
    for manifest in (catalogue_by_id()[one] for one in ROLES):
        for pinned in manifest.skills:
            assert STARTER_SKILL_DIGESTS[pinned.name] == pinned.digest


@pytest.mark.parametrize("template_id", IDS)
def test_every_capability_a_role_template_names_is_a_field_a_source_maps(
    template_id: str,
) -> None:
    """A capability on an entity a connector provides must be one of the field rules that
    connector classifies, so the template reads something rather than a name nothing maps. The
    knowledge library's own reads are the one entity no connector provides and are held by the
    document plane's own tests.

    Delete this and a role template can name `read:ticket.description` where Freshdesk maps
    `description_text`, which is exactly the defect version 1 had: installed, enabled and
    reading nothing."""
    from brain.agents.binding import provider_of

    rules = _field_rules()
    manifest = catalogue_by_id()[template_id]
    checked = 0
    for capability in manifest.authority.capabilities:
        if provider_of(capability.noun) is None and capability.noun != "price_list":
            continue
        checked += 1
        assert capability.value in rules, (template_id, capability.value)

    assert checked, f"{template_id} names no field of any source, so this proved nothing"


@pytest.mark.parametrize("template_id", [one for one in IDS if one not in SENSITIVE_BY_DESIGN])
def test_a_role_template_reads_nothing_classified_above_internal(template_id: str) -> None:
    """The sales agent reads a deal's stage and not its amount, the maintenance and project
    agents read a client's status and not its contract value, and the price list is read by its
    sell price and never its cost or margin. Held against the classifications themselves, so a
    column reclassified up, or a template widened to one, fails whichever moved.

    Delete this and a role template can be given a confidential column in a one-word edit that
    reads, in review, as one more field."""
    rules = _field_rules()
    manifest = catalogue_by_id()[template_id]
    above = {Classification.CONFIDENTIAL, Classification.RESTRICTED}

    reads = [one.value for one in manifest.authority.capabilities if one.value in rules]

    assert reads, template_id
    assert not [one for one in reads if rules[one] in above], (template_id, reads)


def test_the_finance_agent_reads_the_amount_owed_and_nothing_else_above_internal() -> None:
    """The finance agent exists to say what is owed, so it holds the ledger's restricted column,
    and it holds no other restricted or confidential one.

    Delete this and the finance agent can pick up the contact's tax number beside the amount."""
    rules = _field_rules()
    manifest = catalogue_by_id()["accountant_agent"]
    above = {Classification.CONFIDENTIAL, Classification.RESTRICTED}

    reads = {one.value for one in manifest.authority.capabilities if rules.get(one.value) in above}

    assert reads == SENSITIVE_BY_DESIGN["accountant_agent"]


@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.parametrize("template_id", IDS)
def test_a_role_template_installs_ready_and_a_run_through_it_starts(
    template_id: str, source: str
) -> None:
    """**The leaves' own sentence, as a property of the registry an install builds.** Every tool a
    role template declares binds to a registered tool, an install of it with its connectors
    serving is complete, and the real gate starts a run for somebody holding its whole ceiling.

    The positive half of everything above: a template whose every capability is a mapped field
    and whose every tool is unbound would pass those and answer nothing.

    Delete this and a role template can be installed READY on paper and refused by the gate on
    its first question."""
    manifest = catalogue_by_id()[template_id]
    tools = _registry(source)
    installed = _installed(manifest, tools)
    holder = EntitlementSet(
        principal_id="u_holder", grants=entitlement_ceiling(installed.record).grants
    )

    assert {binding.target for binding in installed.tools if not binding.ready} == set()
    assert installed.completeness.is_ready, installed.completeness.missing
    rehearsal = rehearse(installed, registry=tools, entitlement=holder, assessment=CLEAN, now=NOW)
    assert rehearsal.started, template_id


@pytest.mark.parametrize("template_id", IDS)
def test_a_role_template_whose_connector_is_not_serving_is_incomplete_and_not_answering(
    template_id: str,
) -> None:
    """Naming a connector holds the install incomplete until one serves, so the agent never
    answers a question about a source it cannot read from whatever else it can reach.

    Held for every role template with the connectors absent: each reports exactly the declared
    connectors as missing, and nothing else, so the badge says what to go and do.

    Delete this and a role template can lose the connectors it is written around and still
    install READY, answering from the knowledge library alone."""
    from brain.agents.install import Offer, begin, complete
    from brain.agents.model import AgentAudience
    from brain.agents.template import publish
    from brain.connectors.registry import ConnectorRegistry
    from brain.knowledge.visibility import Visibility
    from tests.unit.test_catalogue import INSTALLER, KEY

    manifest = catalogue_by_id()[template_id]
    tools = _registry(SOURCES[0])
    signed = publish(manifest, key=KEY, signed_by="system", at=NOW)
    audience = AgentAudience(level=Visibility.PERSONAL, owner_id=INSTALLER)
    draft = begin(
        Offer(signed=signed, audience=audience), instance_id=template_id, installer=INSTALLER
    )
    installed = complete(
        draft, key=KEY, audience=audience, registry=ConnectorRegistry(), tools=tools, at=NOW
    )

    missing = {(one.kind, one.name) for one in installed.completeness.missing}

    assert missing == {(MissingKind.CONNECTOR, name) for name in manifest.connectors}
    assert installed.record.disabled_at is not None


@pytest.mark.parametrize("template_id", IDS)
def test_a_role_template_reaches_no_further_than_a_read(template_id: str) -> None:
    """Every role template has a read-only ceiling, so none of the six can send, write or
    commit anything on its own word: the reply the maintenance agent prepares is a step of a
    workflow a person approves, which is put on the installed agent and is not in the template.

    Delete this and a role template can be given a write tool and keep installing at Shadow,
    which is a supervised agent that can act rather than an agent that cannot."""
    manifest = catalogue_by_id()[template_id]

    assert manifest.guardrails.max_side_effect is SideEffect.NONE
    assert not [
        one for one in manifest.authority.allowed_tools if ".write" in one or "reply" in one
    ]


@pytest.mark.parametrize("source", SOURCES)
def test_the_maintenance_agent_checks_a_website_over_http_and_may_open_the_read_only_browser(
    source: str,
) -> None:
    """The HTTP website check binds on an install that registers it, the capability the check
    needs to open the read-only browser is in the ceiling, and no other browser capability is:
    the surface-acting one is what a click, a typed value or a submitted form would need.

    Delete this and the maintenance agent can lose the website check it is named for, or gain the
    browser's write."""
    from brain.tools.website_check import WEBSITE_CHECK_TOOL

    manifest = maintenance_agent()
    tools = _registry(source)
    bound = {
        name
        for binding in bind_tools(manifest.authority.allowed_tools, tools)
        for name in binding.bound
    }
    held = {one.value for one in manifest.authority.capabilities}

    assert WEBSITE_CHECK_TOOL in bound
    assert {"read:website_check", "read:browser_surface"} <= held
    assert not [one for one in held if "act_on" in one or one.startswith("write:")]


def test_the_maintenance_agent_reads_a_clients_status_and_never_its_contract_value() -> None:
    """The maintenance records source is read for whether a client's plan is active and when that
    changed, and the restricted contract value beside it in the same view is not in the ceiling.

    Delete this and the maintenance agent can be asked what a client pays, and answer, because
    the number is in the row it already reads."""
    held = {one.value for one in maintenance_agent().authority.capabilities}

    assert {"read:laravel_client.status", "read:laravel_client.name"} <= held
    assert not [one for one in held if "contract" in one or "manager" in one]


def test_every_role_template_is_a_generic_entry_naming_no_company() -> None:
    """The persona, the summary and the golden cases of the six name no company, domain, person
    or client, because the catalogue is the product's and an install is somebody else's.

    Held as the absence of a capitalised word in the middle of a sentence, which is how a name
    appears, apart from the product names a template has to use. A blocklist of company names
    would pass for every company except the ones on it, and a template naming one is a value
    that has to be removed at the end and by then is in the history.

    Delete this and a role template can carry the first client's name in a golden case."""
    import re

    allowed = {"HTTP", "Freshdesk", "Laravel", "HubSpot", "Xero", "SEO", "SEM", "WooCommerce"}
    for template_id in ROLES:
        manifest = catalogue_by_id()[template_id]
        texts = [
            manifest.persona,
            manifest.identity.summary,
            *(case.question for case in manifest.golden_set),
            *(case.expectation for case in manifest.golden_set),
        ]
        for text in texts:
            for sentence in re.split(r"(?<=[.?!])\s+", text):
                inside = re.findall(r"\b[A-Z][A-Za-z]*\b", sentence)[1:]
                assert set(inside) <= allowed, (template_id, sorted(set(inside) - allowed))


def test_no_two_role_templates_reach_the_same_things() -> None:
    """The six hold six different capability sets, so choosing between the support agent and the
    maintenance agent buys a different reach and not a different name.

    Delete this and the project management agent can drift into the support agent with another
    persona, which the catalogue-wide copy check only sees when the sets are exactly equal."""
    held = {
        template_id: frozenset(
            one.value for one in catalogue_by_id()[template_id].authority.capabilities
        )
        for template_id in ROLES
    }

    assert len(set(held.values())) == len(ROLES)
    assert held["support_ticket_agent"] < held["maintenance_agent"]
