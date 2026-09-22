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
 * the routes from the API's internal document, and the screens from the route table.
 *
 * **What is typed is the judgement, and every judgement is checked for coverage.** Which area a
 * table, a route, a value or a screen belongs to is not something the code can say, so it is written
 * here. `tests/console-audit.test.ts` refuses a table, a route, a value or a screen that no area
 * claims and nothing excuses, an excuse with no reason, a gap naming a leaf the work breakdown does
 * not have, and a document that differs from what this module renders.
 *
 * **Which screen reaches which route is observed, not claimed.** A read is the path a page asked
 * for when `support/pageCases.ts` opened it, which the state tests prove is every path it asks for.
 * A write is `support/writes.ts`' list of every call that sends one, each mapped here to its route
 * through the function that spells the address, and the function is called to prove it.
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
import { ANSWER_API_PATH } from "../../src/pages/askQuery";
import { ACCESS_REQUESTS_API_PATH } from "../../src/pages/accessRequestsQuery";
import { automationStartApiPath, automationStopApiPath } from "../../src/pages/agentAutomationsQuery";
import { STEWARD_API_PATH } from "../../src/pages/dataStewardQuery";
import { automationInstallApiPath, automationPreviewApiPath } from "../../src/pages/automationGalleryQuery";
import { approvalDecisionApiPath } from "../../src/pages/approvalsQuery";
import { historyApiPath, VERIFICATION_API_PATH } from "../../src/pages/auditQuery";
import { CHECKS_API_PATH } from "../../src/pages/requirementChecksQuery";
import { UNDO_API_PATH } from "../../src/pages/learningQuery";
import { reviewApiPath } from "../../src/pages/classificationQuery";
import { assignPath, reviewPath, SKILLS_API_PATH } from "../../src/pages/skillsQuery";
import { EXPORTS_API_PATH } from "../../src/pages/dataTransferQuery";
import { switchPath } from "../../src/pages/featuresQuery";
import { savePath } from "../../src/pages/settingsQuery";
import {
  DISABLE_API_PATH,
  ELEVATION_REQUESTS_API_PATH,
  ENABLE_API_PATH,
  LEAD_API_PATH,
  MEMBERSHIP_API_PATH,
  REVIEW_DECISIONS_API_PATH,
  REVIEW_DECISION_API_PATH,
  elevationDecisionApiPath,
} from "../../src/pages/governPeopleQuery";
import {
  APPOINTMENT_API_PATH,
  DEPUTY_API_PATH,
  GRANTS_API_PATH,
  GROUP_RULES_API_PATH,
  GROUP_RULE_RETIREMENT_API_PATH,
  PACK_ASSIGNMENT_API_PATH,
  REMOVAL_API_PATH,
  ROLE_REMOVAL_API_PATH,
} from "../../src/pages/governQuery";
import { actionPath } from "../../src/pages/jobsQuery";
import { rungApiPath } from "../../src/pages/matrixQuery";
import { ADD_RUNG_API_PATH, GOLDEN_API_PATH, retireGoldenApiPath } from "../../src/pages/matrixGateQuery";
import {
  ADD_PROVIDER_API_PATH,
  REGISTER_API_PATH as PROVIDER_REGISTER_API_PATH,
  retireProviderApiPath,
  termsApiPath,
} from "../../src/pages/providerRegisterQuery";
import { modelPinApiPath } from "../../src/pages/agentModelPinQuery";
import { providerCheckApiPath, providerSwitchApiPath } from "../../src/pages/modelsQuery";
import {
  RESIDENCY_API_PATH,
  residencyRetireApiPath,
  tierApiPath,
  tierResetApiPath,
} from "../../src/pages/routingSettingsQuery";
import { editPath, giveBackPath } from "../../src/pages/promptsQuery";
import {
  ERASURES_API_PATH,
  HOLD_API_PATH,
  LIFT_API_PATH,
  RELEASE_API_PATH,
  WITHDRAWAL_API_PATH,
} from "../../src/pages/retentionQuery";
import { END_SESSIONS_API_PATH, END_SESSION_API_PATH } from "../../src/pages/sessionsQuery";
import { LINK_API_PATH, UNLINK_API_PATH } from "../../src/pages/signInLinksQuery";
import {
  APPLY_FIRST_SYNC_API_PATH,
  CONNECT_API_PATH,
  CONNECTION_TEST_API_PATH,
  CREDENTIAL_API_PATH,
  FIRST_SYNC_API_PATH,
  TRIAL_API_PATH,
  transferApiPath,
} from "../../src/pages/staffSourcesQuery";
import { CONNECTORS_API_PATH, disconnectApiPath } from "../../src/pages/connectorsQuery";
import { LARK_API_PATH, LARK_TEST_API_PATH } from "../../src/pages/larkConnectQuery";
import { credentialPath } from "../../src/components/ProviderKeyForm";
import { REGISTER_API_PATH, secretApiPath, switchOffApiPath } from "../../src/pages/webhooksQuery";
import {
  PASSWORD_API_PATH as RELAY_PASSWORD_API_PATH,
  RELAY_API_PATH,
  TRIAL_API_PATH as RELAY_TRIAL_API_PATH,
  noticeApiPath,
} from "../../src/pages/notificationsQuery";
import {
  REGISTRATION_PATH as STAFF_LIST_REGISTRATION_PATH,
  SIGN_IN_PATH as STAFF_LIST_SIGN_IN_PATH,
  TRIAL_PATH as STAFF_LIST_TRIAL_PATH,
} from "../../src/setup/staffList";
import { APPOINTMENT_PATH, FINISH_PATH } from "../../src/setup/wizard";
import { BREACHES_API_PATH, breachStepApiPath, topicApiPath } from "../../src/pages/complianceQuery";
import { handledApiPath } from "../../src/pages/referralsQuery";
import { CONSOLE_ROOT, readRepoFile } from "./repo";

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
  for (const route of Object.keys(document["paths"] as Record<string, unknown>)) {
    if (new RegExp(`^${route.replace(/\{[^}]+\}/g, "[^/]+")}$`).test(path)) {
      return route;
    }
  }
  return null;
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
  /** Addresses in `App.tsx` that serve it. */
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
    screens: ["/", "/people", "/people/:subject", "/roles", "/capabilities", "/scopes", "/access_review", "/elevation", "/sessions", "/sign-in-links", "/staff_sources", "/access-requests"],
    routes: [
      "/api/v1/me",
      "/api/v1/console/navigation",
      "/api/v1/govern/people",
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
      "/api/v1/access-requests",
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
      "gate.role_grant",
      "auth.group_role_rule",
      "gate.break_glass_notice",
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
    ],
    gaps: [
      {
        what: "A grant written from People and grants cannot be given an expiry, and the screen says so beside the form.",
        because:
          "Buildable today: POST /api/v1/govern/grants takes not_after and the form's proposal schema has no field for it. It is left to the change reworking member grants, which is in progress beside this one and owns that form.",
      },
      {
        what: "A pack cannot be assigned or withdrawn, and a capability that arrived through a pack cannot be removed.",
        because: "No route writes gate.capability_pack_assignment. brain.govern_routes.remove_grant refuses a pack's capability in the ordinary words, because withdrawing it removes every other capability in the pack.",
      },
      {
        what: "Roles, capabilities and scopes are read and never changed.",
        because: "No route writes gate.scope or the role and capability registries; they are declared by the product and by migrations.",
      },
      {
        what: "A break-glass notice to the standing Super Admins is shown on their Elevation screen and is not sent by email or chat, and nobody is told when somebody only asks.",
        because:
          "Nothing records a Super Admin's email address or chat identity for a notice to be sent to: auth.principal holds no address and principal_identity holds digests. The notice is written in the approval's transaction to gate.break_glass_notice and read by its recipient; a request is not an elevation until it is approved.",
      },
      { what: "The identity provider and the staff source cannot be changed after setup.", because: ONCE_BY_THE_WIZARD },
      {
        what: "A service account and its keys are registered, issued, revoked and retired through /api/v1/govern/service-accounts, and no screen calls it.",
        leaf: "M27.11.5",
      },
    ],
  },
  "Departments, teams and client configuration": {
    screens: ["/departments", "/department"],
    routes: ["/api/v1/govern/departments*"],
    tables: ["gate.department", "gate.team", "gate.team_membership", "gate.department_lead"],
    installation: ["INSTALL_COMPANY_NAME", "INSTALL_PRODUCT_NAME", "INSTALL_LOGO_URL", "INSTALL_ACCENT_COLOUR"],
    gaps: [
      {
        what: "A department, a team or a scope cannot yet be created, renamed or retired from this screen.",
        because: "brain.govern_people_routes serves the eight writes, audited by 0086's triggers, and Departments.tsx does not call them yet; the screen places people in the teams that are there and leads the departments that are there.",
      },
      {
        what: "Nothing applies the staff list's teams and leads on a schedule.",
        because: "brain.identity.organisation_sync plans them and brain.identity.organisation_store applies a plan, and no job runs either. The nightly staff sync (brain.ops.staff_sync_run, since 2026-09-21) applies the roster's people and marks leavers, and not its teams or leads.",
      },
    ],
  },
  "System settings and application configuration": {
    screens: ["/install", "/settings", "/limits", "/connections", "/first-run", "/first-run/staff-list"],
    routes: ["/api/v1/install", "/api/v1/install/settings*", "/api/v1/install/limits", "/api/v1/install/capacity", "/setup/*"],
    tables: ["ops.setting", "ops.budget_version"],
    installation: ["INSTALL_LOCALES", "INSTALL_CURRENCY", "INSTALL_TIME_ZONE"],
    gaps: [
      { what: "Languages, currency and time zone cannot be changed after setup.", because: ONCE_BY_THE_WIZARD },
      {
        what: "Limits and budgets are read and never changed.",
        because: "No route writes ops.budget_version or a ceiling; a limit is a release today.",
      },
    ],
  },
  "AI providers, models and the routing between them": {
    screens: ["/models", "/routing", "/routing/:rungId"],
    routes: [
      "/api/v1/operate/models",
      "/api/v1/models/providers*",
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
      {
        what: "A provider's terms and an added provider's retirement are logged and not on the audit ledger: the ledger's action list gains no provider entry in this release.",
        leaf: "M5.6.4",
      },
      { what: "A provider key cannot be written or replaced from a screen after setup.", leaf: "M27.8.8" },
      { what: "The model profile and endpoint cannot be changed after setup.", because: ONCE_BY_THE_WIZARD },
    ],
  },
  "Agents and their configuration, including templates": {
    screens: ["/agents", "/agents/:agentId", "/agents/:agentId/:tab", "/agent-templates", "/approvals", "/approvals/:suspensionId"],
    routes: [
      "/api/v1/agents",
      "/api/v1/agents/{agent_id}/workspace",
      "/api/v1/agents/{agent_id}/about",
      "/api/v1/agents/{agent_id}/model-pin",
      "/api/v1/agent-templates",
      "/api/v1/approvals*",
    ],
    tables: [
      "agent.agent",
      "agent.template_instance",
      "agent.template_version",
      "agent.upgrade_decline",
      "agent.browser_envelope",
      "gate.suspension",
    ],
    installation: [],
    gaps: [
      {
        what: "An agent cannot be created, and its manifest, leash and procedure cannot be edited.",
        because: "components/ManifestForm.tsx and components/ProcedureCanvas.tsx are built and tested and rendered by no registered page, and no route writes agent.agent or a template version from the console.",
      },
    ],
  },
  "Skills and tools": {
    screens: ["/skills", "/skills/:name"],
    routes: ["/api/v1/skills", "/api/v1/skills/{digest}/review", "/api/v1/skills/{digest}/assignments"],
    tables: ["agent.skill", "agent.skill_review", "agent.skill_assignment"],
    installation: [],
    gaps: [
      {
        what: "A skill cannot be fetched from a repository or a link, only pasted or uploaded.",
        because: "brain.tools.fetch can fetch and check a source, and agent.skill admits only an upload; nothing on an install is given the network reach a fetch needs.",
      },
      {
        what: "A skill cannot be removed from an agent from the console, only replaced by another version of it.",
        because: "brain.console.agent_tabs.detach decides a removal and no route performs one; brain.skill_routes assigns and replaces.",
      },
      {
        what: "A skill that declares scripts cannot be added.",
        because: "brain.tools.skills.Skill.digest covers a script's name and not its bytes, so an approval would not cover the code, and brain.tools.run_skill has no runner; brain.console.skill_library refuses one at the door.",
      },
    ],
  },
  "Workflows and automations": {
    screens: ["/agents/:agentId/:tab"],
    routes: [
      "/api/v1/agents/{agent_id}/automation-templates*",
      "/api/v1/agents/{agent_id}/automations",
      "/api/v1/agents/{agent_id}/automations/{automation_id}/start",
      "/api/v1/agents/{agent_id}/automations/{automation_id}/stop",
    ],
    tables: ["agent.automation", "agent.automation_run", "agent.automation_schedule", "gate.automation_owner"],
    installation: [],
    gaps: [
      {
        what: "An installed automation cannot be changed or removed, only started and stopped.",
        because: "brain.automation_schedule_routes starts and stops one and brain.console.agent_automations.remove decides a removal that no route performs; 0067 grants an update of the next run alone.",
      },
      {
        what: "Three of the four automation templates cannot be started on any install.",
        because: "brain.ops.automation_run.TASKS says what work_summary, source_freshness and approvals_waiting each still need, and the Automations tab shows that sentence instead of a Start control.",
      },
    ],
  },
  "Connectors and third-party integrations": {
    screens: ["/connectors"],
    routes: [
      "/api/v1/connectors",
      "/api/v1/connectors/{connector}/disconnect",
      "/api/v1/connectors/lark-app",
      "/api/v1/connectors/lark-app/test",
    ],
    tables: [
      "ops.connector_connection",
      "ops.connector_sync",
      "proj.record",
      "er.alias",
      "er.canonical",
      "er.identifier",
      "er.link",
    ],
    installation: ["INSTALL_LARK_USES", "INSTALL_LARK_PLATFORM", "INSTALL_LARK_BASE"],
    gaps: [
      {
        what: "A connected source is read and kept, and no question is answered from what is kept.",
        because:
          "No row tool is registered for a connected source's records: brain.tools.startup.classification_for is keyed on the entity alone and Xero and HubSpot both project contact, which that module records as the limit to change first. brain.ops.connector_admin.WHAT_CONNECTING_A_SOURCE_STARTS says so on the screen.",
      },
      {
        what: "HubSpot can be connected and is not read.",
        because:
          "brain.ops.limits records no verified call ceiling for it and brain.connectors.throttle.limits_for refuses to invent one; its row carries brain.ops.connector_sync.NO_VERIFIED_CEILING.",
      },
      {
        what: "Freshdesk, Google Drive and the Laravel views cannot be connected from a screen.",
        because:
          "Each needs a visibility rule, a department declaration or a key file the form cannot collect, which brain.ops.connectable.NOT_FROM_THE_CONSOLE says for each.",
      },
      {
        what: "Connect Lark switches knowledge from Wiki and Base on, and no question is answered from Lark yet.",
        because:
          "The Lark knowledge connector that keeps the minimal index and reads pages and records live is still to be built over the settings Connect Lark writes; brain.ops.lark_connect.KNOWLEDGE_IS_SWITCHED_ON_AND_NOTHING_IS_COPIED says so on the screen.",
      },
      {
        what: "The Lark chat channel is set up and tested and does not yet receive Lark's events.",
        because:
          "No channel in this release receives a webhook, so there is no address for Lark's Events and callbacks page to verify; brain.ops.lark_connect.THE_CHANNEL_RECEIVER_IS_NOT_BUILT_YET says so in the steps.",
      },
    ],
  },
  "API keys, credentials and secrets, held in the vault and never displayed": {
    screens: ["/webhooks", "/vault", "/models"],
    routes: ["/api/v1/credentials*", "/api/v1/vault"],
    tables: ["ops.credential_write", "ops.vault_access"],
    installation: [],
    gaps: [],
  },
  "Knowledge bases, documents and data sources": {
    screens: [
      "/library",
      "/learning",
      "/memory",
      "/memory/:subject",
      "/records",
      "/records/:entity",
      "/classification",
      "/classification/:entity",
      "/classification/:entity/:column",
      "/artifacts",
    ],
    routes: [
      "/api/v1/govern/library",
      "/api/v1/govern/learning",
      "/api/v1/govern/learning/undo",
      "/api/v1/govern/memory",
      "/api/v1/records/{entity}",
      "/api/v1/classifications*",
      "/api/v1/govern/artifacts",
      "/api/v1/records/{entity}/access",
    ],
    tables: [
      "know.item",
      "know.chunk",
      "mem.adaptive",
      "mem.persistent",
      "mem.learning",
      "mem.correction",
      "gate.fast_path_rule",
      "gate.field_policy",
      "agent.artifact",
    ],
    installation: ["INSTALL_VECTOR_STORE", "INSTALL_EMBEDDING_REVISION"],
    gaps: [
      { what: "A document or a data source cannot be added from the console after setup.", leaf: "M42.5.9" },
      {
        what: "A memory cannot be edited from a screen, and a tier-two rule cannot be promoted nor a tier-three change decided.",
        because:
          "brain.ops.memory_store writes an edit and no route offers one: the control belongs on a person's own memory tab, and the Memory screen says edit_is_not_writable. Nothing records agreement or a decision, which the Learning screen says in place of Promote and Decide.",
      },
      {
        what: "A column's classification cannot be changed; a proposed change is reviewed and not applied.",
        because: "brain.classification_routes mounts only the dry-run review, and tests/unit/test_classification_routes.py holds that nothing mounted there can change a classification.",
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
    screens: ["/webhooks"],
    routes: ["/api/v1/webhooks*"],
    tables: ["ops.webhook_subscriber", "ops.webhook_change"],
    installation: [],
    gaps: [
      {
        what: "No platform's webhook is received.",
        because:
          "No route receives one, and the WhatsApp and Lark checks are not written; the Webhooks screen lists each channel's check from brain.ops.inbound_webhooks.",
      },
    ],
  },
  "Scheduled jobs and background work": {
    screens: ["/jobs", "/runs"],
    routes: ["/api/v1/jobs*", "/api/v1/operate/runs"],
    tables: ["ops.control_run", "ops.operation"],
    installation: [],
    gaps: [
      {
        what: "A run in progress cannot be stopped.",
        because: "The route says no_run_can_be_stopped: a control runs to its end inside the worker's tick and there is nothing to signal.",
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
    routes: ["/api/v1/errors", "/api/v1/logs"],
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
    screens: ["/audit", "/requirement-checks"],
    routes: ["/api/v1/audit*", "/api/v1/requirements/checks"],
    tables: ["obs.audit_entry", "ops.sensitive_read", "ops.requirement_check"],
    installation: [],
    gaps: [],
  },
  "System health and the state of every service": {
    screens: ["/models", "/runs"],
    routes: [],
    tables: [],
    installation: [],
    gaps: [
      {
        what: "The state of each service the install runs on is not shown.",
        because: "/health/ready answers the orchestrator outside /api/v1 with no screen reading it. Each rung's circuit breaker is shown, on the Models and health screen from GET /api/v1/models/providers, replayed from the attempts the executor recorded.",
      },
    ],
  },
  "Backup and recovery": {
    screens: ["/recovery", "/retention", "/compliance", "/referrals"],
    routes: [
      "/api/v1/install/recovery",
      "/api/v1/govern/retention*",
      "/api/v1/govern/legal-holds*",
      "/api/v1/govern/erasures",
      "/api/v1/govern/compliance*",
      "/api/v1/me/referrals*",
    ],
    tables: [
      "ops.retention_release",
      "ops.retention_report",
      "obs.legal_hold",
      "ops.erasure_request",
      "ops.breach_case",
      "ops.sensitive_referral",
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
  "POST /api/v1/automation/tool-call":
    "Called by a running automation with its owner's reach, not by a person at a screen; installing the automation is the console's part.",
  "chat.conversation": "What a person asked and was answered belongs to them; no store queries it yet (brain.chat.threads) and usage is reported without the words.",
  "chat.message": "The same as chat.conversation: a person's own words, reported on and never managed.",
  "gate.channel_event":
    "The dedupe key of each inbound channel message, claimed once by brain.gate.event_store.first_delivery and read by nothing else; there is nothing in it for anybody to manage.",
};

/**
 * Reads a screen makes only once a person has done something, which opening the page does not
 * show: a subject's history, a staff source's trial run and an automation's preview.
 */
/** `versioned` is false for a read served at the root, as the setup routes are, rather than under `/api/v1`. */
export const READ_AFTER_AN_ACTION: Readonly<
  Record<string, { readonly screen: string; readonly spelled: string; readonly built: string; readonly versioned?: boolean }>
> = {
  "GET /api/v1/audit/history": { screen: "/audit", spelled: "historyApiPath", built: historyApiPath("principal", "u_1").split("?")[0] ?? "" },
  "GET /api/v1/govern/staff_sources/trial": { screen: "/staff_sources", spelled: "TRIAL_API_PATH", built: TRIAL_API_PATH },
  "GET /setup/staff-source/registration": {
    screen: "/first-run",
    spelled: "REGISTRATION_PATH",
    built: STAFF_LIST_REGISTRATION_PATH,
    versioned: false,
  },
  "GET /api/v1/models/providers-register": { screen: "/models", spelled: "REGISTER_API_PATH", built: PROVIDER_REGISTER_API_PATH },
  "GET /api/v1/agents/{agent_id}/automation-templates/{template_id}/preview": {
    screen: "/agents/:agentId/:tab",
    spelled: "automationPreviewApiPath",
    built: automationPreviewApiPath("quote-helper", "weekly_work_summary"),
  },
};

// ---------------------------------------------------------------------- writes and proofs

/** One write a screen sends: the call's key in `support/writes.ts`, and every route it can reach. */
export interface WriteRoute {
  readonly route: string;
  /** The address the call builds, from the function or constant that spells it. */
  readonly spelled: string;
  readonly built: string;
  /** False for the two setup routes, which live at the root rather than under `/api/v1`. */
  readonly versioned: boolean;
}

/** A case or referral id to build a compliance address with; the routes take a UUID. */
const COMPLIANCE_CASE = "11111111-2222-4333-8444-555555555555";

function at(route: string, spelled: string, built: string, versioned = true): WriteRoute {
  return { route, spelled, built, versioned };
}

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/Learning.tsx UNDO_API_PATH": [at("POST /api/v1/govern/learning/undo", "UNDO_API_PATH", UNDO_API_PATH)],
  "src/pages/Departments.tsx asked.path": [
    at("POST /api/v1/govern/departments/membership", "MEMBERSHIP_API_PATH", MEMBERSHIP_API_PATH),
    at("POST /api/v1/govern/departments/lead", "LEAD_API_PATH", LEAD_API_PATH),
    at("POST /api/v1/govern/people/disable", "DISABLE_API_PATH", DISABLE_API_PATH),
    at("POST /api/v1/govern/people/enable", "ENABLE_API_PATH", ENABLE_API_PATH),
  ],
  "src/pages/Elevation.tsx ELEVATION_REQUESTS_API_PATH": [
    at("POST /api/v1/govern/elevation/requests", "ELEVATION_REQUESTS_API_PATH", ELEVATION_REQUESTS_API_PATH),
  ],
  "src/pages/Elevation.tsx elevationDecisionApiPath(chosen.row.request_id)": [
    at(
      "POST /api/v1/govern/elevation/requests/{request_id}/decision",
      "elevationDecisionApiPath",
      elevationDecisionApiPath("11111111-2222-3333-4444-555555555555"),
    ),
  ],
  "src/pages/AccessReview.tsx REVIEW_DECISION_API_PATH": [
    at("POST /api/v1/govern/access-review/decision", "REVIEW_DECISION_API_PATH", REVIEW_DECISION_API_PATH),
  ],
  "src/pages/AccessReview.tsx REVIEW_DECISIONS_API_PATH": [
    at("POST /api/v1/govern/access-review/decisions", "REVIEW_DECISIONS_API_PATH", REVIEW_DECISIONS_API_PATH),
  ],
  "src/pages/Approvals.tsx approvalDecisionApiPath(suspensionId)": [
    at("POST /api/v1/approvals/{suspension_id}/decision", "approvalDecisionApiPath", approvalDecisionApiPath("sus-1")),
  ],
  "src/pages/Ask.tsx ANSWER_API_PATH": [at("POST /api/v1/answer", "ANSWER_API_PATH", ANSWER_API_PATH)],
  "src/pages/AccessRequests.tsx ACCESS_REQUESTS_API_PATH": [
    at("POST /api/v1/access-requests", "ACCESS_REQUESTS_API_PATH", ACCESS_REQUESTS_API_PATH),
  ],
  "src/pages/Classification.tsx reviewApiPath(entity, row.column)": [
    at("POST /api/v1/classifications/{entity}/columns/{column}/review", "reviewApiPath", reviewApiPath("price_list", "cost")),
  ],
  "src/pages/DataTransfer.tsx EXPORTS_API_PATH": [at("POST /api/v1/data-transfer/exports", "EXPORTS_API_PATH", EXPORTS_API_PATH)],
  "src/pages/Features.tsx switchPath(row.name)": [at("POST /api/v1/install/features/{name}", "switchPath", switchPath("schedule_control"))],
  "src/pages/Settings.tsx savePath(row.name)": [at("PUT /api/v1/install/settings/{name}", "savePath", savePath("INSTALL_COMPANY_NAME"))],
  "src/pages/FirstRun.tsx FINISH_PATH": [at("POST /setup/sign-in", "FINISH_PATH", FINISH_PATH, false)],
  "src/pages/FirstRun.tsx APPOINTMENT_PATH": [at("POST /setup/appointment", "APPOINTMENT_PATH", APPOINTMENT_PATH, false)],
  "src/components/StaffListCheck.tsx SIGN_IN_PATH": [
    at("POST /setup/staff-source/sign-in", "SIGN_IN_PATH", STAFF_LIST_SIGN_IN_PATH, false),
  ],
  "src/components/StaffListCheck.tsx TRIAL_PATH": [
    at("POST /setup/staff-source/trial", "TRIAL_PATH", STAFF_LIST_TRIAL_PATH, false),
  ],
  "src/pages/StaffSources.tsx CREDENTIAL_API_PATH": [
    at("PUT /api/v1/govern/staff_sources/credential", "CREDENTIAL_API_PATH", CREDENTIAL_API_PATH),
  ],
  "src/pages/StaffSources.tsx transferApiPath(agentId)": [
    at("POST /api/v1/govern/staff_sources/transfers/{agent_id}", "transferApiPath", transferApiPath("a_quotes")),
  ],
  "src/components/ConnectStaffSource.tsx path": [
    at("POST /api/v1/govern/staff_sources/test", "CONNECTION_TEST_API_PATH", CONNECTION_TEST_API_PATH),
    at("POST /api/v1/govern/staff_sources/first-sync", "FIRST_SYNC_API_PATH", FIRST_SYNC_API_PATH),
  ],
  "src/components/ConnectStaffSource.tsx CONNECT_API_PATH": [
    at("POST /api/v1/govern/staff_sources/connect", "CONNECT_API_PATH", CONNECT_API_PATH),
  ],
  "src/components/ConnectStaffSource.tsx APPLY_FIRST_SYNC_API_PATH": [
    at("POST /api/v1/govern/staff_sources/first-sync/apply", "APPLY_FIRST_SYNC_API_PATH", APPLY_FIRST_SYNC_API_PATH),
  ],
  "src/pages/Jobs.tsx actionPath(asked.action, asked.row.control)": [
    at("POST /api/v1/jobs/{name}/pause", "actionPath", actionPath("pause", "spend_report_refresh")),
    at("POST /api/v1/jobs/{name}/resume", "actionPath", actionPath("resume", "spend_report_refresh")),
    at("POST /api/v1/jobs/{name}/run", "actionPath", actionPath("run", "spend_report_refresh")),
  ],
  "src/pages/Matrix.tsx rungApiPath(rung.id)": [at("PATCH /api/v1/routing/rungs/{rung_id}", "rungApiPath", rungApiPath("rung-1"))],
  "src/components/MatrixGate.tsx GOLDEN_API_PATH": [
    at("POST /api/v1/routing/golden-questions", "GOLDEN_API_PATH", GOLDEN_API_PATH),
  ],
  "src/components/MatrixGate.tsx retireGoldenApiPath(asked.row.id)": [
    at(
      "POST /api/v1/routing/golden-questions/{question_id}/retire",
      "retireGoldenApiPath",
      retireGoldenApiPath("33333333-3333-4333-8333-333333333333"),
    ),
  ],
  "src/components/MatrixGate.tsx ADD_RUNG_API_PATH": [at("POST /api/v1/routing/rungs", "ADD_RUNG_API_PATH", ADD_RUNG_API_PATH)],
  "src/components/ProviderRegister.tsx termsApiPath(asked.provider)": [
    at("PUT /api/v1/models/providers/{provider}/terms", "termsApiPath", termsApiPath("anthropic")),
  ],
  "src/components/ProviderRegister.tsx retireProviderApiPath(asked.provider)": [
    at("POST /api/v1/models/providers/{provider}/retire", "retireProviderApiPath", retireProviderApiPath("acme_llm")),
  ],
  "src/components/ProviderRegister.tsx ADD_PROVIDER_API_PATH": [
    at("POST /api/v1/models/providers", "ADD_PROVIDER_API_PATH", ADD_PROVIDER_API_PATH),
  ],
  "src/components/ProviderKeyForm.tsx credentialPath(slot)": [
    at("PUT /api/v1/credentials/{family}/{name}", "credentialPath", credentialPath("providers/anthropic")),
  ],
  "src/components/RoutingSettings.tsx tierApiPath(asked.tier)": [
    at("PUT /api/v1/models/tiers/{tier}", "tierApiPath", tierApiPath("main")),
  ],
  "src/components/RoutingSettings.tsx tierResetApiPath(asked.tier)": [
    at("POST /api/v1/models/tiers/{tier}/reset", "tierResetApiPath", tierResetApiPath("main")),
  ],
  "src/components/RoutingSettings.tsx RESIDENCY_API_PATH": [
    at("POST /api/v1/models/residency", "RESIDENCY_API_PATH", RESIDENCY_API_PATH),
  ],
  "src/components/RoutingSettings.tsx residencyRetireApiPath(asked.row.id)": [
    at(
      "POST /api/v1/models/residency/{constraint_id}/retire",
      "residencyRetireApiPath",
      residencyRetireApiPath("44444444-4444-4444-8444-444444444444"),
    ),
  ],
  "src/components/AgentModelPin.tsx modelPinApiPath(agentId)": [
    at("PUT /api/v1/agents/{agent_id}/model-pin", "modelPinApiPath", modelPinApiPath("quote-helper")),
  ],
  "src/pages/Models.tsx providerSwitchApiPath(pending.provider)": [
    at("PUT /api/v1/models/providers/{provider}", "providerSwitchApiPath", providerSwitchApiPath("anthropic")),
  ],
  "src/pages/Models.tsx providerCheckApiPath(pending.provider)": [
    at("POST /api/v1/models/providers/{provider}/check", "providerCheckApiPath", providerCheckApiPath("anthropic")),
  ],
  "src/pages/People.tsx REMOVAL_API_PATH": [at("POST /api/v1/govern/grants/removal", "REMOVAL_API_PATH", REMOVAL_API_PATH)],
  "src/pages/People.tsx GRANTS_API_PATH": [at("POST /api/v1/govern/grants", "GRANTS_API_PATH", GRANTS_API_PATH)],
  "src/components/DataStewardCard.tsx STEWARD_API_PATH": [
    at("POST /api/v1/govern/data-steward", "STEWARD_API_PATH", STEWARD_API_PATH),
  ],
  "src/pages/Prompts.tsx editPath(asked.row.agent_id)": [at("POST /api/v1/govern/prompts/{agent_id}", "editPath", editPath("quote-helper"))],
  "src/pages/Prompts.tsx giveBackPath(asked.row.agent_id)": [
    at("POST /api/v1/govern/prompts/{agent_id}/give-back", "giveBackPath", giveBackPath("quote-helper")),
  ],
  "src/pages/Retention.tsx path": [
    at("POST /api/v1/govern/retention/release", "RELEASE_API_PATH", RELEASE_API_PATH),
    at("POST /api/v1/govern/retention/withdrawal", "WITHDRAWAL_API_PATH", WITHDRAWAL_API_PATH),
    at("POST /api/v1/govern/legal-holds", "HOLD_API_PATH", HOLD_API_PATH),
    at("POST /api/v1/govern/legal-holds/lift", "LIFT_API_PATH", LIFT_API_PATH),
    at("POST /api/v1/govern/erasures", "ERASURES_API_PATH", ERASURES_API_PATH),
  ],
  "src/pages/Sessions.tsx END_SESSION_API_PATH": [at("POST /api/v1/govern/sessions/end", "END_SESSION_API_PATH", END_SESSION_API_PATH)],
  "src/pages/Sessions.tsx END_SESSIONS_API_PATH": [
    at("POST /api/v1/govern/sessions/end-several", "END_SESSIONS_API_PATH", END_SESSIONS_API_PATH),
  ],
  "src/pages/SignInLinks.tsx LINK_API_PATH": [at("POST /api/v1/sign-ins", "LINK_API_PATH", LINK_API_PATH)],
  "src/pages/SignInLinks.tsx UNLINK_API_PATH": [at("POST /api/v1/govern/sign-ins/unlink", "UNLINK_API_PATH", UNLINK_API_PATH)],
  "src/pages/Webhooks.tsx REGISTER_API_PATH": [at("POST /api/v1/webhooks/subscribers", "REGISTER_API_PATH", REGISTER_API_PATH)],
  "src/pages/Webhooks.tsx secretApiPath(asked.id)": [
    at("POST /api/v1/webhooks/subscribers/{subscriber_id}/secret", "secretApiPath", secretApiPath("billing_bridge")),
  ],
  "src/pages/Webhooks.tsx switchOffApiPath(asked.id)": [
    at("POST /api/v1/webhooks/subscribers/{subscriber_id}/switch-off", "switchOffApiPath", switchOffApiPath("billing_bridge")),
  ],
  "src/pages/Notifications.tsx noticeApiPath(asked.row.kind)": [
    at("POST /api/v1/notifications/notices/{kind}", "noticeApiPath", noticeApiPath("evening_digest")),
  ],
  "src/pages/Notifications.tsx RELAY_API_PATH": [at("POST /api/v1/notifications/relay", "RELAY_API_PATH", RELAY_API_PATH)],
  "src/pages/Notifications.tsx PASSWORD_API_PATH": [
    at("POST /api/v1/notifications/relay/password", "PASSWORD_API_PATH", RELAY_PASSWORD_API_PATH),
  ],
  "src/pages/Notifications.tsx TRIAL_API_PATH": [
    at("POST /api/v1/notifications/relay/test", "TRIAL_API_PATH", RELAY_TRIAL_API_PATH),
  ],
  "src/pages/Skills.tsx SKILLS_API_PATH": [at("POST /api/v1/skills", "SKILLS_API_PATH", SKILLS_API_PATH)],
  "src/pages/Skills.tsx reviewPath(one.digest)": [
    at("POST /api/v1/skills/{digest}/review", "reviewPath", reviewPath("d".repeat(64))),
  ],
  "src/pages/Skills.tsx assignPath(one.digest)": [
    at("POST /api/v1/skills/{digest}/assignments", "assignPath", assignPath("d".repeat(64))),
  ],
  "src/pages/Connectors.tsx disconnectApiPath(row.name)": [
    at("POST /api/v1/connectors/{connector}/disconnect", "disconnectApiPath", disconnectApiPath("xero")),
  ],
  "src/components/ConnectSource.tsx CONNECTORS_API_PATH": [at("POST /api/v1/connectors", "CONNECTORS_API_PATH", CONNECTORS_API_PATH)],
  "src/components/ConnectLark.tsx LARK_TEST_API_PATH": [
    at("POST /api/v1/connectors/lark-app/test", "LARK_TEST_API_PATH", LARK_TEST_API_PATH),
  ],
  "src/components/ConnectLark.tsx LARK_API_PATH": [at("POST /api/v1/connectors/lark-app", "LARK_API_PATH", LARK_API_PATH)],
  "src/components/AutomationGallery.tsx automationInstallApiPath(agentId)": [
    at("POST /api/v1/agents/{agent_id}/automations", "automationInstallApiPath", automationInstallApiPath("quote-helper")),
  ],
  "src/components/AgentAutomations.tsx path": [
    at(
      "POST /api/v1/agents/{agent_id}/automations/{automation_id}/start",
      "automationStartApiPath",
      automationStartApiPath("quote-helper", "auto_one"),
    ),
    at(
      "POST /api/v1/agents/{agent_id}/automations/{automation_id}/stop",
      "automationStopApiPath",
      automationStopApiPath("quote-helper", "auto_one"),
    ),
  ],
  "src/pages/RoleControls.tsx path": [
    at("POST /api/v1/govern/roles/appointment", "APPOINTMENT_API_PATH", APPOINTMENT_API_PATH),
    at("POST /api/v1/govern/roles/deputy", "DEPUTY_API_PATH", DEPUTY_API_PATH),
  ],
  "src/pages/GroupRules.tsx GROUP_RULES_API_PATH": [
    at("POST /api/v1/govern/roles/group-rules", "GROUP_RULES_API_PATH", GROUP_RULES_API_PATH),
  ],
  "src/pages/GroupRules.tsx GROUP_RULE_RETIREMENT_API_PATH": [
    at(
      "POST /api/v1/govern/roles/group-rules/retirement",
      "GROUP_RULE_RETIREMENT_API_PATH",
      GROUP_RULE_RETIREMENT_API_PATH,
    ),
  ],
  "src/pages/RoleControls.tsx ROLE_REMOVAL_API_PATH": [
    at("POST /api/v1/govern/roles/removal", "ROLE_REMOVAL_API_PATH", ROLE_REMOVAL_API_PATH),
  ],
  "src/pages/People.tsx PACK_ASSIGNMENT_API_PATH": [
    at("POST /api/v1/govern/packs/assignment", "PACK_ASSIGNMENT_API_PATH", PACK_ASSIGNMENT_API_PATH),
  ],
  "src/pages/Audit.tsx VERIFICATION_API_PATH": [
    at("POST /api/v1/audit/verification", "VERIFICATION_API_PATH", VERIFICATION_API_PATH),
  ],
  "src/pages/RequirementChecks.tsx CHECKS_API_PATH": [
    at("POST /api/v1/requirements/checks", "CHECKS_API_PATH", CHECKS_API_PATH),
  ],
  "src/pages/Compliance.tsx topicApiPath(asked.topic)": [
    at("PUT /api/v1/govern/compliance/topics/{topic}", "topicApiPath", topicApiPath("grievance")),
  ],
  "src/pages/Compliance.tsx path": [
    at("POST /api/v1/govern/compliance/breaches", "BREACHES_API_PATH", BREACHES_API_PATH),
    at(
      "POST /api/v1/govern/compliance/breaches/{case_id}/assessment",
      "breachStepApiPath",
      breachStepApiPath(COMPLIANCE_CASE, "assessment"),
    ),
    at(
      "POST /api/v1/govern/compliance/breaches/{case_id}/commission",
      "breachStepApiPath",
      breachStepApiPath(COMPLIANCE_CASE, "commission"),
    ),
    at(
      "POST /api/v1/govern/compliance/breaches/{case_id}/individuals",
      "breachStepApiPath",
      breachStepApiPath(COMPLIANCE_CASE, "individuals"),
    ),
    at(
      "POST /api/v1/govern/compliance/breaches/{case_id}/exception",
      "breachStepApiPath",
      breachStepApiPath(COMPLIANCE_CASE, "exception"),
    ),
    at("POST /api/v1/govern/compliance/breaches/{case_id}/close", "breachStepApiPath", breachStepApiPath(COMPLIANCE_CASE, "close")),
  ],
  "src/pages/Referrals.tsx handledApiPath(chosen.referral_id)": [
    at("POST /api/v1/me/referrals/{referral_id}/handled", "handledApiPath", handledApiPath(COMPLIANCE_CASE)),
  ],
};

/** A named Python test that asserts one of the three, or why there is none. */
export type Proof =
  | { readonly test: string; readonly database: boolean }
  | { readonly none: string; readonly leaf?: string }
  | { readonly notApplicable: string };

export interface Proofs {
  readonly row: Proof;
  readonly audit: Proof;
  readonly behaviour: Proof;
}

function t(file: string, name: string, database = false): Proof {
  return { test: `tests/unit/${file}.py::${name}`, database };
}

/** `tests/unit/test_console_control_audit.py`, which presses these controls against PostgreSQL. */
function audited(name: string): Proof {
  return t("test_console_control_audit", name, true);
}

const SETTINGS_PRESSED = audited("test_a_feature_switch_and_each_job_control_reach_the_row_the_ledger_and_the_next_tick");
const BRANDING_SAVED = t(
  "test_settings_routes",
  "test_saving_a_company_name_writes_its_row_and_the_console_header_draws_it_next",
);
const INSTRUCTIONS_PRESSED = audited("test_an_instruction_edit_and_its_give_back_reach_the_install_the_ledger_and_the_prompt");
const GROUP_RULES_PRESSED = t(
  "test_group_sync",
  "test_mapping_and_retiring_through_the_routes_reach_the_rows_and_the_ledger",
  true,
);
const ROLES_PRESSED = t(
  "test_role_grant",
  "test_an_appointment_through_the_routes_reaches_the_row_and_the_ledger_with_its_reason",
  true,
);
const GRANTS_PRESSED = audited("test_a_grant_written_and_removed_from_the_people_screen_reaches_row_ledger_and_reach");
const WEBHOOK_LEDGER = audited("test_each_webhook_change_through_the_store_appends_one_entry_naming_its_own_author");
const HOLDS_SWEPT = audited("test_a_hold_placed_through_the_store_keeps_its_rows_from_the_sweep_and_lifted_releases_them");
const A_WEBHOOK_IS_DELIVERED = t(
  "test_webhook_delivery",
  "test_a_due_event_is_signed_received_verified_and_recorded_delivered",
  true,
);
const NO_TRIAL_LEDGER: Proof = {
  none: "A test message is recorded in ops.operation under its key, and the audit ledger has no action for a message sent: brain.ops.mail.A_TEST_IS_ONE_MESSAGE_PER_CONFIGURATION.",
};
const A_SETTING_ENTRY_NO_TEST_FOLLOWS: Proof = {
  none: "The write is an ops.setting row, which migration 0059's trigger records as a setting entry naming the key, the change and the writer, and no test follows this route's write to that entry.",
};

const CONNECTION_REACHES_THE_ROW_AND_THE_LEDGER = t(
  "test_connector_store",
  "test_connecting_and_disconnecting_reach_the_row_the_ledger_and_the_key_s_record",
  true,
);
const A_CONNECTED_SOURCE_IS_READ_AND_A_DISCONNECTED_ONE_IS_NOT = t(
  "test_connector_sync_run",
  "test_a_connected_source_is_read_and_once_disconnected_it_is_never_read_again",
  true,
);

const UNDO_REACHES_THE_ROW_THE_LEDGER_AND_RECALL = t(
  "test_memory_store",
  "test_an_undo_reaches_the_row_the_ledger_and_what_is_recalled_next",
  true,
);
const PLACEMENT_REACHES_THE_ROW_THE_LEDGER_AND_THE_PAGE = t(
  "test_organisation_store",
  "test_placing_and_appointing_reach_the_rows_the_ledger_and_the_departments_page",
  true,
);
const DISABLE_REACHES_THE_ROW_THE_LEDGER_AND_THE_TOKEN = t(
  "test_principal_state",
  "test_a_disable_ends_the_session_refuses_the_token_and_an_enable_returns_the_grants",
  true,
);
const ELEVATION_REACHES_THE_ROW_THE_LEDGER_AND_THE_RESOLVER = t(
  "test_elevation_store",
  "test_an_approved_elevation_widens_the_requester_and_after_its_lapse_it_does_not",
  true,
);

const A_PERSON_NAMED_FOR_A_TOPIC = t(
  "test_compliance_store",
  "test_naming_a_person_writes_one_route_row_and_a_setting_entry_without_the_value",
  true,
);
const BREACH_STEP_WRITTEN = t(
  "test_compliance_store",
  "test_each_breach_step_writes_its_column_and_one_breach_entry_in_the_same_transaction",
  true,
);
/** Every breach write, opening a case and each step after it, is proved by the same three tests. */
const BREACH_STEP: Proofs = {
  row: BREACH_STEP_WRITTEN,
  audit: BREACH_STEP_WRITTEN,
  behaviour: t("test_compliance_routes", "test_a_case_shows_its_clock_from_the_awareness_and_its_findings"),
};

/** Every write route a screen sends, followed to the system. */
export const PROOFS: Readonly<Record<string, Proofs>> = {
  "POST /api/v1/govern/learning/undo": {
    row: UNDO_REACHES_THE_ROW_THE_LEDGER_AND_RECALL,
    audit: UNDO_REACHES_THE_ROW_THE_LEDGER_AND_RECALL,
    behaviour: t(
      "test_estate_routes",
      "test_an_undo_writes_the_correction_and_the_next_reading_no_longer_recalls_the_learning",
    ),
  },
  "POST /api/v1/govern/departments/membership": {
    row: PLACEMENT_REACHES_THE_ROW_THE_LEDGER_AND_THE_PAGE,
    audit: PLACEMENT_REACHES_THE_ROW_THE_LEDGER_AND_THE_PAGE,
    behaviour: PLACEMENT_REACHES_THE_ROW_THE_LEDGER_AND_THE_PAGE,
  },
  "POST /api/v1/govern/departments/lead": {
    row: PLACEMENT_REACHES_THE_ROW_THE_LEDGER_AND_THE_PAGE,
    audit: PLACEMENT_REACHES_THE_ROW_THE_LEDGER_AND_THE_PAGE,
    behaviour: PLACEMENT_REACHES_THE_ROW_THE_LEDGER_AND_THE_PAGE,
  },
  "POST /api/v1/govern/people/disable": {
    row: DISABLE_REACHES_THE_ROW_THE_LEDGER_AND_THE_TOKEN,
    audit: DISABLE_REACHES_THE_ROW_THE_LEDGER_AND_THE_TOKEN,
    behaviour: DISABLE_REACHES_THE_ROW_THE_LEDGER_AND_THE_TOKEN,
  },
  "POST /api/v1/govern/people/enable": {
    row: DISABLE_REACHES_THE_ROW_THE_LEDGER_AND_THE_TOKEN,
    audit: DISABLE_REACHES_THE_ROW_THE_LEDGER_AND_THE_TOKEN,
    behaviour: DISABLE_REACHES_THE_ROW_THE_LEDGER_AND_THE_TOKEN,
  },
  "POST /api/v1/govern/elevation/requests": {
    row: ELEVATION_REACHES_THE_ROW_THE_LEDGER_AND_THE_RESOLVER,
    audit: ELEVATION_REACHES_THE_ROW_THE_LEDGER_AND_THE_RESOLVER,
    behaviour: ELEVATION_REACHES_THE_ROW_THE_LEDGER_AND_THE_RESOLVER,
  },
  "POST /api/v1/govern/elevation/requests/{request_id}/decision": {
    row: ELEVATION_REACHES_THE_ROW_THE_LEDGER_AND_THE_RESOLVER,
    audit: ELEVATION_REACHES_THE_ROW_THE_LEDGER_AND_THE_RESOLVER,
    behaviour: ELEVATION_REACHES_THE_ROW_THE_LEDGER_AND_THE_RESOLVER,
  },
  "POST /api/v1/connectors": {
    row: CONNECTION_REACHES_THE_ROW_AND_THE_LEDGER,
    audit: CONNECTION_REACHES_THE_ROW_AND_THE_LEDGER,
    behaviour: A_CONNECTED_SOURCE_IS_READ_AND_A_DISCONNECTED_ONE_IS_NOT,
  },
  "POST /api/v1/connectors/lark-app": {
    row: t("test_lark_connect", "test_a_save_keeps_one_credential_in_each_uses_slot_and_switches_them_on"),
    audit: A_SETTING_ENTRY_NO_TEST_FOLLOWS,
    behaviour: t("test_lark_connect", "test_after_a_save_each_use_says_where_it_stands"),
  },
  "POST /api/v1/connectors/lark-app/test": {
    row: { notApplicable: "A Lark test writes no row here or in Lark: every request after the token exchange is a read, which the fake Lark server records." },
    audit: { notApplicable: "Nothing is written, so there is nothing for the ledger to record, and the secret is never logged." },
    behaviour: t("test_lark_connect", "test_the_test_route_reports_each_use_and_writes_nothing"),
  },
  "POST /api/v1/connectors/{connector}/disconnect": {
    row: CONNECTION_REACHES_THE_ROW_AND_THE_LEDGER,
    audit: CONNECTION_REACHES_THE_ROW_AND_THE_LEDGER,
    behaviour: A_CONNECTED_SOURCE_IS_READ_AND_A_DISCONNECTED_ONE_IS_NOT,
  },
  "POST /api/v1/govern/access-review/decision": {
    row: t("test_review_store", "test_keeping_and_removing_reach_the_rows_the_ledger_and_what_the_holder_is_resolved_to", true),
    audit: t("test_review_store", "test_keeping_and_removing_reach_the_rows_the_ledger_and_what_the_holder_is_resolved_to", true),
    behaviour: t("test_review_store", "test_keeping_and_removing_reach_the_rows_the_ledger_and_what_the_holder_is_resolved_to", true),
  },
  // Several decisions are the single decision's store call once per holding, which the route test
  // holds; what that call writes, records and changes is the single decision's database proof.
  "POST /api/v1/govern/access-review/decisions": {
    row: t("test_govern_people_routes", "test_several_holdings_are_decided_one_at_a_time_each_by_the_single_decisions_question"),
    audit: t("test_review_store", "test_keeping_and_removing_reach_the_rows_the_ledger_and_what_the_holder_is_resolved_to", true),
    behaviour: t("test_review_store", "test_keeping_and_removing_reach_the_rows_the_ledger_and_what_the_holder_is_resolved_to", true),
  },
  "POST /api/v1/approvals/{suspension_id}/decision": {
    row: t("test_suspension_store", "test_a_decided_approval_leaves_one_ledger_entry_that_survives_a_restart", true),
    audit: t("test_suspension_store", "test_a_decided_approval_leaves_one_ledger_entry_that_survives_a_restart", true),
    behaviour: t("test_suspension_store", "test_an_approved_suspension_is_what_resume_reads_and_a_rejected_one_is_not_run", true),
  },
  "POST /api/v1/access-requests": {
    row: t("test_access_request_store", "test_a_request_is_stored_and_its_owner_reads_it_back_as_the_application_role", true),
    audit: {
      notApplicable:
        "A request changes nothing anybody holds: it is a row addressed to its owner, and a decision is a grant written on the Roles screen, which is recorded there.",
    },
    behaviour: t("test_access_request_routes", "test_the_owner_reads_the_requests_addressed_to_them_and_nobody_else_does"),
  },
  "POST /api/v1/answer": {
    row: { notApplicable: "Asking a question writes no row an administrator manages." },
    audit: { notApplicable: "Asking a question is not a change to the system." },
    behaviour: { notApplicable: "The answer is the behaviour, and tests/invariants hold it." },
  },
  "POST /api/v1/classifications/{entity}/columns/{column}/review": {
    row: { notApplicable: "A review is a dry run and writes nothing." },
    audit: { notApplicable: "A review changes nothing, so there is nothing to record." },
    behaviour: t("test_classification_routes", "test_nothing_mounted_here_can_change_a_classification"),
  },
  "POST /api/v1/data-transfer/exports": {
    row: t("test_data_export_store", "test_an_export_leaves_its_record_and_a_publish_entry_naming_what_left_and_who_took_it", true),
    audit: t("test_data_export_store", "test_an_export_leaves_its_record_and_a_publish_entry_naming_what_left_and_who_took_it", true),
    behaviour: t("test_data_transfer_routes", "test_the_listing_offers_the_export_to_a_reader_who_may_take_it_and_shows_only_their_own"),
  },
  "PUT /api/v1/install/settings/{name}": {
    row: BRANDING_SAVED,
    audit: {
      none: "The route sets the audit attribution 0059's trigger reads, which BRANDING_SAVED asserts over a stub; no scratch-Postgres test yet reads the ledger entry back.",
    },
    behaviour: BRANDING_SAVED,
  },
  "POST /api/v1/install/features/{name}": {
    row: SETTINGS_PRESSED,
    audit: SETTINGS_PRESSED,
    behaviour: t("test_console_controls_reach_behaviour", "test_switching_schedule_control_on_from_the_features_screen_is_what_lets_a_job_be_paused"),
  },
  "POST /setup/sign-in": {
    row: t("test_sign_in_routes", "test_the_finishing_screen_binds_the_installers_sign_in_to_the_first_administrator"),
    audit: t("test_sign_in_routes", "test_the_finishing_screen_binds_the_first_administrator_once_against_the_database", true),
    behaviour: t("test_setup_routes", "test_a_fresh_install_reaches_a_signed_in_administrator_through_the_routes_alone", true),
  },
  "POST /setup/appointment": {
    row: t("test_setup_routes", "test_the_setup_code_holder_appoints_the_first_administrator_and_is_sent_to_finish"),
    audit: t("test_first_administrator", "test_the_first_administrator_is_a_live_person_holding_administration_everywhere", true),
    behaviour: t("test_setup_routes", "test_a_fresh_install_reaches_a_signed_in_administrator_through_the_routes_alone", true),
  },
  "POST /setup/staff-source/sign-in": {
    row: { notApplicable: "It answers the directory's own sign-in page for the setup code's holder and writes nothing." },
    audit: { notApplicable: "Nothing changes when a sign-in page is asked for, so there is nothing to record." },
    behaviour: t("test_setup_staff_routes", "test_a_directory_is_chosen_signed_in_to_and_its_list_pulled"),
  },
  "POST /setup/staff-source/trial": {
    row: t("test_setup_staff_routes", "test_a_trial_that_read_the_directory_keeps_its_credential_for_the_nightly_sync"),
    audit: t("test_setup_staff_routes", "test_a_trial_that_read_the_directory_keeps_its_credential_for_the_nightly_sync"),
    behaviour: t("test_setup_staff_routes", "test_a_directory_is_chosen_signed_in_to_and_its_list_pulled"),
  },
  "PUT /api/v1/govern/staff_sources/credential": {
    row: t("test_staff_sync_routes", "test_the_credential_is_replaced_into_its_slot_recorded_and_never_sent_back"),
    audit: t(
      "test_credential_writes",
      "test_a_credential_write_appends_exactly_the_entry_the_recorder_writes_and_the_chain_holds",
      true,
    ),
    behaviour: t("test_staff_sync_run", "test_a_scheduled_run_reads_lark_with_the_kept_credential_and_applies_the_plan"),
  },
  "POST /api/v1/govern/staff_sources/transfers/{agent_id}": {
    row: t(
      "test_staff_sync_routes",
      "test_taking_a_leavers_agent_moves_the_owner_starts_it_again_and_never_widens_its_reach",
    ),
    audit: t("test_staff_connect", "test_the_owner_change_trigger_writes_the_details_the_recorder_writes"),
    behaviour: t(
      "test_staff_sync_routes",
      "test_taking_a_leavers_agent_moves_the_owner_starts_it_again_and_never_widens_its_reach",
    ),
  },
  "POST /api/v1/govern/staff_sources/test": {
    row: { notApplicable: "A connection test keeps nothing: no setting, no credential and no member is written." },
    audit: { notApplicable: "A connection test is not a change to the system, so there is nothing to record." },
    behaviour: t("test_staff_connect", "test_the_test_route_keeps_nothing_and_never_sends_the_secret_back"),
  },
  "POST /api/v1/govern/staff_sources/connect": {
    row: t(
      "test_staff_connect",
      "test_connecting_keeps_the_credential_in_its_slot_saves_two_settings_and_echoes_nothing",
    ),
    audit: t(
      "test_credential_writes",
      "test_a_credential_write_appends_exactly_the_entry_the_recorder_writes_and_the_chain_holds",
      true,
    ),
    behaviour: t(
      "test_staff_sync_run",
      "test_a_source_saved_on_the_screen_is_the_source_the_worker_reads_with_no_server_edit",
    ),
  },
  "POST /api/v1/govern/staff_sources/first-sync": {
    row: { notApplicable: "The first sync's dry run reads the directory and the roster and writes nothing." },
    audit: { notApplicable: "A dry run is not a change to the system, so there is nothing to record." },
    behaviour: t(
      "test_staff_connect",
      "test_the_first_sync_shows_who_it_would_add_and_writes_nothing_until_apply_is_pressed",
    ),
  },
  "POST /api/v1/govern/staff_sources/first-sync/apply": {
    row: t(
      "test_staff_connect",
      "test_the_first_sync_shows_who_it_would_add_and_writes_nothing_until_apply_is_pressed",
    ),
    audit: {
      notApplicable:
        "Applying the first sync is the nightly run started now, and a run is recorded on its own row in auth.staff_sync_run, which the screen lists; no ledger member records a roster run.",
    },
    behaviour: t(
      "test_staff_sync_store",
      "test_the_night_that_marks_a_leaver_stops_their_agents_and_nobody_elses",
      true,
    ),
  },
  "POST /api/v1/jobs/{name}/pause": {
    row: SETTINGS_PRESSED,
    audit: SETTINGS_PRESSED,
    behaviour: t("test_console_controls_reach_behaviour", "test_a_job_paused_from_the_screen_is_left_unstarted_by_the_next_tick_and_resumed_is_started"),
  },
  "POST /api/v1/jobs/{name}/resume": {
    row: SETTINGS_PRESSED,
    audit: SETTINGS_PRESSED,
    behaviour: t("test_console_controls_reach_behaviour", "test_a_job_paused_from_the_screen_is_left_unstarted_by_the_next_tick_and_resumed_is_started"),
  },
  "POST /api/v1/jobs/{name}/run": {
    row: SETTINGS_PRESSED,
    audit: SETTINGS_PRESSED,
    behaviour: t("test_console_controls_reach_behaviour", "test_a_run_asked_for_from_the_screen_is_started_by_the_next_tick_even_while_paused"),
  },
  "PATCH /api/v1/routing/rungs/{rung_id}": {
    row: audited("test_a_rung_saved_from_the_screen_leaves_its_row_and_an_entry_naming_what_moved"),
    audit: audited("test_a_rung_saved_from_the_screen_leaves_its_row_and_an_entry_naming_what_moved"),
    behaviour: t(
      "test_provider_routes",
      "test_a_rung_saved_on_the_routing_screen_is_the_rung_the_next_call_walks",
      true,
    ),
  },
  "POST /api/v1/routing/golden-questions": {
    row: t("test_routing_routes", "test_a_golden_question_is_recorded_only_as_a_principal_the_directory_holds"),
    audit: {
      none: "A golden question is a check the matrix gate asks and is logged, not written to the audit ledger; the changes it holds are recorded in ops.routing_change.",
      leaf: "M5.6.2",
    },
    behaviour: t("test_matrix_gate", "test_a_change_that_stops_the_ladder_answering_is_held_with_the_failing_question_shown"),
  },
  "POST /api/v1/routing/golden-questions/{question_id}/retire": {
    row: t("test_routing_routes", "test_a_retired_golden_question_is_marked_retired_and_asked_no_more"),
    audit: {
      none: "Retiring a golden question is logged, not written to the audit ledger.",
      leaf: "M5.6.2",
    },
    behaviour: t("test_matrix_gate", "test_a_gate_with_no_golden_questions_holds_the_change_and_says_to_record_some"),
  },
  "POST /api/v1/routing/rungs": {
    row: t("test_routing_routes", "test_a_rung_is_added_at_the_end_of_its_tier_only_through_the_gate"),
    audit: audited("test_a_rung_saved_from_the_screen_leaves_its_row_and_an_entry_naming_what_moved"),
    behaviour: t("test_model_calls", "test_a_provider_added_from_the_console_answers_through_the_ladder_with_no_release"),
  },
  "PUT /api/v1/models/providers/{provider}/terms": {
    row: t("test_provider_registry_routes", "test_terms_recorded_for_a_built_in_provider_write_its_first_registry_row"),
    audit: {
      none: "A provider's terms are logged and not written to the audit ledger in this release.",
      leaf: "M5.6.4",
    },
    behaviour: t(
      "test_model_calls",
      "test_a_constrained_call_skips_an_undocumented_rung_for_the_documented_one_behind_it",
    ),
  },
  "POST /api/v1/models/providers/{provider}/retire": {
    row: t("test_provider_registry_routes", "test_an_added_provider_is_retired_and_a_built_in_one_cannot_be"),
    audit: {
      none: "Retiring an added provider is logged and not written to the audit ledger in this release.",
      leaf: "M5.6.4",
    },
    behaviour: t("test_model_assembly", "test_a_provider_with_no_driver_is_told_which_of_the_two_things_is_missing"),
  },
  "POST /api/v1/models/providers": {
    row: t("test_provider_registry_routes", "test_an_added_provider_has_its_key_kept_in_its_own_slot_before_its_row_is_written"),
    audit: t("test_credential_routes", "test_a_key_set_from_the_console_is_recorded_as_its_setter_with_their_reach_and_trace"),
    behaviour: t("test_model_calls", "test_a_provider_added_from_the_console_answers_through_the_ladder_with_no_release"),
  },
  "PUT /api/v1/models/tiers/{tier}": {
    row: t("test_model_health_routes", "test_a_tier_rule_is_written_as_the_window_and_only_the_keys_the_router_reads"),
    audit: {
      none: "A tier's numbers are logged and not written to the audit ledger in this release.",
      leaf: "M5.2.2",
    },
    behaviour: t("test_model_calls", "test_a_request_is_classified_against_the_tier_table_the_ladder_read"),
  },
  "POST /api/v1/models/tiers/{tier}/reset": {
    row: t("test_model_health_routes", "test_a_reset_retires_the_row_so_the_tier_runs_at_the_product_default"),
    audit: {
      none: "Resetting a tier is logged and not written to the audit ledger in this release.",
      leaf: "M5.2.2",
    },
    behaviour: t("test_tier_rules", "test_a_tier_with_no_row_runs_at_the_compiled_numbers_and_is_not_marked_configured"),
  },
  "POST /api/v1/models/residency": {
    row: t("test_model_health_routes", "test_a_residency_constraint_is_written_with_its_scope_and_regions"),
    audit: {
      none: "A residency constraint is logged and not written to the audit ledger in this release.",
      leaf: "M5.5.1",
    },
    behaviour: t("test_model_calls", "test_a_reach_touching_a_constrained_scope_skips_the_rung_outside_its_regions"),
  },
  "POST /api/v1/models/residency/{constraint_id}/retire": {
    row: t("test_model_health_routes", "test_retiring_a_constraint_marks_it_retired_and_deletes_nothing"),
    audit: {
      none: "Retiring a residency constraint is logged and not written to the audit ledger in this release.",
      leaf: "M5.5.1",
    },
    behaviour: t("test_model_calls", "test_a_reach_with_nowhere_compliant_is_refused_and_one_elsewhere_is_answered"),
  },
  "PUT /api/v1/agents/{agent_id}/model-pin": {
    row: t("test_agent_model_routes", "test_an_administrator_pins_a_model_a_rung_serves_and_it_is_written_to_the_agent"),
    audit: {
      none: "An agent's pin is logged and not written to the audit ledger in this release.",
      leaf: "M5.7.3",
    },
    behaviour: t("test_model_calls", "test_a_pinned_model_is_tried_first_even_from_another_tier"),
  },
  "PUT /api/v1/models/providers/{provider}": {
    row: t("test_model_service", "test_the_stores_read_the_ladder_write_attempts_by_id_and_keep_a_switch", true),
    audit: A_SETTING_ENTRY_NO_TEST_FOLLOWS,
    behaviour: t("test_provider_routes", "test_switching_a_provider_off_takes_its_rungs_out_of_the_next_plan_at_once"),
  },
  "POST /api/v1/models/providers/{provider}/check": {
    row: t("test_provider_routes", "test_a_check_is_one_metered_call_recorded_on_the_ledger_and_never_as_a_question"),
    audit: { notApplicable: "A check changes no setting and no record an administrator manages; it is a metered call on the request ledger, not a change to audit." },
    behaviour: t("test_provider_routes", "test_a_check_is_one_metered_call_recorded_on_the_ledger_and_never_as_a_question"),
  },
  "POST /api/v1/govern/grants/removal": {
    row: GRANTS_PRESSED,
    audit: GRANTS_PRESSED,
    behaviour: GRANTS_PRESSED,
  },
  "POST /api/v1/govern/grants": {
    row: GRANTS_PRESSED,
    audit: GRANTS_PRESSED,
    behaviour: GRANTS_PRESSED,
  },
  "POST /api/v1/govern/data-steward": {
    row: t(
      "test_data_steward_routes",
      "test_an_administrator_names_themselves_steward_over_http_once_and_is_told_why_not_twice",
      true,
    ),
    audit: t("test_data_steward", "test_every_steward_grant_leaves_a_ledger_entry_naming_who_made_it", true),
    behaviour: t(
      "test_data_steward",
      "test_a_steward_named_at_setup_grants_a_source_s_read_on_and_the_administrator_cannot",
      true,
    ),
  },
  "POST /api/v1/govern/prompts/{agent_id}": {
    row: INSTRUCTIONS_PRESSED,
    audit: INSTRUCTIONS_PRESSED,
    behaviour: INSTRUCTIONS_PRESSED,
  },
  "POST /api/v1/govern/prompts/{agent_id}/give-back": {
    row: INSTRUCTIONS_PRESSED,
    audit: INSTRUCTIONS_PRESSED,
    behaviour: INSTRUCTIONS_PRESSED,
  },
  "POST /api/v1/govern/retention/release": {
    row: t("test_retention_store", "test_a_release_names_the_newest_report_and_is_withdrawn_by_being_marked", true),
    audit: t("test_retention_audit", "test_each_retention_write_the_console_makes_appends_one_entry_naming_its_own_actor", true),
    behaviour: t("test_worker_schedule", "test_a_released_sweep_is_started_to_act_and_a_withdrawn_one_to_report", true),
  },
  "POST /api/v1/govern/retention/withdrawal": {
    row: t("test_retention_store", "test_a_release_names_the_newest_report_and_is_withdrawn_by_being_marked", true),
    audit: t("test_retention_audit", "test_each_retention_write_the_console_makes_appends_one_entry_naming_its_own_actor", true),
    behaviour: t("test_worker_schedule", "test_a_released_sweep_is_started_to_act_and_a_withdrawn_one_to_report", true),
  },
  "POST /api/v1/govern/legal-holds": {
    row: t("test_retention_store", "test_a_hold_is_placed_lifted_once_and_kept", true),
    audit: t("test_retention_audit", "test_each_retention_write_the_console_makes_appends_one_entry_naming_its_own_actor", true),
    behaviour: HOLDS_SWEPT,
  },
  "POST /api/v1/govern/legal-holds/lift": {
    row: t("test_retention_store", "test_a_hold_is_placed_lifted_once_and_kept", true),
    audit: t("test_retention_audit", "test_each_retention_write_the_console_makes_appends_one_entry_naming_its_own_actor", true),
    behaviour: HOLDS_SWEPT,
  },
  "POST /api/v1/govern/erasures": {
    row: t("test_erasure_store", "test_a_request_is_filed_in_the_sessions_own_name_once_per_open_person_and_never_finished", true),
    audit: t("test_erasure_store", "test_a_request_is_filed_in_the_sessions_own_name_once_per_open_person_and_never_finished", true),
    behaviour: t("test_erasure_store", "test_the_queue_carries_a_request_out_and_writes_what_each_store_did_and_what_it_could_not", true),
  },
  "POST /api/v1/govern/sessions/end": {
    row: t("test_session_store", "test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request", true),
    audit: t("test_session_store", "test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request", true),
    behaviour: t("test_session_store", "test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request", true),
  },
  // Several endings are the single ending's store call once per session, which the route test holds;
  // what that call writes, records and refuses is the single ending's database proof.
  "POST /api/v1/govern/sessions/end-several": {
    row: t("test_session_routes", "test_several_sessions_are_ended_one_at_a_time_each_decided_by_the_single_endings_question"),
    audit: t("test_session_store", "test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request", true),
    behaviour: t("test_session_store", "test_ending_a_session_writes_the_row_the_ledger_entry_and_refuses_the_next_request", true),
  },
  "POST /api/v1/sign-ins": {
    row: t("test_sign_in_binding", "test_binding_the_same_subject_twice_writes_one_row", true),
    audit: t("test_sign_in_routes", "test_an_administrators_binding_is_in_the_ledger_naming_them_their_reach_and_the_request", true),
    behaviour: t("test_sign_in_binding", "test_a_valid_token_is_refused_until_its_subject_is_bound_and_accepted_after", true),
  },
  "POST /api/v1/govern/sign-ins/unlink": {
    row: t("test_sign_in_links", "test_an_unlink_retires_the_link_names_who_did_it_and_the_account_is_refused_after", true),
    audit: t("test_sign_in_links", "test_an_unlink_retires_the_link_names_who_did_it_and_the_account_is_refused_after", true),
    behaviour: t("test_sign_in_links", "test_an_unlink_retires_the_link_names_who_did_it_and_the_account_is_refused_after", true),
  },
  "POST /api/v1/webhooks/subscribers": {
    row: t("test_webhook_routes", "test_a_registration_is_written_with_the_reader_as_its_creator_and_its_secret_kept"),
    audit: WEBHOOK_LEDGER,
    behaviour: A_WEBHOOK_IS_DELIVERED,
  },
  "PUT /api/v1/credentials/{family}/{name}": {
    row: t("test_credential_routes", "test_setting_a_key_writes_the_slot_and_answers_that_it_is_held_and_when"),
    audit: t("test_credential_routes", "test_a_key_set_from_the_console_is_recorded_as_its_setter_with_their_reach_and_trace"),
    behaviour: t("test_credentials", "test_a_key_kept_here_is_handed_to_this_process_unless_the_environment_outranks_it"),
  },
  "POST /api/v1/webhooks/subscribers/{subscriber_id}/secret": {
    row: t("test_webhook_routes", "test_replacing_a_secret_writes_the_new_one_and_a_switched_off_subscriber_is_refused"),
    audit: WEBHOOK_LEDGER,
    behaviour: t("test_webhook_delivery", "test_the_worker_reads_the_secret_at_the_path_the_console_writes_it_to"),
  },
  "POST /api/v1/webhooks/subscribers/{subscriber_id}/switch-off": {
    row: t("test_webhook_routes", "test_switching_off_records_who_did_it_and_a_second_switch_off_is_refused"),
    audit: WEBHOOK_LEDGER,
    behaviour: t("test_webhook_store", "test_registering_replacing_and_switching_off_reach_the_rows_and_the_fan_out", true),
  },
  "POST /api/v1/notifications/notices/{kind}": {
    row: t("test_notification_routes", "test_switching_a_notice_off_writes_its_row_with_the_writer_and_the_next_read_sees_it"),
    audit: A_SETTING_ENTRY_NO_TEST_FOLLOWS,
    behaviour: t("test_notices", "test_switched_off_a_re_verification_run_records_nothing_and_switched_on_it_does", true),
  },
  "POST /api/v1/notifications/relay": {
    row: t("test_notification_routes", "test_a_relay_is_saved_as_five_rows_with_its_writer_and_read_back_configured"),
    audit: A_SETTING_ENTRY_NO_TEST_FOLLOWS,
    behaviour: t("test_notification_routes", "test_a_test_message_reaches_the_saved_relay_once_with_the_kept_password"),
  },
  "POST /api/v1/notifications/relay/password": {
    row: t("test_notification_routes", "test_a_password_is_kept_at_its_slot_recorded_and_never_answered"),
    audit: t("test_notification_routes", "test_a_password_is_kept_at_its_slot_recorded_and_never_answered"),
    behaviour: t("test_notification_routes", "test_a_test_message_reaches_the_saved_relay_once_with_the_kept_password"),
  },
  "POST /api/v1/notifications/relay/test": {
    row: t("test_mail", "test_pressing_the_test_button_twice_sends_one_message"),
    audit: NO_TRIAL_LEDGER,
    behaviour: t("test_notification_routes", "test_a_test_message_reaches_the_saved_relay_once_with_the_kept_password"),
  },
  "POST /api/v1/skills": {
    row: t("test_skill_store", "test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store", true),
    audit: t("test_skill_store", "test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store", true),
    behaviour: t("test_skill_routes", "test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent"),
  },
  "POST /api/v1/skills/{digest}/review": {
    row: t("test_skill_store", "test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store", true),
    audit: t("test_skill_store", "test_an_import_and_a_decision_each_write_one_row_and_one_entry_through_the_store", true),
    behaviour: t("test_skill_routes", "test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent"),
  },
  "POST /api/v1/skills/{digest}/assignments": {
    row: t("test_skill_routes", "test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent"),
    audit: t("test_skill_store", "test_the_database_refuses_a_decision_by_the_importer_and_an_assignment_nobody_approved", true),
    behaviour: t("test_skill_routes", "test_an_administrator_adds_a_skill_a_second_person_approves_it_and_it_is_assigned_to_an_agent"),
  },
  "POST /api/v1/agents/{agent_id}/automations": {
    row: t("test_automation_gallery_routes", "test_one_confirmed_request_writes_the_automation_its_registry_entry_and_its_audit_context"),
    audit: t("test_agent_automation_store", "test_an_install_writes_one_row_one_ledger_entry_and_a_second_install_writes_neither", true),
    behaviour: t("test_automation_gallery_routes", "test_one_confirmed_request_writes_the_automation_its_registry_entry_and_its_audit_context"),
  },
  "POST /api/v1/agents/{agent_id}/automations/{automation_id}/start": {
    row: t("test_automation_run_store", "test_the_console_starts_and_stops_as_the_application_role_and_the_ledger_says_who", true),
    audit: t("test_automation_run_store", "test_the_console_starts_and_stops_as_the_application_role_and_the_ledger_says_who", true),
    behaviour: t("test_automation_schedule_routes", "test_a_confirmed_start_is_written_as_the_approver_and_a_stale_one_writes_nothing"),
  },
  "POST /api/v1/agents/{agent_id}/automations/{automation_id}/stop": {
    row: t("test_automation_run_store", "test_the_console_starts_and_stops_as_the_application_role_and_the_ledger_says_who", true),
    audit: t("test_automation_run_store", "test_the_console_starts_and_stops_as_the_application_role_and_the_ledger_says_who", true),
    behaviour: t("test_automation_schedule_routes", "test_the_owner_stops_their_own_without_approval_and_a_bystander_cannot"),
  },
  "POST /api/v1/govern/roles/appointment": {
    row: ROLES_PRESSED,
    audit: ROLES_PRESSED,
    behaviour: t("test_role_grant", "test_the_last_two_super_admins_cannot_be_reduced_to_one"),
  },
  "POST /api/v1/govern/roles/deputy": {
    row: t("test_role_grant", "test_the_guard_keeps_deputies_depth_one_and_the_table_keeps_them_bounded", true),
    audit: ROLES_PRESSED,
    behaviour: t("test_role_grant", "test_a_deputy_covers_a_standing_holder_and_never_another_deputy"),
  },
  "POST /api/v1/govern/roles/removal": {
    row: ROLES_PRESSED,
    audit: ROLES_PRESSED,
    behaviour: t("test_role_grant", "test_the_guard_refuses_a_removal_below_the_floor_and_allows_one_above_it", true),
  },
  "POST /api/v1/govern/roles/group-rules": {
    row: GROUP_RULES_PRESSED,
    audit: GROUP_RULES_PRESSED,
    behaviour: t("test_group_sync", "test_a_sign_in_writes_and_removes_synced_rows_and_the_ledger_records_both", true),
  },
  "POST /api/v1/govern/roles/group-rules/retirement": {
    row: GROUP_RULES_PRESSED,
    audit: GROUP_RULES_PRESSED,
    behaviour: GROUP_RULES_PRESSED,
  },
  "POST /api/v1/govern/packs/assignment": {
    row: t("test_govern_pack_routes", "test_an_assignment_reaches_the_row_the_ledger_and_the_resolver", true),
    audit: t("test_govern_pack_routes", "test_an_assignment_reaches_the_row_the_ledger_and_the_resolver", true),
    behaviour: t("test_govern_pack_routes", "test_an_assignment_reaches_the_row_the_ledger_and_the_resolver", true),
  },
  "POST /api/v1/audit/verification": {
    row: { notApplicable: "Walking the ledger reads it and writes nothing." },
    audit: { notApplicable: "A verification changes nothing, so there is nothing to record." },
    behaviour: t("test_chain_check", "test_a_truncated_ledger_is_reported_through_the_route"),
  },
  "POST /api/v1/requirements/checks": {
    row: t("test_requirement_check_routes", "test_the_store_keeps_every_check_and_reads_back_the_newest_per_requirement", true),
    audit: {
      none: "A check is an append-only row attributed to the person who recorded it, and is not written to the ledger: brain.tables.requirement_check argues why.",
    },
    behaviour: t(
      "test_requirement_check_routes",
      "test_a_check_is_recorded_as_the_person_asking_on_the_running_release_and_read_back",
    ),
  },
  "PUT /api/v1/govern/compliance/topics/{topic}": {
    row: A_PERSON_NAMED_FOR_A_TOPIC,
    audit: A_PERSON_NAMED_FOR_A_TOPIC,
    behaviour: t("test_compliance_routes", "test_a_sensitive_question_is_routed_to_the_person_named_for_its_topic"),
  },
  "POST /api/v1/govern/compliance/breaches": BREACH_STEP,
  "POST /api/v1/govern/compliance/breaches/{case_id}/assessment": BREACH_STEP,
  "POST /api/v1/govern/compliance/breaches/{case_id}/commission": BREACH_STEP,
  "POST /api/v1/govern/compliance/breaches/{case_id}/individuals": BREACH_STEP,
  "POST /api/v1/govern/compliance/breaches/{case_id}/exception": BREACH_STEP,
  "POST /api/v1/govern/compliance/breaches/{case_id}/close": BREACH_STEP,
  "POST /api/v1/me/referrals/{referral_id}/handled": {
    row: t("test_compliance_store", "test_a_referral_is_filed_without_content_and_read_only_by_its_person", true),
    audit: {
      none: "Marking a referral handled writes handled_at and handled_by on its row and no ledger entry: an entry that only a sensitive question writes is the disclosure brain.audit.compliance.intercept argues against.",
    },
    behaviour: t("test_compliance_routes", "test_a_referral_marked_handled_is_shown_handled"),
  },
};

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

/** The whole document, deterministically. */
export function renderAudit(measured: Measured): string {
  const lines: string[] = [];
  const areaNames = Object.keys(AREAS);
  const gapCount = areaNames.reduce((sum, name) => sum + (AREAS[name]?.gaps.length ?? 0), 0);
  const unreached = measured.routes.filter(
    (route) => (measured.readBy[route] ?? []).length === 0 && (measured.writtenBy[route] ?? []).length === 0,
  );
  const writeRoutes = Object.keys(PROOFS).sort();
  const proved = writeRoutes.filter((route) => {
    const one = PROOFS[route];
    return one !== undefined && [one.row, one.audit, one.behaviour].every((proof) => !("none" in proof));
  });
  const withoutDatabase = proved.filter((route) => {
    const one = PROOFS[route];
    return one !== undefined && [one.row, one.audit, one.behaviour].every((proof) => !("test" in proof) || !proof.database);
  });

  lines.push("# The console audit");
  lines.push("");
  lines.push(
    "What an administrator would need to manage, read out of the schema, the routes and the installation values, compared with what the console serves, screen by screen, with every gap either linked to its open leaf or recorded with its reason. It is the audit `docs/admin-console.md` asks for before the console is called done.",
  );
  lines.push("");
  lines.push(
    "**This page is generated and must not be edited by hand.** `console/tests/console-audit.test.ts` renders it from `console/tests/support/consoleAudit.ts` and fails when this file differs. To regenerate it after a change, run `npm run api:generate` and then `WRITE_CONSOLE_AUDIT=1 npx vitest run tests/console-audit.test.ts` in `console/`.",
  );
  lines.push("");
  lines.push("## What was measured");
  lines.push("");
  lines.push(`- ${String(areaNames.length)} areas, the bullets of \`docs/admin-console.md\` in its order.`);
  lines.push(`- ${String(measured.tables.length)} tables, from \`brain.db.Base.metadata\`.`);
  lines.push(`- ${String(measured.installation.length)} installation values, from \`brain.install.INSTALLATION\`.`);
  lines.push(`- ${String(measured.routes.length)} routes under \`/api/v1\` and \`/setup\`, from the API's internal document.`);
  lines.push(`- ${String(measured.screens.length)} console addresses, from the route table in \`console/src/App.tsx\`.`);
  lines.push(
    `- ${String(measured.writeCount)} calls in the console that send a write, from \`console/tests/support/writes.ts\`, reaching ${String(writeRoutes.length)} routes.`,
  );
  lines.push(`- ${String(gapCount)} gaps recorded, and ${String(unreached.length)} routes no screen calls.`);
  lines.push("");

  lines.push("## Area by area");
  lines.push("");
  for (const name of areaNames) {
    const area = AREAS[name];
    if (area === undefined) {
      continue;
    }
    const routes = measured.routes.filter((route) => area.routes.some((claim) => claims(claim, route)));
    lines.push(`### ${name}`);
    lines.push("");
    lines.push(`- **Screens:** ${area.screens.length === 0 ? "none" : area.screens.map(code).join(", ")}`);
    lines.push(`- **Tables:** ${area.tables.length === 0 ? "none" : area.tables.map(code).join(", ")}`);
    lines.push(`- **Installation values:** ${area.installation.length === 0 ? "none" : area.installation.map(code).join(", ")}`);
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
  }

  lines.push("## Not administered here");
  lines.push("");
  lines.push("| What | Why it is not a gap |");
  lines.push("| --- | --- |");
  for (const [what, why] of Object.entries(NOT_ADMINISTERED).sort(([a], [b]) => a.localeCompare(b))) {
    lines.push(`| ${code(what)} | ${cellSafe(why)} |`);
  }
  lines.push("");

  lines.push("## Every write the console sends, followed to the system");
  lines.push("");
  lines.push(
    `Leaf \`M27.8.17\`: a write is followed to the row it writes, to the audit entry it leaves, and to the behaviour it changes. ${String(proved.length)} of ${String(writeRoutes.length)} write routes have all three proved or not applicable, ${String(withoutDatabase.length)} of those without a live database. Every other row below says what is missing and why. A test marked database runs against a scratch Postgres, which CI provides and this machine does not.`,
  );
  lines.push("");
  lines.push("| Write | Called by | Row | Audit entry | Behaviour |");
  lines.push("| --- | --- | --- | --- | --- |");
  for (const route of writeRoutes) {
    const one = PROOFS[route];
    if (one === undefined) {
      continue;
    }
    const callers = (measured.writtenBy[route] ?? []).map(code).join(", ");
    lines.push(
      `| ${code(route)} | ${callers || "**no screen**"} | ${cellSafe(proofCell(one.row))} | ${cellSafe(proofCell(one.audit))} | ${cellSafe(proofCell(one.behaviour))} |`,
    );
  }
  lines.push("");

  lines.push("## The rules every screen is held to");
  lines.push("");
  lines.push(
    "- **Loading, empty, unreachable and failed** are four different sentences on every registered address: `console/tests/screen-states.test.tsx`, with the addresses excused and why in `console/tests/support/screenStateRules.tsx`.",
  );
  lines.push(
    "- **A destructive write is confirmed**, and the confirmation names what and says what will happen: `console/tests/destructive-confirmed.test.ts`, with the writes that are not destructive and why.",
  );
  lines.push(
    "- **A form that writes is judged before it sends**, and a blank one says what to fill in: `console/tests/validated-before-write.test.tsx`.",
  );
  lines.push(
    "- **Long lists page, search, filter and sort** through one convention, `brain.listing`, over the rows the reader may see, and a filter offers only values on rows drawn: `console/tests/long-lists.test.tsx` measures every long list against its route and records what each does not offer with its reason. Ending several sessions and deciding several review holdings are bulk acts, each item decided by the single act's own check.",
  );
  lines.push("");
  return `${lines.join("\n")}`;
}
