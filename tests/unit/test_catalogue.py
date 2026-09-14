"""The catalogue templates, held to the properties they were written to demonstrate.

`tests/unit/test_agent_template.py` proves the template model is correct. These prove it is
*usable*, which is a different claim: six manifests written against real agency work, each
driven through the real `materialise` rather than asserted about as data.

Task ids: M13.5.1, M13.5.2, M13.5.3, M13.5.4, M13.5.5, M13.5.6, M13.5.7, M13.5.8
Task ids: M13.5.9, M13.5.10, M13.5.11, M13.5.12, M13.5.13, M13.5.14, M13.5.15
Task ids: M13.5.16, M13.5.17, M13.5.19, M13.5.20, M13.5.21, M13.5.22, M13.5.23
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest

from brain.agents.catalogue import (
    CATALOGUE,
    PUBLISHER,
    accountant_agent,
    capacity_and_hours_analyst,
    catalogue_by_id,
    content_uploader,
    internal_helpdesk,
    knowledge_gap_curator,
    laravel_developer,
    pre_sales,
    sem_agent,
    seo_agent,
    site_health_sentinel,
    support_ticket_agent,
    ux_designer,
    wordpress_developer,
)
from brain.agents.install import (
    Installation,
    MissingKind,
    Offer,
    begin,
    complete,
    provide,
    rehearse,
)
from brain.agents.model import AgentAudience, entitlement_ceiling
from brain.agents.template import TemplateManifest, publish
from brain.app import Settings
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
from brain.core.envelope import SideEffect
from brain.core.scope import Scope
from brain.gate.injection import AutonomyTier, RiskAssessment
from brain.knowledge.rows import RowQuery
from brain.knowledge.visibility import Visibility
from brain.ops.secrets import SecretRef, VaultRole
from brain.tools.registry import ToolRegistry
from brain.tools.startup import build_registry

IDS = [m.identity.template_id for m in CATALOGUE]


@pytest.mark.parametrize("manifest", CATALOGUE, ids=IDS)
def test_every_template_starts_on_the_bottom_rung(manifest: TemplateManifest) -> None:
    """**The property the whole catalogue is written to.** A rung says how far a stranger's
    install should trust an agent on its first day, and the person who wrote the template has
    never met that company.

    Asserted over every target rather than over the leash as a whole, because a leash that is
    SHADOW on two targets and ASSISTED on a third is exactly the shape somebody adds while
    making one case convenient.

    Read-only templates declare it too, and that is deliberate rather than redundant: a
    read-only agent that is wrong is still wrong in somebody's answer, and SHADOW is what
    makes the first few wrong answers visible.

    Delete this and a template ships pre-trusted, which is a decision made by its author
    about a company they have never seen."""
    assert manifest.guardrails.leash, f"{manifest.identity.template_id} names no target"
    for rung in manifest.guardrails.leash:
        assert rung.rung is AutonomyTier.SHADOW, (
            f"{manifest.identity.template_id} ships {rung.target} pre-trusted at {rung.rung}"
        )


@pytest.mark.parametrize("manifest", CATALOGUE, ids=IDS)
def test_every_template_materialises_into_a_real_agent(manifest: TemplateManifest) -> None:
    """**The claim this whole module exists to test.** The template model is known to be
    correct; whether it can express a useful agent is a separate question and the only way to
    answer it is to build some and run them through the real path.

    `materialise` constructs an `AgentRecord`, so every validator in `brain.agents.model`
    runs: the tier must be one the router can route, the persona must not be empty, the
    audience and the authority must be consistent. A manifest that satisfies the schema and
    not those is a manifest that would fail at install time.

    Delete this and the catalogue can drift into a set of documents that parse and cannot be
    installed, which is the state a fixture-only test suite would never notice."""
    from datetime import UTC, datetime

    from brain.agents.model import AgentAudience
    from brain.agents.template import TemplateInstance, content_digest, materialise
    from brain.knowledge.visibility import Visibility

    signed = publish(
        manifest,
        key="a-key-for-this-test",
        signed_by="p_publisher",
        at=datetime(2026, 9, 6, tzinfo=UTC),
    )
    instance = TemplateInstance(
        instance_id=manifest.identity.template_id,
        template_id=manifest.identity.template_id,
        template_version=manifest.identity.version,
        content_digest=content_digest(manifest),
        created_by="p_installer",
    )
    effective = materialise(
        signed,
        instance,
        audience=AgentAudience(level=Visibility.COMPANY, owner_id="p_installer"),
    )

    assert effective.record.persona, "materialised with no persona"


@pytest.mark.parametrize("manifest", CATALOGUE, ids=IDS)
def test_no_template_can_do_more_than_draft(manifest: TemplateManifest) -> None:
    """Not one of these six needs to write, send or move money, and the ceiling says so
    rather than the persona.

    A persona reading "never change anything without asking" is a request to a model. A
    `max_side_effect` of NONE or DRAFT is a refusal `gate.leash.govern` enforces, and the
    difference between those two sentences is the difference between a guardrail and a hope.

    The bound is DRAFT rather than NONE because `sem_agent` legitimately composes a change
    for a person to commit. Anything above it here would be a template shipping the ability
    to act on a company it has never seen.

    Delete this and a template can acquire `SideEffect.WRITE` in one word, and the only
    symptom is an agent that starts doing things."""
    assert manifest.guardrails.max_side_effect in (SideEffect.NONE, SideEffect.DRAFT), (
        f"{manifest.identity.template_id} ships able to {manifest.guardrails.max_side_effect}"
    )


def test_a_human_commits_a_budget_change_and_the_ceiling_is_what_says_so() -> None:
    """M13.5.21 states the constraint in its own title: a human commits budget changes.

    That is `SideEffect.DRAFT` and it is the reason this template is in the catalogue and the
    AR chaser is not. DRAFT is a thing the gate can refuse; "shadow-pinned thirty days" is a
    duration the leash has nowhere to put.

    Asserted as DRAFT exactly rather than as "at most WRITE", because the whole point is that
    the agent prepares and does not apply, and NONE would be a different agent that cannot
    prepare either.

    Delete this and the one template whose title names a constraint stops being held to it."""
    assert sem_agent().guardrails.max_side_effect is SideEffect.DRAFT


def test_the_analyst_reads_the_hours_and_not_the_money_beside_them() -> None:
    """The fixture case `tests/e2e/test_wave_two_lark_question.py` drives with two real
    people, written as a template instead of a test double.

    A maintenance Base holds hours and contract values in one table, so an analyst that could
    read the row could read the money. The capability list is what separates them, and it is
    the ceiling rather than a filter applied later: `E_run = E(caller) ∩ ceiling`, so a caller
    who *can* see contract values still cannot see them through this agent.

    Delete this and the template can acquire the money capability while its persona still
    says it answers questions about hours."""
    held = {c.value for c in capacity_and_hours_analyst().authority.capabilities}

    assert "read:client.hours_remaining" in held
    assert "read:client.contract_value" not in held
    assert not any("margin" in value for value in held)


def test_the_accountant_may_read_the_ledger_and_may_not_move_anything() -> None:
    """The only template here naming money capabilities, and it still declares
    `SideEffect.NONE`.

    Reading a ledger and moving money are different verbs. A template that could do the
    second because it needed the first is how a reconciliation agent becomes a payment agent,
    and the change would read in review as one word in a field nobody looks at.

    Delete this and the money capabilities stay while the ceiling can rise."""
    manifest = accountant_agent()
    held = {c.value for c in manifest.authority.capabilities}

    assert "read:invoice.amount" in held
    assert manifest.guardrails.max_side_effect is SideEffect.NONE
    assert all(value.startswith("read:") for value in held), (
        "the accountant holds a capability that is not a read"
    )


def test_the_curator_reads_the_questions_and_never_who_asked() -> None:
    """M13.5.23's whole output is a list of things nobody wrote down, drawn from questions
    people asked. That makes it one capability away from a report on who keeps asking about
    pricing, which is a performance review assembled inside a curation tool.

    So it holds no capability naming a principal, a person or a department, and this asserts
    the absence rather than the presence, because the presence is what a future edit adds.

    Delete this and "who asked" becomes available to the one agent whose job makes it look
    useful."""
    held = {c.value for c in knowledge_gap_curator().authority.capabilities}

    for forbidden in ("principal", "person", "asker", "user", "department", "email"):
        assert not any(forbidden in value for value in held), (
            f"the curator can read something naming a {forbidden}"
        )


@pytest.mark.parametrize("manifest", CATALOGUE, ids=IDS)
def test_no_persona_tries_to_decide_a_permission(manifest: TemplateManifest) -> None:
    """Prompt material is stored and never parsed, so a persona saying "only show this to
    managers" is a permission decided by whoever last edited a text box, and enforced by
    nobody.

    The words below are the ones that would appear if somebody tried. It is a blunt check and
    it is meant to be: what it really guards is the habit, because the first persona that
    says "do not reveal salaries" is the one that makes the next reader believe personas are
    load-bearing.

    Delete this and the catalogue teaches, by example, that access control can be written in
    English."""
    lowered = manifest.persona.lower()

    for phrase in ("only show", "do not reveal", "not allowed to see", "only if the user is"):
        assert phrase not in lowered, (
            f"{manifest.identity.template_id}'s persona tries to decide a permission"
        )


def test_the_catalogue_is_distinct_templates_and_its_index_is_derived() -> None:
    """Two things that drift apart if either is maintained by hand: the ids inside the
    manifests and any mapping keyed by them.

    `catalogue_by_id` derives the mapping, so a template whose id changes cannot leave a stale
    key behind, and a duplicate id collapses the mapping rather than shipping two templates
    that install over each other.

    Delete this and two manifests can share an id, which the install flow would resolve by
    whichever it happened to read second."""
    index = catalogue_by_id()

    assert len(index) == len(CATALOGUE), "two templates share an id"
    assert set(index) == set(IDS)
    for template_id, manifest in index.items():
        assert manifest.identity.template_id == template_id


@pytest.mark.parametrize("manifest", CATALOGUE, ids=IDS)
def test_every_template_names_the_house_as_its_publisher(manifest: TemplateManifest) -> None:
    """`published_by` on a person is a record pointing at a principal who may have left, and
    `Principal.is_active` refuses one. A template outlives whoever wrote it.

    M13.6 is where a client's own templates get a real author, and that author is a person at
    that company rather than here.

    Delete this and a departed colleague's id is baked into a signed manifest."""
    assert manifest.identity.published_by == PUBLISHER


def test_the_templates_that_declare_a_connector_declare_one_that_exists() -> None:
    """A connector name in a manifest makes the install ask for a binding and reaches
    nothing, which means a typo produces a template that can never be completed: the install
    waits forever for a binding to a connector nobody can bind.

    Checked against the modules under `brain.connectors` rather than a list here, so a
    connector added or renamed moves this on its own.

    Delete this and `freshdsk` is a template that is permanently incomplete for a reason
    nobody can see from the console."""
    import pkgutil

    import brain.connectors as package

    available = {info.name for info in pkgutil.iter_modules(package.__path__)}
    declared = {name for manifest in CATALOGUE for name in manifest.connectors}

    assert declared, "no template declares a connector, so this checks nothing"
    assert declared <= available, f"declared but absent: {sorted(declared - available)}"


def test_the_support_agent_and_the_developer_both_wait_for_freshdesk() -> None:
    """Naming a connector reaches nothing: it makes `install.completeness` hold the agent
    incomplete and disabled until a binding exists.

    That is the property worth having for these two. A support agent that cannot see tickets
    must not answer a question about tickets from whatever else it can reach, and the
    mechanism that stops it is the install being incomplete rather than the agent being
    careful.

    Delete this and either template can lose its declaration and start answering from the
    knowledge base instead."""
    assert "freshdesk" in support_ticket_agent().connectors
    assert "freshdesk" in wordpress_developer().connectors


def test_no_two_templates_hold_the_same_authority() -> None:
    """**The failure a catalogue of twenty-three invites, and the one no other test here
    catches.**

    Writing this many templates in one sitting, the cheap way is to copy the last one, change
    the name and the persona, and leave the capability list alone. Every other test in this
    module passes on that: the ids are distinct, the rungs are SHADOW, the ceilings are within
    bounds, the personas decide no permissions. What would be wrong is that a Shopify
    developer and a Laravel developer reach the same things, so installing the narrower one
    buys nothing, and a reader comparing them learns that the distinctions in the docstrings
    are decoration.

    Compared as a frozen set of capability values, so ordering is not what makes two lists
    differ, and reported with both names so the duplicate is identifiable rather than merely
    counted.

    Delete this and the catalogue can grow by copying, which is exactly how it will grow."""
    seen: dict[frozenset[str], str] = {}

    for manifest in CATALOGUE:
        held = frozenset(c.value for c in manifest.authority.capabilities)
        first = seen.get(held)
        assert first is None, (
            f"{manifest.identity.template_id} reaches exactly what {first} reaches, so one "
            "of the two is a copy and installing the narrower buys nothing"
        )
        seen[held] = manifest.identity.template_id


def test_the_helpdesk_holds_no_capability_naming_a_person() -> None:
    """The most dangerous template here, and the danger is what it looks like rather than
    what it does.

    An internal helpdesk is asked everything, so it accumulates reach one reasonable request
    at a time: the leave policy, then a leave balance, then whose leave was approved. Each
    step is a small extension of the last and the destination is an HR system with a chat
    interface.

    Asserted as an absence rather than a presence, because the presence is what a future edit
    adds. The words below are the ones that would appear when somebody makes the reasonable
    next request.

    Delete this and "how much leave has she left" becomes answerable by the one agent whose
    job makes that look like a service."""
    held = {c.value for c in internal_helpdesk().authority.capabilities}

    for forbidden in ("person", "principal", "employee", "staff", "leave", "salary", "email"):
        assert not any(forbidden in value for value in held), (
            f"the helpdesk can read something naming a {forbidden}"
        )


def test_the_uploader_is_named_for_a_verb_it_cannot_perform() -> None:
    """`content_uploader` describes a job that writes and its ceiling is DRAFT, so a person
    commits.

    That gap between the name and the ceiling is the thing worth protecting, because it reads
    as an oversight: somebody will notice that the Content Uploader cannot upload and fix it,
    and the fix is one word. What it would buy is forty pages published with the wrong
    template and no record of what changed.

    DRAFT exactly rather than at most DRAFT, because NONE would be a different template that
    cannot prepare either, and the draft is the deliverable.

    Delete this and the one template whose name argues against its own ceiling loses the
    argument."""
    assert content_uploader().guardrails.max_side_effect is SideEffect.DRAFT


def test_the_two_marketing_agents_differ_by_ceiling_and_not_by_name() -> None:
    """`seo_agent` and `sem_agent` are the same discipline at different ceilings: one
    recommends and one spends. They sit beside each other in the module deliberately.

    This is the clearest statement in the catalogue that a ceiling follows what an agent can
    do rather than what it is called, and it is asserted because the pair is also the easiest
    place to lose it: the obvious tidy-up is to give two similar agents the same guardrails.

    Delete this and SEO can quietly acquire DRAFT, or SEM lose it, and the catalogue stops
    demonstrating the distinction it was written to demonstrate."""
    assert seo_agent().guardrails.max_side_effect is SideEffect.NONE
    assert sem_agent().guardrails.max_side_effect is SideEffect.DRAFT

    seo_held = {c.value for c in seo_agent().authority.capabilities}
    assert not any("budget" in value or "campaign" in value for value in seo_held), (
        "the SEO agent can reach a campaign or a budget, which is the SEM agent's work"
    )


def test_the_sentinel_reaches_nothing_that_would_be_a_count() -> None:
    """A monitoring agent's natural output is a list of everything that is wrong, and a list
    of everything is the one thing this system cannot produce.

    `E_run = E(caller) intersected with the ceiling` means the answer is over the caller's
    sites, so a sentinel reporting "three sites are down" to somebody entitled to see one has
    disclosed two. The defence is that there is no figure to reach rather than a rule about
    rendering: the redactor withholds a count over a filtered collection, and this template
    gives it nothing to withhold.

    Delete this and the sentinel can grow a capability naming a total, which is the most
    natural thing in the world to add to a monitoring agent."""
    held = {c.value for c in site_health_sentinel().authority.capabilities}

    for forbidden in ("count", "total", "summary", "all_sites", "estate"):
        assert not any(forbidden in value for value in held), (
            f"the sentinel can read a {forbidden}, which is a fact about what it cannot see"
        )


def test_the_laravel_agent_reads_the_shape_of_an_application_and_never_its_rows() -> None:
    """One word of difference and all of the difference: `read:model.name` is a fact about
    the application, and a model's records are a client's data. The same connector reaches
    both.

    This is the template where that line is easiest to cross, because "show me the model" and
    "show me what is in it" are one sentence apart in the question a developer actually asks.

    Delete this and a developer agent becomes a way to read production data with a
    developer's justification attached."""
    held = {c.value for c in laravel_developer().authority.capabilities}

    assert "read:model.name" in held
    for forbidden in ("record", "row", "data", "content", "value"):
        assert not any(forbidden in value for value in held), (
            f"the Laravel agent can read a {forbidden} rather than the application's shape"
        )


def test_the_presales_agent_reads_a_deals_stage_and_never_what_it_is_worth() -> None:
    """An agent that can see what a deal is worth can be asked which clients are worth
    answering quickly, and it will answer, because the figures are in front of it.

    The capability list is what prevents that. The persona is not, and a persona saying "do
    not rank clients by value" would be a permission decided by whoever last edited a text
    box.

    Delete this and the pre-sales template acquires the one capability that turns recall into
    triage."""
    held = {c.value for c in pre_sales().authority.capabilities}

    assert "read:deal.stage" in held
    for forbidden in ("value", "amount", "revenue", "margin", "worth"):
        assert not any(forbidden in one for one in held), (
            f"the pre-sales agent can read a deal's {forbidden}"
        )


def test_every_leaf_this_module_claims_has_a_template_behind_it() -> None:
    """The catalogue claims twenty-three leaves in its `Task ids:` line, and a claim is only
    worth what stands behind it.

    Counted rather than listed, and compared against the module's own docstring rather than
    against a number written here, so adding a template without claiming its leaf fails, and
    claiming a leaf without writing its template fails too. Those are the two directions and
    they are different mistakes: the first under-reports finished work, and the second is the
    one this repository has a `Reopens:` trailer for.

    The claims are also held against the work breakdown's own list of catalogue leaves, so
    a leaf can be neither forgotten nor invented. Until 2026-09-14 this asserted the chaser
    was absent, because the leash had no time dimension; `brain.agents.supervision` gave the
    pin one, and the twenty-third template closed the gap.

    Delete this and the docstring's claim and the tuple below it drift apart silently, which
    is the failure the traceability sweep exists to catch one level up."""
    from brain.agents import catalogue as module

    claimed = set(re.findall(r"M13[.]5[.]\d+", module.__doc__ or ""))

    assert len(claimed) == len(CATALOGUE), (
        f"the docstring claims {len(claimed)} leaves and the catalogue holds "
        f"{len(CATALOGUE)} templates"
    )
    import json
    from pathlib import Path

    plan = json.loads(
        (Path(__file__).resolve().parents[2] / "docs" / "wbs.json").read_text(encoding="utf-8")
    )
    leaves = {
        leaf for one in plan["modules"] for leaf in one["leaf_ids"] if leaf.startswith("M13.5.")
    }
    assert claimed == leaves, (
        f"catalogue leaves with no template: {sorted(leaves - claimed)}; "
        f"claimed and not leaves: {sorted(claimed - leaves)}"
    )


def test_the_chaser_is_reviewed_at_thirty_days_and_no_timer_ever_releases_it() -> None:
    """**The leaf's own words are "shadow-pinned thirty days", and this is what they mean
    here.** The number of days is read out of the work breakdown rather than restated,
    because a test comparing `SHADOW_REVIEW_PERIOD` with a thirty written beside it is green
    for every value the two could agree on.

    Then the part the owner decided. The chaser declares SHADOW on every target, a review
    before the period is not yet due, and on the day it falls due an unreviewed chaser is not
    released: the pin extends. Nothing on the manifest carries a date that could run out.

    Delete this and the chaser's thirty days is a word in a docstring with nothing behind
    it."""
    import json
    from datetime import UTC, datetime, timedelta
    from pathlib import Path

    from brain.agents.catalogue import catalogue_by_id
    from brain.agents.supervision import SHADOW_REVIEW_PERIOD, ShadowOutcome, pin, review
    from brain.gate.injection import AutonomyTier

    plan = json.loads(
        (Path(__file__).resolve().parents[2] / "docs" / "wbs.json").read_text(encoding="utf-8")
    )
    texts = {
        leaf: sentence
        for one in plan["modules"]
        for leaf, sentence in zip(one["leaf_ids"], one["leaf_texts"], strict=True)
    }
    stated = re.search(r"(\w+) days", texts["M13.5.18"])
    assert stated is not None, texts["M13.5.18"]
    assert timedelta(days={"thirty": 30}[stated.group(1)]) == SHADOW_REVIEW_PERIOD

    chaser = catalogue_by_id()["ar_and_renewal_chaser"]
    assert {one.rung for one in chaser.guardrails.leash} == {AutonomyTier.SHADOW}

    start = datetime(2019, 1, 1, tzinfo=UTC)
    held = pin("ag_chaser", now=start)
    early = review(held, simulated=(), reviews=(), now=start + timedelta(days=29))
    due = review(held, simulated=(), reviews=(), now=start + SHADOW_REVIEW_PERIOD)

    assert early.outcome is ShadowOutcome.NOT_YET_DUE
    assert due.outcome is ShadowOutcome.EXTENDED
    assert due.pin.review_due_at > held.review_due_at


def test_the_chaser_reads_what_is_late_and_never_what_it_is_worth() -> None:
    """A reminder needs the invoice, its status and its due date. The amount is the field
    that would make the chaser a second accountant and put a figure owed into a draft
    somebody might forward, so it is asserted by prefix rather than by name: holding
    `read:invoice.amount_due` fails as surely as `read:invoice.amount`.

    Delete this and the chaser's ceiling can grow to the ledger's without another test here
    noticing, because it would still differ from the accountant by its due date."""
    from brain.agents.catalogue import catalogue_by_id

    chaser = catalogue_by_id()["ar_and_renewal_chaser"]
    held = {one.value for one in chaser.authority.capabilities}

    assert "read:invoice.due_date" in held
    assert not any(value.startswith("read:invoice.amount") for value in held), held
    assert chaser.guardrails.max_side_effect.name == "DRAFT"


def test_the_ux_designer_reads_a_finding_and_never_who_produced_it() -> None:
    """**Written because a mutation survived.** The module's own docstring says the UX
    designer "reads a finding and never the participant", and adding
    `read:research_finding.participant` passed the whole file. A claim in prose with nothing
    behind it is the shape this repository keeps finding, and it was mine this time.

    A usability session has a person in it. A template that can name them turns a research
    archive into a record of which member of a client's staff struggled with the checkout,
    and it does so while looking like better citation. The finding is the product; who
    produced it is not, and the distinction survives only if it is asserted.

    Absence rather than presence, for the same reason the curator's and the helpdesk's tests
    are: the presence is what a future edit adds, one reasonable request at a time.

    Delete this and the participant comes back, and the docstring goes on saying otherwise."""
    held = {c.value for c in ux_designer().authority.capabilities}

    assert "read:research_finding.summary" in held
    for forbidden in ("participant", "person", "user", "tester", "name", "email"):
        assert not any(forbidden in value for value in held), (
            f"the UX designer can read something naming a {forbidden}"
        )


def test_no_built_in_template_is_published_by_a_company() -> None:
    """**`PUBLISHER` read `"verz"` until 2026-09-08, twenty-two times.** Every built-in
    template shipped to every client stamped with the first client's name, which is the
    violation `CLAUDE.md` forbids in its first rule and which `brain.install` uses as its
    illustration of the archetypal defect.

    **`client_independence` was green over it and could not have caught it.**
    `value_shaped_literals` matches an address, a bare IPv4 or an absolute URL, and a company
    slug is none of those. `install.py` already says why: a company name has no shape, so a
    shape-based sweep cannot find one. Widening the pattern is not the fix; it would have to
    become a list of company names, which is the blocklist that passes for every company
    except the ones on it.

    So the anchor is the value rather than the shape. The catalogue's publisher is the
    system's, `brain.agents.template.SYSTEM_PUBLISHER`, which existed in the same package for
    the blank template and for the same reason: nobody in particular published these. Compared
    against that constant rather than against the string "system", so the two cannot drift,
    and asserted over every template rather than over the constant alone, because the constant
    being right does not mean every manifest uses it.

    Delete this and the next person naming a publisher has nothing to stop them writing a
    company, and the sweep will go on saying the tree is clean."""
    from brain.agents.template import SYSTEM_PUBLISHER

    assert PUBLISHER is SYSTEM_PUBLISHER

    published = {one.identity.published_by for one in CATALOGUE}

    assert published == {SYSTEM_PUBLISHER}
    assert len(CATALOGUE) > 5, "almost no templates were read, so an empty difference is nothing"


# ------------------------------------------------------------- the tools a template uses
@pytest.mark.parametrize("manifest", CATALOGUE, ids=IDS)
def test_every_template_declares_its_tools_once(manifest: TemplateManifest) -> None:
    """**The leash targets are the tools, and there is one declaration of them.** Until
    2026-09-14 every template named its tools on its leash and allowed none, so the gate, which
    keeps a tool only when the ceiling allows it, kept nothing for any of them.

    Held as equality rather than containment in either direction, because each direction is its
    own mistake: a tool allowed and not leashed runs at `MISSING_ENTRY_RUNG`, which is SHADOW by
    a fallback rather than by the template's word, and a tool leashed and not allowed is
    supervision written for a tool the agent can never call.

    Delete this and the two lists drift, and the first symptom is an agent that starts no run."""
    assert manifest.authority.allowed_tools, f"{manifest.identity.template_id} allows no tool"
    assert set(manifest.authority.allowed_tools) == {
        rung.target for rung in manifest.guardrails.leash
    }


@pytest.mark.parametrize("manifest", CATALOGUE, ids=IDS)
def test_every_tool_a_template_reads_is_on_an_entity_its_ceiling_reads(
    manifest: TemplateManifest,
) -> None:
    """**Written because the analyst read `record` and its ceiling read `client`.** A tool that
    reads or searches an entity requires the read of that entity, and a ceiling derives the
    read only of an entity it names a column of, so a tool on any other entity binds, if it
    binds at all, to something no run through the agent can reach.

    Delete this and a template can declare a read nobody can ever make through it, and it shows
    up only as an agent that starts and never finds anything."""
    read_entities = {
        capability.value.partition(":")[2].partition(".")[0]
        for capability in manifest.authority.capabilities
        if capability.verb == "read"
    }

    for target in manifest.authority.allowed_tools:
        entity, _, verb = target.partition(".")
        if verb in ("read", "search"):
            assert entity in read_entities, (manifest.identity.template_id, target)


KEY = "a-key-for-installing-the-catalogue"
INSTALLER = "u_installer"
NOW = datetime(2019, 1, 1, 9, 0, tzinfo=UTC)
CLEAN = RiskAssessment(score=0, matched=())


class _NoRows:
    """A row source with nothing in it: these tests ask which tools exist, not what they read."""

    async def rows(self, query: RowQuery) -> Sequence[Mapping[str, Any]]:
        del query
        return ()


def _serving(names: tuple[str, ...]) -> ConnectorRegistry:
    """Every connector a template declares, installed and switched on, so a connector is never
    the reason an install below is incomplete."""
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
                        visibility=Scope.department("maintenance"),
                    ),
                ),
            ),
            installer=admin,
            now=NOW,
        )
        registry.enable(name, installer=admin, now=NOW)
    return registry


def _installed(manifest: TemplateManifest, tools: ToolRegistry) -> Installation:
    """Installed through every step of the wizard, with every placeholder answered and every
    connector serving, so a tool is the only thing that can be missing."""
    signed = publish(manifest, key=KEY, signed_by=PUBLISHER, at=NOW)
    audience = AgentAudience(level=Visibility.PERSONAL, owner_id=INSTALLER)
    draft = begin(
        Offer(signed=signed, audience=audience),
        instance_id=manifest.identity.template_id,
        installer=INSTALLER,
    )
    for placeholder in manifest.placeholders:
        if placeholder.required:
            draft = provide(draft, placeholder.key, f"this install's {placeholder.key}")
    return complete(
        draft,
        key=KEY,
        audience=audience,
        registry=_serving(manifest.connectors),
        tools=tools,
        at=NOW,
    )


#: The sources the application reads: its default, and the demo's.
SOURCES = [Settings().tool_source, "demo"]


@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.parametrize("manifest", CATALOGUE, ids=IDS)
def test_an_installed_template_is_ready_only_when_the_gate_starts_it_for_its_ceilings_holder(
    manifest: TemplateManifest, source: str
) -> None:
    """**The defect, as a property of the whole catalogue.** Until 2026-09-14 the badge said
    READY for all twenty-three while `brain.gate.invoke.invoke` refused every one. So, against
    the registry the application builds for the source it reads by default and for the demo's,
    an install missing nothing must start a run through the real gate for somebody holding its
    whole ceiling, and an install missing something must name exactly the declared tools
    nothing bound.

    Delete this and the badge and the gate can disagree again, which nobody asking a question
    can see from where they are."""
    tools = build_registry(source=source, records=_NoRows())
    installed = _installed(manifest, tools)
    holder = EntitlementSet(
        principal_id="u_holder", grants=entitlement_ceiling(installed.record).grants
    )
    unbound = {binding.target for binding in installed.tools if not binding.ready}

    assert {(one.kind, one.name) for one in installed.completeness.missing} == {
        (MissingKind.TOOL, target) for target in unbound
    }
    if installed.completeness.is_ready:
        rehearsal = rehearse(
            installed, registry=tools, entitlement=holder, assessment=CLEAN, now=NOW
        )
        assert rehearsal.started, manifest.identity.template_id


@pytest.mark.parametrize("source", SOURCES)
def test_the_templates_that_read_only_documents_are_the_ones_every_install_can_start(
    source: str,
) -> None:
    """**The positive half, written out.** The property above holds vacuously for a catalogue
    in which nothing is ever READY, so the set that is READY is named: the three templates whose
    every tool is on the document plane, which every install with rows registers. Every other
    template declares a row tool, a search or a draft that no source registers today, and stays
    incomplete on both sources until one does.

    Delete this and a change that made every install incomplete passes the whole catalogue."""
    tools = build_registry(source=source, records=_NoRows())

    ready = {
        manifest.identity.template_id
        for manifest in CATALOGUE
        if _installed(manifest, tools).completeness.is_ready
    }

    assert ready == {"html_developer", "internal_helpdesk", "knowledge_gap_curator"}
