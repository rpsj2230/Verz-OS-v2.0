/**
 * The audit `docs/admin-console.md` asks for, as data a test can hold against the code, and the
 * document written from it.
 *
 * `docs/admin-console.md` ends with an audit: read the schema, the modules, the routes and the
 * settings, list everything an administrator would need to manage, compare it with what the console
 * serves screen by screen, and build or record every gap. Written by hand, that audit is true on
 * the day it is written. So the four lists are read, never typed: the areas from the standard's own
 * bullets, the tables and installation values from `src/api/generated/inventory.json` (which
 * `scripts/export-openapi.py` writes from `brain.db.Base.metadata` and `brain.install.INSTALLATION`),
 * the routes from the API's internal document, and the screens from the route files.
 *
 * **What is typed is the judgement, and every judgement is checked for coverage.** Which area a
 * table, a route, a value or a screen belongs to is not something the code can say, so it is written
 * here. `tests/console-audit.test.ts` refuses a table, a route, a value or a screen that no area
 * claims and nothing excuses, an excuse with no reason, a gap naming a leaf the work breakdown does
 * not have, and a document that differs from what this module renders.
 *
 * **Which screen reaches which route is observed, not claimed.** A read is the path a page asked
 * for when `support/pageCases.ts` opened it, which the state tests prove is every path it asks for.
 * A write is `support/writes.ts`' list of every call that sends one, each mapped to its route in
 * its module's file under `consoleAudit/` through the function that spells the address, and the
 * function is called to prove it.
 *
 * **The proofs of M27.8.17 are named tests, and each is found.** Every write a screen sends is
 * followed to its row, its audit entry and the behaviour it changes by naming the Python test that
 * asserts each, or by saying why there is none. The name is looked up in the file, and whether it
 * needs a live database is checked against what the file imports.
 *
 * Task ids: M27.8.1, M27.8.17
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { CONSOLE_ROOT, readRepoFile } from "./repo";
import type { Proof, Proofs, ReadAfterAnAction, WriteRoute } from "./auditClaims";

export type { Proof, Proofs, ReadAfterAnAction, WriteRoute } from "./auditClaims";

// ------------------------------------------------------------------------------------ inputs

export interface Inventory {
  readonly tables: readonly string[];
  readonly installation: readonly { readonly name: string; readonly belongs: string; readonly required: boolean }[];
}

/** What `scripts/export-openapi.py` wrote beside the API document. */
export function inventory(): Inventory {
  return JSON.parse(readFileSync(join(CONSOLE_ROOT, "src", "api", "generated", "inventory.json"), "utf8")) as Inventory;
}

/** The bullets under "What an administrator must be able to manage", in the standard's order. */
export function standardAreas(): string[] {
  const text = readRepoFile("docs/admin-console.md");
  const start = text.indexOf("## What an administrator must be able to manage");
  const end = text.indexOf("\n## ", start + 1);
  if (start < 0 || end < 0) {
    throw new Error("docs/admin-console.md no longer has the list of what an administrator manages.");
  }
  return text
    .slice(start, end)
    .split("\n")
    .filter((line) => line.startsWith("- "))
    .map((line) => line.slice(2).trim());
}

/** Every route the API document declares under `/api/v1` and `/setup`, as `METHOD path`. */
export function declaredRoutes(document: Record<string, unknown>): string[] {
  const found: string[] = [];
  for (const [path, operations] of Object.entries(document["paths"] as Record<string, Record<string, unknown>>)) {
    if (!path.startsWith("/api/v1/") && !path.startsWith("/setup/")) {
      continue;
    }
    for (const method of Object.keys(operations)) {
      if (["get", "post", "put", "patch", "delete"].includes(method)) {
        found.push(`${method.toUpperCase()} ${path}`);
      }
    }
  }
  return found.sort();
}

/** The route template a concrete path was asked of, or null. */
export function templateOf(document: Record<string, unknown>, path: string): string | null {
  // The most specific template wins, as it does in the router: `/service-accounts/keys` is the
  // literal route and not `/service-accounts/{client_id}` with an id of "keys".
  const matching = Object.keys(document["paths"] as Record<string, unknown>).filter((route) =>
    new RegExp(`^${route.replace(/\{[^}]+\}/g, "[^/]+")}$`).test(path),
  );
  const parameters = (route: string) => (route.match(/\{/g) ?? []).length;
  return [...matching].sort((a, b) => parameters(a) - parameters(b))[0] ?? null;
}

// ---------------------------------------------------------------------------- the judgement

/** A gap: what an administrator cannot do from the console, and the leaf or the reason. */
export interface Gap {
  readonly what: string;
  /** The open work breakdown leaf that builds it. */
  readonly leaf?: string;
  /** Why it is not a leaf: what would have to exist first, or why it should not be built. */
  readonly because?: string;
}

export interface Area {
  /** Console addresses, from the route files and `App.tsx`, that serve it. */
  readonly screens: readonly string[];
  /** Routes, as `METHOD path` or a path meaning every method; a trailing `*` matches a prefix. */
  readonly routes: readonly string[];
  readonly tables: readonly string[];
  readonly installation: readonly string[];
  readonly gaps: readonly Gap[];
}

const ONCE_BY_THE_WIZARD =
  "Set by the first-run wizard, which saves them to ops.setting, and no route changes one afterwards; " +
  "changing one today is editing the server's environment file or the row by hand.";

/** Every area of the standard, keyed by the standard's own words. */
export const AREAS: Readonly<Record<string, Area>> = {
  "People, roles, permissions and access control": {
    screens: ["/people", "/people/:personId", "/people/:personId/:view", "/roles", "/capabilities", "/scopes", "/packs", "/access_review", "/access_review/:kind/:rowId", "/elevation", "/elevation/:requestId", "/sessions", "/sign-in-links", "/staff_sources", "/access-requests", "/service-accounts", "/service-accounts/:clientId"],
    routes: [
      "/api/v1/me",
      "/api/v1/console/navigation",
      "/api/v1/govern/people",
      "/api/v1/govern/directory*",
      "/api/v1/govern/roles",
      "/api/v1/govern/capabilities",
      "/api/v1/govern/scopes",
      "/api/v1/govern/grants*",
      "/api/v1/govern/access-review*",
      "/api/v1/govern/elevation*",
      "/api/v1/govern/sessions*",
      "/api/v1/govern/sign-ins*",
      "/api/v1/sign-ins",
      "/api/v1/govern/data-steward",
      "/api/v1/govern/staff_sources*",
      "/api/v1/govern/packs*",
      "/api/v1/govern/roles/misconfigurations",
      "/api/v1/govern/people/disable",
      "/api/v1/govern/people/enable",
      "/api/v1/govern/service-accounts*",
      "/api/v1/access-requests*",
      "/api/v1/stewardship/self-grants",
      "/api/v1/escalations",
      "/api/v1/govern/roles/holders",
      "/api/v1/govern/roles/appointment",
      "/api/v1/govern/roles/deputy",
      "/api/v1/govern/roles/removal",
      "/api/v1/govern/roles/group-rules*",
    ],
    tables: [
      "auth.principal",
      "auth.principal_identity",
      "auth.session",
      "auth.directory_role_grant",
      "gate.capability_grant",
      "gate.capability_pack",
      "gate.capability_pack_assignment",
      "gate.capability_registry",
      "gate.scope",
      "gate.grants_version",
      "gate.policy_epoch",
      "gate.review_decision",
      "gate.elevation_request",
      "auth.staff_member",
      "auth.staff_sync_run",
      "auth.service_account",
      "auth.api_key",
      "gate.access_request",
      "gate.access_request_handled",
      "gate.role_grant",
      "auth.group_role_rule",
      "gate.break_glass_notice",
      "gate.self_grant",
      "ops.connector_steward",
    ],
    installation: [
      "INSTALL_OIDC_ISSUER",
      "INSTALL_OIDC_REALM",
      "INSTALL_OIDC_CLIENT_ID",
      "INSTALL_OIDC_REDIRECT_URIS",
      "INSTALL_BROKERED_DIRECTORY",
      "INSTALL_STAFF_SOURCE",
      "INSTALL_STAFF_SOURCE_LOCATION",
      "INSTALL_BROKERED_CLIENT_ID",
      "INSTALL_ACCOUNT_EMPLOYMENT_TYPES",
      "INSTALL_DEPARTMENTS_FROM",
    ],
    gaps: [
      {
        what: "Capabilities are read and never changed, and what a role grants is not edited.",
        because: "The capability registry is declared by the product's tools and connected sources, and a role grants nothing, so there is nothing to edit.",
      },
      {
        what: "What a run through an agent reaches for somebody else is not previewed on their Access view.",
        leaf: "M27.15.61",
      },
      {
        what: "GET /api/v1/govern/people, the grant-holder listing, is read by no screen since People lists every person from the directory.",
        because: "It is kept for any client of the API that reads grant holders by subject; the People list and each person's Grants view read GET /api/v1/govern/directory and its detail, which carry the same holdings with their scope and lapse.",
      },
      {
        what: "A break-glass notice to the standing Super Admins is shown on their Elevation screen and is not sent by email or chat, and nobody is told when somebody only asks.",
        because:
          "Nothing records a Super Admin's email address or chat identity for a notice to be sent to: auth.principal holds no address and principal_identity holds digests. The notice is written in the approval's transaction to gate.break_glass_notice and read by its recipient; a request is not an elevation until it is approved.",
      },
      { what: "The identity provider and the staff source cannot be changed after setup.", because: ONCE_BY_THE_WIZARD },
      {
        what: "A service account's end date and owner cannot be changed from Service accounts: no route writes auth.service_account after registration, so a new account is registered instead.",
        leaf: "M27.15.26",
      },
    ],
  },
  "Departments, teams and client configuration": {
    screens: ["/departments", "/departments/:slug", "/departments/:slug/:view", "/department", "/department/:view"],
    routes: ["/api/v1/govern/departments*"],
    tables: ["gate.department", "gate.team", "gate.team_membership", "gate.department_lead"],
    installation: ["INSTALL_COMPANY_NAME", "INSTALL_PRODUCT_NAME", "INSTALL_LOGO_URL", "INSTALL_ACCENT_COLOUR"],
    gaps: [
      {
        what: "Nothing applies the staff list's teams and leads on a schedule.",
        because: "brain.identity.organisation_sync plans them and brain.identity.organisation_store applies a plan, and no job runs either. The nightly staff sync (brain.ops.staff_sync_run, since 2026-09-21) applies the roster's people and marks leavers, and not its teams or leads.",
      },
    ],
  },
  "System settings and application configuration": {
    screens: ["/install", "/settings", "/limits", "/connections", "/first-run", "/first-run/staff-list"],
    routes: [
      "/api/v1/install",
      "/api/v1/install/settings*",
      "/api/v1/install/limits",
      "/api/v1/install/tuning*",
      "/api/v1/install/capacity",
      "/api/v1/digest/destination",
      "/setup/*",
    ],
    tables: ["ops.setting", "ops.budget_version"],
    installation: [
      "INSTALL_LOCALES",
      "INSTALL_CURRENCY",
      "INSTALL_TIME_ZONE",
      "INSTALL_DIGEST_DESTINATION",
      "INSTALL_DIGEST_TIME",
      "INSTALL_SERVICES",
    ],
    gaps: [
      {
        what: "Spending budgets are read and never changed.",
        because:
          "No route writes ops.budget_version. The request windows and capacity budgets are changed on Rate limits (brain.tuning_routes, since 2026-09-29); a spending ceiling is a release today.",
      },
    ],
  },
  "AI providers, models and the routing between them": {
    screens: ["/models", "/models/:provider", "/models/:provider/:view", "/routing", "/routing/:rungId"],
    routes: [
      "/api/v1/operate/models",
      "/api/v1/models/providers*",
      "/api/v1/models/profile",
      "/api/v1/models/prices",
      "/api/v1/routing/export",
      "/api/v1/routing/rungs*",
      "/api/v1/routing/changes",
      "/api/v1/routing/golden-questions*",
      "/api/v1/models/tiers*",
      "/api/v1/models/residency*",
    ],
    tables: [
      "ops.routing_rung",
      "ops.routing_tier",
      "ops.model_attempt",
      "ops.model_provider",
      "ops.golden_question",
      "ops.routing_change",
      "ops.provider_health",
      "ops.chain_depth_alert",
      "ops.residency_constraint",
    ],
    installation: ["INSTALL_MODEL_PROFILE", "INSTALL_MODEL_ENDPOINT", "INSTALL_EMBEDDING_DIMENSIONS"],
    gaps: [
      { what: "The model endpoint cannot be changed after setup.", because: ONCE_BY_THE_WIZARD },
      {
        what: "A provider's page shows no cost: cost is kept per request, whose calls can reach more than one provider, so it is left out rather than drawn as nought, and the Spend report shows it by model.",
        because: "brain.ops.usage_store writes one cost row per request with its model and no provider, and the spend rows are read under the spend grant, which a reader of the models screen need not hold.",
      },
    ],
  },
  "Agents and their configuration, including templates": {
    screens: [
      "/agents",
      "/agents/:agentId",
      "/agents/:agentId/:tab",
      "/agent-templates",
      "/agent-templates/:templateId",
      "/approvals",
      "/approvals/:suspensionId",
      "/agents/new",
      "/agents/drafts",
      "/agents/drafts/:draftId",
      "/agents/drafts/:draftId/:step",
    ],
    routes: [
      "/api/v1/agents",
      "/api/v1/agents/{agent_id}/workspace",
      "/api/v1/agents/{agent_id}/about",
      "/api/v1/agents/{agent_id}/conversations",
      "/api/v1/agents/{agent_id}/model-pin",
      "/api/v1/agents/{agent_id}/lifecycle",
      "/api/v1/agents/{agent_id}/enable",
      "/api/v1/agents/{agent_id}/disable",
      "/api/v1/agents/{agent_id}/archive",
      "/api/v1/agents/{agent_id}/transfer",
      "/api/v1/agents/{agent_id}/duplicate",
      "/api/v1/agents/{agent_id}/channels",
      "/api/v1/agents/{agent_id}/learning",
      "/api/v1/console/agents/{agent_id}/stats",
      "/api/v1/agents/{agent_id}/budget",
      "/api/v1/agents/{agent_id}/capabilities",
      "/api/v1/agents/{agent_id}/preview",
      "/api/v1/agents/{agent_id}/memory",
      "/api/v1/agents/{agent_id}/memory/{memory_id}/deletion",
      "/api/v1/agents/{agent_id}/memory/{memory_id}/edit",
      "/api/v1/agents/{agent_id}/artifacts",
      "/api/v1/agents/{agent_id}/artifacts/latest",
      "/api/v1/agents/{agent_id}/artifacts/{artifact_id}/download",
      "/api/v1/agents/{agent_id}/artifacts/{artifact_id}/archive",
      "/api/v1/agents/{agent_id}/artifacts/{artifact_id}/supersede",
      "/api/v1/agents/{agent_id}/leash",
      "/api/v1/agents/{agent_id}/leash/moves",
      "/api/v1/agents/{agent_id}/supervision/pin",
      "/api/v1/agents/{agent_id}/supervision/review",
      "/api/v1/agents/{agent_id}/supervision/verdicts",
      "/api/v1/agents/{agent_id}/attachments",
      "/api/v1/agent-templates",
      "/api/v1/agent-templates/{template_id}",
      "/api/v1/agent-templates/{template_id}/versions/{version}*",
      "/api/v1/approvals*",
      "/api/v1/agents/{agent_id}/drafts",
      "/api/v1/agents/{agent_id}/publications",
      "/api/v1/agent-drafts*",
      "/api/v1/builder/form",
    ],
    tables: [
      "agent.agent",
      "agent.template_instance",
      "agent.template_version",
      "agent.upgrade_decline",
      "agent.leash_change",
      "agent.supervised_action",
      "agent.action_verdict",
      "agent.supervision_pin",
      "agent.tool_attachment",
      "agent.browser_envelope",
      "gate.suspension",
      "agent.manifest_draft",
      "agent.manifest_revision",
      "agent.manifest_act",
      "agent.learning_pause",
      "ops.agent_run",
    ],
    installation: [],
    gaps: [
      {
        what: "An agent's finished runs are recorded, how each ended and what it spent, and no screen lists them.",
        because:
          "ops.agent_run is written by brain.gate.runtime for operating the runtime and is not the record of what an agent did (brain.ops.agent_run_store.AN_AGENT_RUN_ROW_IS_A_COUNT_AND_NOT_AN_AUDIT_RECORD); the agent's Dashboard draws spend from the usage routes, and a list of runs is a screen nobody has drawn yet.",
      },
      {
        what: "A draft is written, checked and rehearsed on every install, and published only where the install holds a template signing key.",
        because: "brain.agent_builder_routes signs a published draft with the key brain.agent_lifecycle_routes installs with, and no setting holds one yet (brain.ops.starter_store.NO_TEMPLATE_IS_SIGNED_BEFORE_THE_INSTALL_HOLDS_A_KEY_OF_ITS_OWN); publishing says so rather than signing with a weaker key.",
      },
      {
        what: "A rung above Shadow cannot be published from a draft, and a rehearsal does not ask its test questions.",
        because: "brain.builder.agent_drafts.A_RUNG_IS_RAISED_WITH_EVIDENCE_AND_NEVER_BY_A_DRAFT, and no model answers for an agent yet (brain.agent_builder_routes.A_REHEARSAL_RUNS_NO_MODEL_YET).",
      },
      {
        what: "A published template version cannot be installed from the console.",
        because: "brain.agent_lifecycle_routes serves the version and its install, and the Agent templates page has no button that presses it yet; switching on and off, archiving, duplicating and handing on are pressed from the Agents pages.",
      },
    ],
  },
  "Skills and tools": {
    screens: ["/skills", "/skills/:name", "/skills/:name/:view", "/tools", "/tools/:name"],
    routes: [
      "/api/v1/skills",
      "/api/v1/skills/library",
      "/api/v1/skills/imports",
      "/api/v1/skills/procedures",
      "/api/v1/skills/{digest}/versions",
      "/api/v1/skills/{digest}/categories",
      "/api/v1/skills/{digest}/review",
      "/api/v1/skills/{digest}/assignments",
      "/api/v1/skills/{digest}/retirement",
      "/api/v1/skills/{digest}/reinstatement",
      "/api/v1/skills/{digest}/detachments",
      "/api/v1/skills/{digest}/export",
      "/api/v1/skills/{digest}/rehearsals",
      "/api/v1/console/skills/{skill_name}/stats",
      "/api/v1/tools",
      "/api/v1/tools/{name}/switch",
    ],
    tables: [
      "agent.skill",
      "agent.skill_review",
      "agent.skill_assignment",
      "agent.tool_definition",
      "agent.tool_switch",
      "agent.skill_category",
      "agent.skill_invocation",
      "agent.skill_retirement",
      "agent.skill_script",
      "agent.skill_detachment",
      "agent.skill_export",
      "agent.skill_rehearsal",
    ],
    installation: ["INSTALL_ACCEPTANCE_SKILL_SOURCE"],
    gaps: [
      {
        what: "A skill cannot be tried out through an agent in practice mode, with a model answering, before it is assigned.",
        because: "docs/admin-console-architecture.md 4.2 tests a skill through an agent that holds it, rehearsed at SHADOW. POST /api/v1/skills/{digest}/rehearsals rehearses a version's examples for reach only and runs no model (needs-rupash 161); the Profile draws the practice run inert with pages/skills/skillActions.ts' sentence.",
      },
      {
        what: "A skill that declares scripts cannot be added.",
        because: "brain.tools.skills.Skill.digest covers a script's name and not its bytes, so an approval would not cover the code, and brain.tools.run_skill has no runner; brain.console.skill_library refuses one at the door.",
      },
    ],
  },
  "Workflows and automations": {
    screens: ["/agents/:agentId/:tab", "/automations", "/automations/:automationId", "/automations/:automationId/:view"],
    routes: [
      "/api/v1/agents/{agent_id}/automation-templates*",
      "/api/v1/agents/{agent_id}/automations",
      "/api/v1/agents/{agent_id}/automations/{automation_id}/start",
      "/api/v1/agents/{agent_id}/automations/{automation_id}/stop",
      "/api/v1/console/automations*",
      "/api/v1/automations/{automation_id}/*",
    ],
    tables: [
      "agent.automation",
      "agent.automation_run",
      "agent.automation_schedule",
      "agent.automation_change",
      "gate.automation_owner",
    ],
    installation: [],
    gaps: [
      {
        what: "A removed automation cannot be brought back, and installing the same outcome again for the same agent and person is refused.",
        because:
          "A removal is a final row in agent.automation_change (brain.console.automations.A_REMOVAL_IS_FINAL_AND_KEEPS_ITS_HISTORY) and 0055's one-install-per-agent-template-and-person constraint still reads the removed install; the page draws Bring back as not available yet.",
      },
      {
        what: "An automation registered to call the tool route with its own credential (gate.automation_owner) is not listed or adoptable on a screen.",
        because:
          "Nothing on an install writes that registration yet: brain.ops.automation_owner_store.StoredAutomations.put has no caller, so there is no row to list; its adopt is kept for when one exists.",
      },
      {
        what: "Three of the four automation templates cannot be started on any install.",
        because: "brain.ops.automation_run.TASKS says what work_summary, source_freshness and approvals_waiting each still need, and the Automations tab shows that sentence instead of a Start control.",
      },
    ],
  },
  "Connectors and third-party integrations": {
    screens: [
      "/connectors",
      "/connectors/:connector",
      "/connectors/:connector/:view",
      "/channels",
      "/channels/:name",
      "/channels/:name/:view",
      // Where a vendor sends the person back after consenting to a source (M11.8.6).
      "/connector-consent",
      // An API's connector added from its specification, and reviewed by a second person (M11.7.8).
      "/connectors/new-api",
    ],
    routes: [
      "/api/v1/connectors",
      "/api/v1/connectors/{connector}/consent",
      "/api/v1/connectors/consent/callback",
      // A person's own accounts, listed and consented to from My workspace (M11.8.6).
      "/api/v1/me/accounts",
      "/api/v1/me/accounts/{connector}/consent",
      "/api/v1/connectors/{connector}/disconnect",
      "/api/v1/connectors/{connector}/edit",
      "/api/v1/connectors/{connector}/key",
      "/api/v1/connectors/{connector}/probe",
      "/api/v1/connectors/{connector}/accept",
      "/api/v1/connectors/{connector}/steward",
      "/api/v1/console/connectors",
      "/api/v1/console/connectors/{connector}",
      "/api/v1/console/connectors/{connector}/export",
      "/api/v1/console/connectors/{connector}/probe",
      "/api/v1/console/connectors/{connector}/drift",
      "/api/v1/connectors/lark-app",
      "/api/v1/connectors/lark-app/test",
      "/api/v1/connectors/lark-app/switch-off",
      "/api/v1/connectors/lark-app/wiki-spaces",
      "/api/v1/channels*",
      "/api/v1/me/channels*",
      "/api/v1/console/connectors/{connector}/stats",
      "/api/v1/console/channels",
      "/api/v1/console/channels/{name}",
      "/api/v1/console/channels/{name}/stats",
      // An API's connector: submitted, changed and reviewed (M11.7.8).
      "/api/v1/custom-connectors*",
    ],
    tables: [
      "auth.binding_code",
      "ops.channel",
      "ops.channel_delivery",
      "ops.connector_connection",
      "ops.connector_sync",
      // A consent started at a vendor, held until it is answered once (M11.8.6).
      "ops.oauth_consent",
      // A connector for a new API, as submitted, and who reviewed it (M11.7.8).
      "ops.custom_connector",
      "proj.record",
      "proj.record_retired",
      "proj.source_epoch",
      "er.alias",
      "er.canonical",
      "er.identifier",
      "er.link",
    ],
    installation: ["INSTALL_LARK_USES", "INSTALL_LARK_PLATFORM", "INSTALL_LARK_BASE", "INSTALL_LARK_CARD_APPROVALS"],
    gaps: [
      {
        what: "A connected source is read and kept, and no question is answered from what is kept.",
        because:
          "No row tool is registered for a connected source's records: brain.tools.startup.classification_for is keyed on the entity alone and Xero and HubSpot both project contact, which that module records as the limit to change first. brain.ops.connector_admin.WHAT_CONNECTING_A_SOURCE_STARTS says so in the connect confirmation.",
      },
      {
        what: "HubSpot can be connected and is not read.",
        because:
          "brain.ops.limits records no verified call ceiling for it and brain.connectors.throttle.limits_for refuses to invent one; its row carries brain.ops.connector_sync.NO_VERIFIED_CEILING.",
      },
      {
        what: "Google Drive and the Laravel views cannot be connected from a screen.",
        because:
          "Each needs a visibility rule, a department declaration with an answerable person, or a key file the form cannot collect, which brain.ops.connectable.NOT_FROM_THE_CONSOLE says for each. Freshdesk is connected from the screen with its address and the one department that reads it (brain.connectors.freshdesk.ONE_DEPARTMENT_READS_A_CONNECTED_HELPDESK).",
      },
      {
        what: "Connect Lark switches knowledge from Wiki and Base on, and no question is answered from Lark yet.",
        because:
          "The Lark knowledge connector that keeps the minimal index and reads pages and records live is still to be built over the settings Connect Lark writes; brain.ops.lark_connect.KNOWLEDGE_IS_SWITCHED_ON_AND_NOTHING_IS_COPIED says so on the screen.",
      },
    ],
  },
  "API keys, credentials and secrets, held in the vault and never displayed": {
    screens: [
      "/credentials",
      "/credentials/:family/:name",
      "/credentials/:family/:name/:view",
      "/webhooks",
      "/vault",
      "/models",
    ],
    routes: ["/api/v1/credentials*", "/api/v1/vault"],
    tables: ["ops.credential_write", "ops.vault_access"],
    installation: [],
    gaps: [],
  },
  "Knowledge bases, documents and data sources": {
    screens: [
      "/library",
      "/library/:itemId",
      "/library/:itemId/:view",
      "/solutions",
      "/learning",
      "/learning/:view",
      "/memory",
      "/memory/:subject",
      "/memory/:subject/:view",
      "/records",
      "/records/:entity",
      "/classification",
      "/classification/:entity",
      "/classification/:entity/:column",
      "/duplicates",
      "/artifacts",
    ],
    routes: [
      "/api/v1/govern/library",
      "/api/v1/knowledge/uploads*",
      "/api/v1/knowledge/items*",
      "/api/v1/knowledge/tasks*",
      "/api/v1/knowledge/solutions*",
      "/api/v1/knowledge/links",
      "/api/v1/knowledge/documents",
      "/api/v1/knowledge/verifications",
      "/api/v1/govern/learning",
      "/api/v1/govern/learning/undo",
      "/api/v1/govern/learning/settings*",
      "/api/v1/govern/memory",
      "/api/v1/me/memory*",
      "/api/v1/records/{entity}",
      "/api/v1/classifications*",
      "/api/v1/govern/artifacts",
      "/api/v1/records/{entity}/access",
      "/api/v1/resolution/review*",
      "/api/v1/resolution/weights*",
    ],
    tables: [
      "know.item",
      "know.chunk",
      "know.steward_task",
      "know.solution",
      "mem.adaptive",
      "mem.persistent",
      "mem.learning",
      "mem.correction",
      "gate.fast_path_rule",
      "gate.field_policy",
      "agent.artifact",
      "agent.artifact_change",
      "know.classified_table",
      "know.classified_row",
      "er.review_item",
      "er.merge",
      "er.unmerge",
      "er.observation",
      "er.blocked_value",
    ],
    installation: [
      "INSTALL_VECTOR_STORE",
      "INSTALL_EMBEDDING_REVISION",
      "INSTALL_KNOWLEDGE_SCANNER",
      "INSTALL_CLAMAV_ADDRESS",
    ],
    gaps: [
      {
        what: "Which scanner checks an uploaded file, the structural check or ClamAV added to it, is an installation value and not a control; the Knowledge page says which one checks a file.",
        because:
          "Whether a server can hold an antivirus's signature database is the owner's capacity decision, so brain.knowledge.scanners ships the structural check and reads INSTALL_KNOWLEDGE_SCANNER at every scan, which tests/unit/test_scanners.py holds.",
      },
      {
        what: "A data source cannot be added from the console after setup; a document can, on the Knowledge page.",
        leaf: "M42.5.9",
      },
      {
        what: "A memory cannot be edited from a screen, and a tier-two rule cannot be promoted nor a tier-three change decided.",
        because:
          "brain.ops.memory_store writes an edit and no route offers one: the control belongs on a person's own memory tab, and the Memory screen says edit_is_not_writable. Nothing records agreement or a decision, which the Learning screen says in place of Promote and Decide.",
      },
      {
        what: "A built-in classification's column is reviewed and not applied; an uploaded table's column is marked and applied.",
        because:
          "The shipped price list is a constant compiled into the API's process and changes with a release; brain.classification_routes applies a mark only to a table stored in know.classified_table, which tests/unit/test_classification_routes.py holds by the routes it mounts.",
      },
      {
        what: "A price list uploaded as a document on the Knowledge page is not yet offered conversion to classified rows; it is uploaded on the Classification screen.",
        leaf: "M7.7.3",
      },
      {
        what: "A document cannot be archived from the console; Archive is drawn inert with its reason.",
        because:
          "know.item's policy admits only live rows, so the update moving one to archived is refused under it as a supersession was before 0120 wrote know.supersede_item; archiving needs its own write past the policy, which is a migration.",
      },
      {
        what: "The knowledge inventory cannot be exported; Export inventory is drawn inert with its reason.",
        because:
          "An export is recorded in ops.data_export, whose data sets are a closed list the table checks (brain.tables.data_export.ExportDataSet), so a knowledge inventory is a new member and a migration widening the check; an unrecorded export of titles is not offered meanwhile.",
      },
    ],
  },
  "File and object storage": {
    screens: ["/storage"],
    routes: ["/api/v1/storage"],
    tables: [],
    installation: ["INSTALL_OBJECT_STORE_URL", "INSTALL_OBJECT_STORE_PREFIX", "INSTALL_OBJECT_STORE_BACKEND"],
    gaps: [{ what: "A bucket's retention and the store's address are read and never changed.", leaf: "M27.8.15" }],
  },
  "Prompts and system instructions": {
    screens: ["/prompts"],
    routes: ["/api/v1/govern/prompts*"],
    tables: [],
    installation: [],
    gaps: [],
  },
  "Feature and module enablement": {
    screens: ["/features"],
    routes: ["/api/v1/install/features*"],
    tables: ["ops.plugin_install", "ops.plugin_version"],
    installation: [],
    gaps: [
      {
        what: "A plugin cannot be installed or enabled.",
        because: "Nothing loads a plugin yet: the Features screen says plugins_have_no_loader, and ops.plugin_install has no writer a route calls.",
      },
    ],
  },
  "Notifications and email": {
    screens: ["/subscribers", "/notifications"],
    routes: ["/api/v1/govern/subscribers", "/api/v1/notifications*"],
    tables: ["ops.outbox_event", "ops.outbox_delivery"],
    installation: ["INSTALL_SENDER_ADDRESS"],
    gaps: [
      {
        what: "No notice is sent to a person yet.",
        because:
          "Every notice but the re-verification request is composed and called by nothing, and that one reaches webhook subscribers; the Notifications screen says so per notice from brain.ops.notices, and a sender added for any of them asks its switch.",
      },
      {
        what: "INSTALL_SENDER_ADDRESS is read by nothing that sends.",
        because: "The relay's sender address is saved on the Notifications screen, and the install value is only shown on the Install screen.",
      },
    ],
  },
  Webhooks: {
    screens: ["/webhooks", "/webhooks/:id", "/webhooks/:id/:view"],
    routes: ["/api/v1/webhooks*"],
    tables: ["ops.webhook_subscriber", "ops.webhook_change"],
    installation: [],
    gaps: [
      {
        what: "No vendor platform's webhook is received, only the company's own signed webhook.",
        because:
          "Only brain.channels.webhook has a wire in this release, and the WhatsApp and Lark checks are not written; each channel's About view says whether its check is written, from brain.ops.inbound_webhooks.INBOUND as the Webhooks route serves it.",
      },
    ],
  },
  "Scheduled jobs and background work": {
    screens: ["/jobs", "/jobs/:name", "/jobs/:name/:view", "/runs"],
    routes: ["/api/v1/jobs*", "/api/v1/operate/runs", "/api/v1/operations/interrupted"],
    tables: ["ops.control_run", "ops.operation", "ops.acceptance_result"],
    installation: [],
    gaps: [
      {
        what: "A run in progress cannot be stopped.",
        because: "The route says no_run_can_be_stopped: a control runs to its end inside the worker's tick and there is nothing to signal.",
      },
      {
        what: "The interrupted actions a stopped worker left unconfirmed are served and no screen draws them or resolves one yet.",
        leaf: "M27.15.46",
      },
    ],
  },
  "Usage, activity and system statistics": {
    screens: ["/usage", "/adoption", "/spend", "/questions", "/quality", "/service-levels", "/me"],
    routes: ["/api/v1/report/*", "/api/v1/me/workspace"],
    tables: [
      "ops.question_asked",
      "ops.question_gap",
      "ops.report_refresh",
      "ops.spend_actual",
      "obs.request_telemetry",
    ],
    installation: [],
    gaps: [],
  },
  "Logs and errors": {
    screens: ["/errors", "/logs"],
    routes: ["/api/v1/errors", "/api/v1/logs*"],
    tables: ["obs.application_log"],
    installation: [],
    gaps: [
      {
        what: "The background worker's own output and every debug line are not kept, and information lines are a sample.",
        because: "The Logs screen says worker_output_is_not_kept, debug_is_not_kept and info_is_a_sample: the worker prints to its container rather than logging through structlog, and brain.ops.log_capture keeps warnings and above and bounds the rest.",
      },
    ],
  },
  "The audit trail: who changed what, and when": {
    screens: [
      "/audit",
      "/audit/verify",
      "/audit/trace",
      "/audit/trace/:traceId",
      "/audit/subject/:kind/:id",
      "/audit/subject/:kind/:id/:view",
      "/requirement-checks",
    ],
    routes: ["/api/v1/audit*", "/api/v1/requirements/checks", "/api/v1/traces*"],
    tables: [
      "obs.audit_entry",
      "ops.sensitive_read",
      "ops.requirement_check",
      "agent.browser_session",
      "obs.trace_step",
      "obs.trace_read",
    ],
    installation: [],
    gaps: [],
  },
  "System health and the state of every service": {
    screens: ["/", "/models", "/runs"],
    routes: ["/api/v1/console/overview/figures", "/api/v1/console/overview", "/api/v1/halts*"],
    tables: ["ops.halt"],
    installation: [],
    gaps: [
      {
        what: "The install cannot be stopped or resumed from the console yet: GET, POST /api/v1/halts and POST /api/v1/halts/resume stop and resume through brain.ops.halt_store, and no Stop screen or header control calls them.",
        leaf: "M27.12.4",
      },
    ],
  },
  "Backup and recovery": {
    screens: [
      "/recovery",
      "/retention",
      "/retention/:view",
      "/retention/holds/:holdId",
      "/retention/erasures/:requestId",
      "/compliance",
      "/compliance/:view",
      "/compliance/breaches/:caseId",
      "/referrals",
    ],
    routes: [
      "/api/v1/install/recovery",
      "/api/v1/govern/retention*",
      "/api/v1/govern/legal-holds*",
      "/api/v1/govern/erasures",
      "/api/v1/govern/compliance*",
      "/api/v1/me/referrals*",
      "/api/v1/govern/escalation-routes*",
    ],
    tables: [
      "ops.retention_release",
      "ops.retention_report",
      "obs.legal_hold",
      "ops.erasure_request",
      "ops.breach_case",
      "ops.sensitive_referral",
      "gate.escalation",
    ],
    installation: [],
    gaps: [{ what: "A recovery drill cannot be started, and a restore cannot be verified, from the console.", leaf: "M30.3.9" }],
  },
  "Import and export": {
    screens: ["/import-export"],
    routes: ["/api/v1/data-transfer*"],
    tables: ["ops.data_export"],
    installation: [],
    gaps: [{ what: "Nothing can be imported, and the audit trail is the only export.", leaf: "M27.8.16" }],
  },
  "Version, build and deployment information": {
    screens: ["/updates", "/install"],
    routes: ["/api/v1/install/updates"],
    tables: ["ops.deployment_record"],
    installation: [],
    gaps: [],
  },
};

/** Screens, routes and tables that no administrator manages, and why each is not a gap. */
export const NOT_ADMINISTERED: Readonly<Record<string, string>> = {
  "/ask": "Asking a question is what the console is for a person, not something an administrator manages.",
  "/auth/callback": "The end of a sign-in, drawn by the session module rather than by any screen.",
  "/signed-out": "The page a person lands on after signing out, which asks nothing and manages nothing.",
  "/*": "The page drawn for an address the console does not have, which manages nothing.",
  "POST /api/v1/answer": "The answer lane behind Ask, which writes no row an administrator manages.",
  "POST /api/v1/answer/mark":
    "A person marking an answer they were given helpful or not, one bit against its reference, which no administrator manages and nothing that answers reads.",
  "mem.mark":
    "The marks people put on their own answers, counted and read by nothing that decides an answer; no administrator manages a person's mark.",
  "POST /api/v1/widget/sessions":
    "Where a website visitor's browser asks for a session, which holds nothing and writes no row an administrator manages; the sites it serves are the install's widget origins setting.",
  "POST /api/v1/widget/questions":
    "Where a website visitor's question is answered from knowledge marked public, which writes nothing; what is public is decided on each document's page, by the marking route.",
  "POST /api/v1/automation/tool-call":
    "Called by a running automation with its owner's reach, not by a person at a screen; installing the automation is the console's part.",
  "chat.conversation":
    "What a person asked and was answered belongs to them: kept by brain.chat.thread_store, listed, searched and reopened on Ask for that person alone, and never managed by anybody else.",
  "chat.message": "The same as chat.conversation: a person's own words, reported on and never managed.",
  "GET /api/v1/threads":
    "A person's own conversations on Ask, for them alone and never anybody else's; nothing in it for an administrator to manage.",
  "GET /api/v1/threads/search":
    "A search of a person's own questions on Ask, for them alone; nothing in it for an administrator to manage.",
  "GET /api/v1/threads/{thread_id}":
    "One of a person's own conversations reopened on Ask at the reach they hold now; nothing in it for an administrator to manage.",
  "POST /api/v1/threads/attachments":
    "A person naming a document of their own on their own conversation, from Ask; a note in their thread that lets an answer read it at their reach, and nothing in it for an administrator to manage.",
  "ops.retrieval_event":
    "What a person was answered from, as the learning signal reads it: which retrievers ran, how many passages were shown and where a citation was followed, with no document, question or person; written by the answer route and the cited page, and nothing in it for an administrator to manage.",
  "GET /api/v1/retrievals/signal":
    "The ranking's learning signal, rates over recent retrievals for a knowledge administrator tuning search; it manages nothing, and no screen draws it yet.",
  "POST /api/v1/retrievals/{event_id}/uses":
    "The place of a passage a person followed from an answer, sent by the cited document page for the learning signal; a person's own act, not something an administrator manages.",
  "POST /api/v1/threads/{thread_id}/corrections":
    "A person marking the latest answer in their own conversation wrong, from Ask; a note in their thread the learning signal counts, and nothing in it for an administrator to manage.",
  "gate.channel_event":
    "The dedupe key of each inbound channel message, claimed once by brain.gate.event_store.first_delivery and read by nothing else; there is nothing in it for anybody to manage.",
  "/ask/documents/:documentId":
    "The document a citation on Ask opens, read at the asker's own reach; a person checking an answer, not an administrator managing anything.",
  "GET /api/v1/knowledge/documents/{document_id}":
    "One document's passages for the page a citation opens, read at the caller's reach through the handler and policy the answer used; it writes nothing and manages nothing.",
};

// ---------------------------------------------------------------------- writes and proofs

/**
 * **Each module holds its own writes, and this file collects them.** The writes a module's screens
 * send, the reads they make only once somebody acts, and the proofs of each write route live in
 * `consoleAudit/<module>.ts`, named for the module's kit directory under `src/pages` (for a page not
 * yet moved to the kit, the first segment of its address), and an eager `import.meta.glob` reads
 * every such file. Until 2026-09-29 the three were one object each
 * here, so every console change that sent a write appended to the same lines as every other, and
 * two of them conflicted whatever they built. A write route two modules reach keeps its proofs in
 * one of them. A key two files both hold is refused as they are read, which the one object literal
 * used to refuse at compile time, because the later file would otherwise replace the earlier's
 * claim without a word.
 */
interface ClaimFile {
  readonly READ_AFTER_AN_ACTION?: Readonly<Record<string, ReadAfterAnAction>>;
  readonly WRITE_ROUTES?: Readonly<Record<string, readonly WriteRoute[]>>;
  readonly PROOFS?: Readonly<Record<string, Proofs>>;
}

const CLAIM_FILES = import.meta.glob<ClaimFile>("./consoleAudit/*.ts", { eager: true });

/** One export of every module's file, merged, refusing a key two files both hold. */
function collected<T>(pick: (file: ClaimFile) => Readonly<Record<string, T>> | undefined): Readonly<Record<string, T>> {
  const merged: Record<string, T> = {};
  const heldBy = new Map<string, string>();
  for (const path of Object.keys(CLAIM_FILES).sort()) {
    const file = CLAIM_FILES[path];
    for (const [key, value] of Object.entries((file === undefined ? undefined : pick(file)) ?? {})) {
      const earlier = heldBy.get(key);
      if (earlier !== undefined) {
        throw new Error(`${key} is held by both ${earlier} and ${path}; one claim has one home.`);
      }
      heldBy.set(key, path);
      merged[key] = value;
    }
  }
  return merged;
}

/**
 * Reads a screen makes only once a person has done something, which opening the page does not
 * show: a subject's history, a staff source's trial run and an automation's preview.
 */
export const READ_AFTER_AN_ACTION: Readonly<Record<string, ReadAfterAnAction>> = collected((file) => file.READ_AFTER_AN_ACTION);

/** Every write a screen sends, by its key in `support/writes.ts`, with every route it can reach. */
export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = collected((file) => file.WRITE_ROUTES);

/** Every write route a screen sends, followed to the system. */
export const PROOFS: Readonly<Record<string, Proofs>> = collected((file) => file.PROOFS);

// ---------------------------------------------------------------------------------- matching

/** Whether a claim in an area names a route. */
export function claims(claim: string, route: string): boolean {
  if (!route.includes(" ")) {
    return false;
  }
  const [method, path] = route.split(" ") as [string, string];
  const hasMethod = /^[A-Z]+ /.test(claim);
  const claimMethod = hasMethod ? claim.split(" ")[0] : null;
  const claimPath = hasMethod ? claim.slice(claim.indexOf(" ") + 1) : claim;
  if (claimMethod !== null && claimMethod !== method) {
    return false;
  }
  return claimPath.endsWith("*") ? path.startsWith(claimPath.slice(0, -1)) : path === claimPath;
}

// ---------------------------------------------------------------------------------- rendering

export interface Measured {
  readonly routes: readonly string[];
  readonly tables: readonly string[];
  readonly installation: readonly string[];
  readonly screens: readonly string[];
  /** Screens that asked each GET route when opened. */
  readonly readBy: Readonly<Record<string, readonly string[]>>;
  /** Screens whose calls send each write route. */
  readonly writtenBy: Readonly<Record<string, readonly string[]>>;
  /** Whether each named proof test needs a live database, as declared and checked. */
  readonly writeCount: number;
}

function code(text: string): string {
  return `\`${text}\``;
}

function proofCell(proof: Proof): string {
  if ("test" in proof) {
    const [file, name] = proof.test.split("::") as [string, string];
    return `${code(name)} in ${code(file)}${proof.database ? " (database, in CI)" : ""}`;
  }
  if ("none" in proof) {
    return `**None.** ${proof.none}${proof.leaf ? ` Leaf ${code(proof.leaf)}.` : ""}`;
  }
  return `Not applicable: ${proof.notApplicable}`;
}

function cellSafe(text: string): string {
  return text.replace(/\|/g, "/");
}

/** The directory the audit is written to, relative to the repository. */
export const AUDIT_DIRECTORY = "docs/console-audit";

/** The file every other file of the audit is read after, and the one that names them. */
export const AUDIT_INDEX = "README.md";

/** The file holding what is not administered here, which sorts after every area's file. */
export const NOT_ADMINISTERED_FILE = "not-administered.md";

/**
 * An area's file name: its place in the standard, then its words. The number is the standard's
 * order, so the served page reads in that order, and the words are there so a diff says which area
 * changed without opening the file.
 */
export function areaFile(name: string, at: number): string {
  const slug = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .split("-")
    .slice(0, 6)
    .join("-");
  return `${String(at + 1).padStart(2, "0")}-${slug}.md`;
}

/** Whether a write route's three proofs are each proved or not applicable. */
function provedWhole(route: string): boolean {
  const one = PROOFS[route];
  return one !== undefined && [one.row, one.audit, one.behaviour].every((proof) => !("none" in proof));
}

/** The table of writes, for the routes given, in route order. */
function writeTable(routes: readonly string[], measured: Measured): string[] {
  const lines = ["| Write | Called by | Row | Audit entry | Behaviour |", "| --- | --- | --- | --- | --- |"];
  for (const route of [...routes].sort()) {
    const one = PROOFS[route];
    if (one === undefined) {
      continue;
    }
    const callers = (measured.writtenBy[route] ?? []).map(code).join(", ");
    lines.push(
      `| ${code(route)} | ${callers || "**no screen**"} | ${cellSafe(proofCell(one.row))} | ${cellSafe(proofCell(one.audit))} | ${cellSafe(proofCell(one.behaviour))} |`,
    );
  }
  return lines;
}

/**
 * The audit, deterministically, as one file per area plus an index and the list of what is not
 * administered here, keyed by file name inside `AUDIT_DIRECTORY`.
 *
 * **Why files and not one document.** Every console change moves some figure in the audit, and
 * until 2026-09-28 every figure was in one file: the totals at its head moved with every route,
 * page and write anybody added, so any two console pull requests changed the same lines of the
 * same file and the second always conflicted with the first. Split by area, a change touches the
 * file of the area it belongs to, and the index carries no figure that moves with a change. What
 * is checked is unchanged: every table, route, value and address is still claimed by an area or
 * excused, every file is compared with what this renders, and a file nothing renders is refused.
 * Rejected: generating the document in CI and serving it from the build, because the page is
 * served by the API from the repository (`/build/console-audit`), and a document that exists only
 * in a build is one the owner cannot read on the commit he is looking at.
 */
export function renderAudit(measured: Measured): Record<string, string> {
  const areaNames = Object.keys(AREAS);
  const files: Record<string, string> = {};
  const index: string[] = [];

  index.push("# The console audit");
  index.push("");
  index.push(
    "What an administrator would need to manage, read out of the schema, the routes and the installation values, compared with what the console serves, screen by screen, with every gap either linked to its open leaf or recorded with its reason. It is the audit `docs/admin-console.md` asks for before the console is called done.",
  );
  index.push("");
  index.push(
    "**These files are generated and must not be edited by hand.** `console/tests/console-audit.test.ts` renders them from `console/tests/support/consoleAudit.ts` and fails when any file here differs, or when a file here is one it did not render. To regenerate them after a change, run `npm run api:generate` and then `WRITE_CONSOLE_AUDIT=1 npx vitest run tests/console-audit.test.ts` in `console/`. The page at `/build/console-audit` is this file followed by every other file here in name order.",
  );
  index.push("");
  index.push(
    "**One file per area, so two changes to the console meet only when they touch the same area.** Each area's file carries its own figures, and this index carries none that a change could move.",
  );
  index.push("");
  index.push("## What was measured");
  index.push("");
  index.push("- The areas: the bullets of `docs/admin-console.md`, in its order, one file each.");
  index.push("- The tables, from `brain.db.Base.metadata`.");
  index.push("- The installation values, from `brain.install.INSTALLATION`.");
  index.push("- The routes under `/api/v1` and `/setup`, from the API's internal document.");
  index.push("- The console addresses, from every page's route file, `console/src/pages/*.route.tsx`, and `console/src/App.tsx`.");
  index.push("- The calls in the console that send a write, from `console/tests/support/writes.ts`, each followed to its routes.");
  index.push("");
  index.push("## The rules every screen is held to");
  index.push("");
  index.push(
    "- **Loading, empty, unreachable and failed** are four different sentences on every registered address: `console/tests/screen-states.test.tsx`, with the addresses excused and why in `console/tests/support/screenStateRules.tsx`.",
  );
  index.push(
    "- **A destructive write is confirmed**, and the confirmation names what and says what will happen: `console/tests/destructive-confirmed.test.ts`, with the writes that are not destructive and why.",
  );
  index.push(
    "- **A form that writes is judged before it sends**, and a blank one says what to fill in: `console/tests/validated-before-write.test.tsx`.",
  );
  index.push(
    "- **Long lists page, search, filter and sort** through one convention, `brain.listing`, over the rows the reader may see, and a filter offers only values on rows drawn: `console/tests/long-lists.test.tsx` measures every long list against its route and records what each does not offer with its reason. Ending several sessions and deciding several review holdings are bulk acts, each item decided by the single act's own check.",
  );
  index.push(
    "- **Every write the console sends is followed to the system** (leaf `M27.8.17`): to the row it writes, to the audit entry it leaves, and to the behaviour it changes, each a named Python test or a reason there is none. Each area's file lists its own writes. A test marked database runs against a scratch Postgres, which CI provides.",
  );
  index.push("");
  index.push("## Area by area");
  index.push("");
  areaNames.forEach((name, at) => {
    index.push(`- [${name}](${areaFile(name, at)})`);
  });
  index.push(`- [Not administered here](${NOT_ADMINISTERED_FILE})`);
  index.push("");
  files[AUDIT_INDEX] = index.join("\n");

  const claimedWrites = new Set<string>();
  areaNames.forEach((name, at) => {
    const area = AREAS[name];
    if (area === undefined) {
      return;
    }
    const lines: string[] = [];
    const routes = measured.routes.filter((route) => area.routes.some((claim) => claims(claim, route)));
    const unreached = routes.filter(
      (route) => (measured.readBy[route] ?? []).length === 0 && (measured.writtenBy[route] ?? []).length === 0,
    );
    const writes = Object.keys(PROOFS).filter((route) => area.routes.some((claim) => claims(claim, route)));
    writes.forEach((route) => claimedWrites.add(route));
    lines.push(`### ${name}`);
    lines.push("");
    lines.push(`- **Screens:** ${area.screens.length === 0 ? "none" : area.screens.map(code).join(", ")}`);
    lines.push(`- **Tables:** ${area.tables.length === 0 ? "none" : area.tables.map(code).join(", ")}`);
    lines.push(`- **Installation values:** ${area.installation.length === 0 ? "none" : area.installation.map(code).join(", ")}`);
    lines.push(
      `- **Measured here:** ${String(routes.length)} routes, ${String(unreached.length)} called by no screen; ${String(writes.length)} write routes, ${String(writes.filter(provedWhole).length)} with all three proofs; ${String(area.gaps.length)} gaps.`,
    );
    lines.push("");
    if (routes.length > 0) {
      lines.push("| Route | Called by |");
      lines.push("| --- | --- |");
      for (const route of routes) {
        const callers = [...new Set([...(measured.readBy[route] ?? []), ...(measured.writtenBy[route] ?? [])])].sort();
        lines.push(`| ${code(route)} | ${callers.length === 0 ? "**no screen**" : callers.map(code).join(", ")} |`);
      }
      lines.push("");
    }
    if (area.gaps.length === 0) {
      lines.push("No gap recorded.");
    } else {
      for (const gap of area.gaps) {
        lines.push(`- **Gap.** ${gap.what} ${gap.leaf ? `Open leaf ${code(gap.leaf)}.` : `Recorded: ${gap.because ?? ""}`}`);
      }
    }
    lines.push("");
    if (writes.length > 0) {
      lines.push("**Every write to this area, followed to the system.**");
      lines.push("");
      lines.push(...writeTable(writes, measured));
      lines.push("");
    }
    files[areaFile(name, at)] = lines.join("\n");
  });

  const excused: string[] = [];
  excused.push("## Not administered here");
  excused.push("");
  excused.push("| What | Why it is not a gap |");
  excused.push("| --- | --- |");
  for (const [what, why] of Object.entries(NOT_ADMINISTERED).sort(([a], [b]) => a.localeCompare(b))) {
    excused.push(`| ${code(what)} | ${cellSafe(why)} |`);
  }
  excused.push("");
  const unclaimed = Object.keys(PROOFS).filter((route) => !claimedWrites.has(route));
  if (unclaimed.length > 0) {
    excused.push("**Every write to a route no area claims, followed to the system.**");
    excused.push("");
    excused.push(...writeTable(unclaimed, measured));
    excused.push("");
  }
  files[NOT_ADMINISTERED_FILE] = excused.join("\n");
  return files;
}
