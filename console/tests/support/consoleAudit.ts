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
import { automationStartApiPath, automationStopApiPath } from "../../src/pages/agentAutomationsQuery";
import { automationInstallApiPath, automationPreviewApiPath } from "../../src/pages/automationGalleryQuery";
import { approvalDecisionApiPath } from "../../src/pages/approvalsQuery";
import { historyApiPath } from "../../src/pages/auditQuery";
import { UNDO_API_PATH } from "../../src/pages/learningQuery";
import { reviewApiPath } from "../../src/pages/classificationQuery";
import { assignPath, reviewPath, SKILLS_API_PATH } from "../../src/pages/skillsQuery";
import { EXPORTS_API_PATH } from "../../src/pages/dataTransferQuery";
import { switchPath } from "../../src/pages/featuresQuery";
import {
  ELEVATION_REQUESTS_API_PATH,
  LEAD_API_PATH,
  MEMBERSHIP_API_PATH,
  REVIEW_DECISION_API_PATH,
  elevationDecisionApiPath,
} from "../../src/pages/governPeopleQuery";
import { GRANTS_API_PATH, REMOVAL_API_PATH } from "../../src/pages/governQuery";
import { actionPath } from "../../src/pages/jobsQuery";
import { rungApiPath } from "../../src/pages/matrixQuery";
import { providerCheckApiPath, providerSwitchApiPath } from "../../src/pages/modelsQuery";
import { editPath, giveBackPath } from "../../src/pages/promptsQuery";
import {
  ERASURES_API_PATH,
  HOLD_API_PATH,
  LIFT_API_PATH,
  RELEASE_API_PATH,
  WITHDRAWAL_API_PATH,
} from "../../src/pages/retentionQuery";
import { END_SESSION_API_PATH } from "../../src/pages/sessionsQuery";
import { LINK_API_PATH, UNLINK_API_PATH } from "../../src/pages/signInLinksQuery";
import { TRIAL_API_PATH } from "../../src/pages/staffSourcesQuery";
import { CONNECTORS_API_PATH, disconnectApiPath } from "../../src/pages/connectorsQuery";
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
    screens: ["/", "/people", "/people/:subject", "/roles", "/capabilities", "/scopes", "/access_review", "/elevation", "/sessions", "/sign-in-links", "/staff_sources"],
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
      "/api/v1/govern/staff_sources*",
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
    ],
    installation: [
      "INSTALL_OIDC_ISSUER",
      "INSTALL_OIDC_REALM",
      "INSTALL_OIDC_CLIENT_ID",
      "INSTALL_OIDC_REDIRECT_URIS",
      "INSTALL_BROKERED_DIRECTORY",
      "INSTALL_STAFF_SOURCE",
      "INSTALL_STAFF_SOURCE_LOCATION",
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
        what: "Nobody is sent a notice when somebody asks for an elevation or is given one.",
        because:
          "The people to tell are the standing Super Admins, and no table records who holds a role (M1.3.2), so brain.console.elevation.client_recipients has nobody to compute; the audit ledger is the record, and the Elevation requests screen says so.",
      },
      { what: "The identity provider and the staff source cannot be changed after setup.", because: ONCE_BY_THE_WIZARD },
    ],
  },
  "Departments, teams and client configuration": {
    screens: ["/departments", "/department"],
    routes: ["/api/v1/govern/departments*"],
    tables: ["gate.department", "gate.team", "gate.team_membership", "gate.department_lead"],
    installation: ["INSTALL_COMPANY_NAME", "INSTALL_PRODUCT_NAME", "INSTALL_LOGO_URL", "INSTALL_ACCENT_COLOUR"],
    gaps: [
      {
        what: "A department or a team cannot be created, renamed or removed.",
        because: "No route and no module under src/brain writes gate.department or gate.team, so the screen places people in the teams that are there and leads the departments that are there, and there is no writer to call for the rest.",
      },
      {
        what: "Nothing applies the staff list's teams and leads on a schedule.",
        because: "brain.identity.organisation_sync plans them and brain.identity.organisation_store applies a plan, and no job runs either, which is true of the whole staff sync: dry_run is read by the Staff sources screen and nothing applies a roster.",
      },
      { what: "The company's name, product name, logo and accent cannot be changed after setup.", because: ONCE_BY_THE_WIZARD },
    ],
  },
  "System settings and application configuration": {
    screens: ["/install", "/limits", "/connections", "/first-run", "/first-run/staff-list"],
    routes: ["/api/v1/install", "/api/v1/install/limits", "/api/v1/install/capacity", "/setup/*"],
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
    routes: ["/api/v1/operate/models", "/api/v1/models/providers*", "/api/v1/routing/rungs*"],
    tables: ["ops.routing_rung", "ops.routing_tier", "ops.model_attempt"],
    installation: ["INSTALL_MODEL_PROFILE", "INSTALL_MODEL_ENDPOINT", "INSTALL_EMBEDDING_DIMENSIONS"],
    gaps: [
      {
        what: "Saving a routing rung changes the chain the next model call walks and no answer: the answer lane still answers from fast-path rules and calls no model, so today only a provider check from Models and health reaches a saved rung.",
        leaf: "M27.8.8",
      },
      { what: "A provider key cannot be written or replaced from a screen after setup.", leaf: "M27.8.8" },
      { what: "The model profile and endpoint cannot be changed after setup.", because: ONCE_BY_THE_WIZARD },
    ],
  },
  "Agents and their configuration, including templates": {
    screens: ["/agents", "/agents/:agentId", "/agents/:agentId/:tab", "/agent-templates", "/approvals", "/approvals/:suspensionId"],
    routes: ["/api/v1/agents", "/api/v1/agents/{agent_id}/workspace", "/api/v1/agent-templates", "/api/v1/approvals*"],
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
      {
        what: "An approval decided on a running install is refused: the application builds no suspension store without a ledger writer, so every approval route answers with the process fault.",
        because: "brain.app.suspension_store_for passes no ledger, deliberately, until a writer for obs.audit_entry survives a restart; tests/unit/test_approval_decisions.py holds that the lifespan builds none.",
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
    routes: ["/api/v1/connectors", "/api/v1/connectors/{connector}/disconnect"],
    tables: [
      "ops.connector_connection",
      "ops.connector_sync",
      "proj.record",
      "er.alias",
      "er.canonical",
      "er.identifier",
      "er.link",
    ],
    installation: [],
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
        what: "Freshdesk, Google Drive, the Laravel views, Lark Base and Lark Wiki cannot be connected from a screen.",
        because:
          "Each needs a visibility rule, a department declaration or a key file the form cannot collect, which brain.ops.connectable.NOT_FROM_THE_CONSOLE says for each.",
      },
    ],
  },
  "API keys, credentials and secrets, held in the vault and never displayed": {
    screens: ["/webhooks"],
    routes: ["/api/v1/credentials*"],
    tables: ["ops.credential_write"],
    installation: [],
    gaps: [
      {
        what: "GET /api/v1/credentials and PUT /api/v1/credentials/{family}/{name} are served, and no screen calls either.",
        leaf: "M27.8.8",
      },
    ],
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
    screens: ["/audit"],
    routes: ["/api/v1/audit*"],
    tables: ["obs.audit_entry"],
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
    screens: ["/recovery", "/retention"],
    routes: [
      "/api/v1/install/recovery",
      "/api/v1/govern/retention*",
      "/api/v1/govern/legal-holds*",
      "/api/v1/govern/erasures",
    ],
    tables: ["ops.retention_release", "ops.retention_report", "obs.legal_hold", "ops.erasure_request"],
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
    tables: [],
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

function at(route: string, spelled: string, built: string, versioned = true): WriteRoute {
  return { route, spelled, built, versioned };
}

export const WRITE_ROUTES: Readonly<Record<string, readonly WriteRoute[]>> = {
  "src/pages/Learning.tsx UNDO_API_PATH": [at("POST /api/v1/govern/learning/undo", "UNDO_API_PATH", UNDO_API_PATH)],
  "src/pages/Departments.tsx asked.path": [
    at("POST /api/v1/govern/departments/membership", "MEMBERSHIP_API_PATH", MEMBERSHIP_API_PATH),
    at("POST /api/v1/govern/departments/lead", "LEAD_API_PATH", LEAD_API_PATH),
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
  "src/pages/Approvals.tsx approvalDecisionApiPath(suspensionId)": [
    at("POST /api/v1/approvals/{suspension_id}/decision", "approvalDecisionApiPath", approvalDecisionApiPath("sus-1")),
  ],
  "src/pages/Ask.tsx ANSWER_API_PATH": [at("POST /api/v1/answer", "ANSWER_API_PATH", ANSWER_API_PATH)],
  "src/pages/Classification.tsx reviewApiPath(entity, row.column)": [
    at("POST /api/v1/classifications/{entity}/columns/{column}/review", "reviewApiPath", reviewApiPath("price_list", "cost")),
  ],
  "src/pages/DataTransfer.tsx EXPORTS_API_PATH": [at("POST /api/v1/data-transfer/exports", "EXPORTS_API_PATH", EXPORTS_API_PATH)],
  "src/pages/Features.tsx switchPath(row.name)": [at("POST /api/v1/install/features/{name}", "switchPath", switchPath("schedule_control"))],
  "src/pages/FirstRun.tsx FINISH_PATH": [at("POST /setup/sign-in", "FINISH_PATH", FINISH_PATH, false)],
  "src/pages/FirstRun.tsx APPOINTMENT_PATH": [at("POST /setup/appointment", "APPOINTMENT_PATH", APPOINTMENT_PATH, false)],
  "src/components/StaffListCheck.tsx SIGN_IN_PATH": [
    at("POST /setup/staff-source/sign-in", "SIGN_IN_PATH", STAFF_LIST_SIGN_IN_PATH, false),
  ],
  "src/components/StaffListCheck.tsx TRIAL_PATH": [
    at("POST /setup/staff-source/trial", "TRIAL_PATH", STAFF_LIST_TRIAL_PATH, false),
  ],
  "src/pages/Jobs.tsx actionPath(asked.action, asked.row.control)": [
    at("POST /api/v1/jobs/{name}/pause", "actionPath", actionPath("pause", "spend_report_refresh")),
    at("POST /api/v1/jobs/{name}/resume", "actionPath", actionPath("resume", "spend_report_refresh")),
    at("POST /api/v1/jobs/{name}/run", "actionPath", actionPath("run", "spend_report_refresh")),
  ],
  "src/pages/Matrix.tsx rungApiPath(rung.id)": [at("PATCH /api/v1/routing/rungs/{rung_id}", "rungApiPath", rungApiPath("rung-1"))],
  "src/pages/Models.tsx providerSwitchApiPath(pending.provider)": [
    at("PUT /api/v1/models/providers/{provider}", "providerSwitchApiPath", providerSwitchApiPath("anthropic")),
  ],
  "src/pages/Models.tsx providerCheckApiPath(pending.provider)": [
    at("POST /api/v1/models/providers/{provider}/check", "providerCheckApiPath", providerCheckApiPath("anthropic")),
  ],
  "src/pages/People.tsx REMOVAL_API_PATH": [at("POST /api/v1/govern/grants/removal", "REMOVAL_API_PATH", REMOVAL_API_PATH)],
  "src/pages/People.tsx GRANTS_API_PATH": [at("POST /api/v1/govern/grants", "GRANTS_API_PATH", GRANTS_API_PATH)],
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
const INSTRUCTIONS_PRESSED = audited("test_an_instruction_edit_and_its_give_back_reach_the_install_the_ledger_and_the_prompt");
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
const ELEVATION_REACHES_THE_ROW_THE_LEDGER_AND_THE_RESOLVER = t(
  "test_elevation_store",
  "test_an_approved_elevation_widens_the_requester_and_after_its_lapse_it_does_not",
  true,
);

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
  "POST /api/v1/approvals/{suspension_id}/decision": {
    row: t("test_approval_decisions", "test_an_approver_in_reach_approves_once_and_one_ledger_entry_records_it"),
    audit: t("test_approval_decisions", "test_an_approver_in_reach_approves_once_and_one_ledger_entry_records_it"),
    behaviour: {
      none:
        "In-process the decision leaves the queue (test_approval_decisions.py::test_a_decided_approval_leaves_the_queue_and_its_card_no_longer_opens), but on a running install brain.app.suspension_store_for builds no store, so the decision a person presses is refused and changes nothing.",
    },
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
    row: { notApplicable: "A read of a staff list writes nothing: nobody is added, and the client secret it signs in with is not kept." },
    audit: { notApplicable: "A read changes nothing an administrator manages, so there is nothing to record." },
    behaviour: t("test_setup_staff_routes", "test_a_directory_is_chosen_signed_in_to_and_its_list_pulled"),
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
    "- **Long lists** are measured rather than claimed, and what each does not offer is recorded with its reason: `console/tests/long-lists.test.tsx`. Leaf `M27.8.6` stays open: most routes take a limit and nothing else.",
  );
  lines.push("");
  return `${lines.join("\n")}`;
}
