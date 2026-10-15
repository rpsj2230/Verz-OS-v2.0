"""Throwaway: the mutation table for the role templates pull request."""

from pathlib import Path

from brain.ops.mutation import Mutation, verify

CAT = "src/brain/agents/catalogue.py"
CHK = "src/brain/ops/acceptance_checks_role_templates.py"
ROLE = ("tests/unit/test_role_templates.py", "tests/unit/test_catalogue.py")
DB = "tests/unit/test_acceptance_role_templates.py::"

mutations = [
    Mutation(
        "a pinned skill digest no longer the starter pack's",
        CAT,
        '"ticket-analysis": "d6a74a916bb67fe76e712eac6df108ccc9bd7ce0fc5dba03a823c4b5af603cff",',
        '"ticket-analysis": "d6a74a916bb67fe76e712eac6df108ccc9bd7ce0fc5dba03a823c4b5af603cfe",',
        ROLE,
    ),
    Mutation(
        "a template pins the wrong skill's digest",
        CAT,
        "STARTER_SKILL_DIGESTS[name]) for name in names",
        'STARTER_SKILL_DIGESTS["seo-audit"]) for name in names',
        ROLE,
    ),
    Mutation(
        "the maintenance agent loses a skill",
        CAT,
        'skills=_skills("ticket-analysis", "website-health-check", "website-troubleshooting"),',
        'skills=_skills("ticket-analysis", "website-health-check"),',
        ROLE,
    ),
    Mutation(
        "the maintenance agent reads a client's contract value",
        CAT,
        '*_reads("laravel_client", "name", "status", "updated_at"),',
        '*_reads("laravel_client", "name", "status", "updated_at", "contract_value"),',
        ROLE,
    ),
    Mutation(
        "the maintenance agent loses the read-only browser",
        CAT,
        'Capability(value="read:browser_surface"),',
        'Capability(value="read:browser_surfaces"),',
        ROLE,
    ),
    Mutation(
        "the maintenance agent loses the ticket desk",
        CAT,
        'connectors=("freshdesk", "laravel"),\n        guardrails=ManifestGuardrails(\n'
        "            max_side_effect=SideEffect.NONE,\n            leash=_shadow(*tools),\n"
        '        ),\n        golden_set=(\n            GoldenCase(\n                question="Is this client\'s website still',
        'connectors=("laravel",),\n        guardrails=ManifestGuardrails(\n'
        "            max_side_effect=SideEffect.NONE,\n            leash=_shadow(*tools),\n"
        '        ),\n        golden_set=(\n            GoldenCase(\n                question="Is this client\'s website still',
        ROLE,
    ),
    Mutation(
        "the maintenance agent may write",
        CAT,
        "            max_side_effect=SideEffect.NONE,\n            leash=_shadow(*tools),\n"
        '        ),\n        golden_set=(\n            GoldenCase(\n                question="Is this client\'s website still',
        "            max_side_effect=SideEffect.WRITE,\n            leash=_shadow(*tools),\n"
        '        ),\n        golden_set=(\n            GoldenCase(\n                question="Is this client\'s website still',
        ROLE,
    ),
    Mutation(
        "the sales agent reads a deal's amount",
        CAT,
        '*_reads("hubspot_deal", "deal_name", "stage", "pipeline", "close_date"),',
        '*_reads("hubspot_deal", "deal_name", "stage", "pipeline", "close_date", "amount"),',
        ROLE,
    ),
    Mutation(
        "the finance agent reads a contact's tax number",
        CAT,
        '*_reads("xero_contact", "name"),',
        '*_reads("xero_contact", "name", "tax_number"),',
        ROLE,
    ),
    Mutation(
        "the SEO agent loses the search console",
        CAT,
        'connectors=("google_analytics", "search_console"),',
        'connectors=("google_analytics",),',
        ROLE,
    ),
    Mutation(
        "the support agent asks for a search no source registers",
        CAT,
        '        "knowledge.search",\n        "ticket.read",\n    )',
        '        "knowledge.search",\n        "ticket.read",\n        "ticket.search",\n    )',
        ROLE,
    ),
    Mutation(
        "a role template names a read as a write",
        CAT,
        'return tuple(Capability(value=f"read:{entity}.{one}") for one in fields)',
        'return tuple(Capability(value=f"write:{entity}.{one}") for one in fields)',
        ROLE,
    ),
    Mutation(
        "the install check stops asking about the SEO agent",
        CAT,
        '    "project_manager",\n    "seo_agent",\n    "support_ticket_agent",\n)',
        '    "project_manager",\n    "support_ticket_agent",\n)',
        ROLE,
    ),
    Mutation(
        "check: a stored template that is not the shipped one passes",
        CHK,
        "        if stored != content_digest(manifest):",
        "        if False:",
        (DB + "test_a_stored_role_template_that_is_not_the_shipped_one_fails_the_check",),
    ),
    Mutation(
        "check: a template missing from the install passes",
        CHK,
        "        if stored is None:",
        "        if False:",
        (DB + "test_a_role_template_the_release_ships_and_the_install_does_not_hold_fails_the_check",),
    ),
    Mutation(
        "check: a connector nobody ships passes",
        CHK,
        "        if not set(manifest.connectors) <= set(connectors):",
        "        if False:",
        (DB + "test_a_role_template_declaring_a_connector_nobody_ships_fails_the_check",),
    ),
    Mutation(
        "check: a skill the starter pack does not furnish passes",
        CHK,
        "            if furnished.get(pinned.name) != pinned.digest:",
        "            if False:",
        (DB + "test_a_role_template_pinning_a_skill_nothing_furnishes_fails_the_check",),
    ),
    Mutation(
        "check: a tool nothing binds passes",
        CHK,
        "        if not all(\n            binding.ready",
        "        if False and not all(\n            binding.ready",
        (DB + "test_a_role_template_declaring_a_tool_nothing_binds_fails_the_check",),
    ),
    Mutation(
        "check: an agent installed enabled passes",
        CHK,
        '        if row.disabled_at is None or {one["rung"] for one in made["leash"]} - {"shadow"}:',
        '        if False or {one["rung"] for one in made["leash"]} - {"shadow"}:',
        (DB + "test_an_install_that_leaves_the_role_agent_enabled_fails_the_check",),
    ),
    Mutation(
        "check: an agent starting above Shadow passes",
        CHK,
        '        if row.disabled_at is None or {one["rung"] for one in made["leash"]} - {"shadow"}:',
        "        if row.disabled_at is None or set():",
        (DB + "test_an_install_whose_agent_starts_above_shadow_fails_the_check",),
    ),
    Mutation(
        "check: an agent with no connectors named passes",
        CHK,
        "        if sorted(row.connectors) != sorted(manifest.connectors):",
        "        if False:",
        (DB + "test_an_install_that_drops_the_connectors_a_role_template_declares_fails_the_check",),
    ),
    Mutation(
        "check: an agent with no skills pinned passes",
        CHK,
        "        if pinned_names != sorted(one.name for one in manifest.skills):",
        "        if False:",
        (DB + "test_an_install_that_drops_the_skills_a_role_template_pins_fails_the_check",),
    ),
    Mutation(
        "check: an incomplete install with sources serving passes",
        CHK,
        "    if not installed.completeness.is_ready:",
        "    if False:",
        (DB + "test_a_role_template_that_is_incomplete_with_its_sources_serving_fails_the_check",),
    ),
    Mutation(
        "check: a gate that starts no run passes",
        CHK,
        "        if not _answers(manifest, app, datetime.now(UTC)):",
        "        if False:",
        (DB + "test_a_gate_that_starts_no_run_through_a_role_agent_fails_the_check",),
    ),
]

report = verify(mutations, repo=Path("."), carry=())
print(report.table())
print("SURVIVORS:", [one.label for one in report.survivors])
