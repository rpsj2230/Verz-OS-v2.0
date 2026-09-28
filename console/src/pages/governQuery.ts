/**
 * What the Roles and permissions screens ask the API for, and the rules about what may be sent back.
 * No React.
 *
 * Until 2026-09-29 this module also carried the old People screen's grant-holder listing and its
 * schema-form grants. The People pages were rebuilt on the page kit over the directory of every
 * person (`people/peopleQuery.ts`), and the grant forms became plain fields there, so that half is
 * gone; the three sentences below are kept because the new pages keep their rules.
 *
 * **Nothing here decides who may see what.** The request is identical for every caller, the API
 * answers from grants this browser never receives, and a refusal comes back as a value rendered in
 * the API's own words. See `A_HIDDEN_CONTROL_IS_NOT_A_REFUSAL`.
 *
 * **No screen here renders a number about its own rows.** Every listing behind them is filtered
 * per caller, so "showing 3" is the subtraction `CLAUDE.md` forbids rather than a footer.
 *
 * Task ids: M27.7.4, M27.7.5, M27.7.6, M27.11.3, M1.3.2, M1.1.5, M1.8.4
 */

import type { components } from "../api/schema";
import type { FilterChoice, SortChoice } from "../components/listing";

/** One of the six roles, as `RoleView` sends it. */
export type RoleRow = components["schemas"]["RoleView"];
/** One registered capability and what it reaches, as `CapabilityView` sends it. */
export type CapabilityRow = components["schemas"]["CapabilityView"];
/** One named scope, predicate included, as `ScopeView` sends it. */
export type ScopeRowView = components["schemas"]["ScopeView"];

/**
 * Written down because an empty capability list on a person is the one thing on these screens
 * that a reader will want explained, and explaining it is the disclosure.
 */
export const AN_EMPTY_CAPABILITY_LIST_MEANS_TWO_THINGS_AND_SAYS_NEITHER =
  "A person's row comes back with no capabilities both when they hold none and when this " +
  "reader may not be told what they hold, and there is no field saying which. That is " +
  "brain.console.govern's decision and this console must not undo it by rendering a lock, a " +
  "dash with a tooltip, or a sentence under the table: every one of those says this subject " +
  "holds something, which is the disclosure the withholding was for. An empty cell here means " +
  "what an empty cell means everywhere else in this console, which is that there was nothing " +
  "to show.";

/**
 * Written down because hiding a control is presentation and looks exactly like enforcement.
 */
export const A_HIDDEN_CONTROL_IS_NOT_A_REFUSAL =
  "`editable` comes from the API, on the response, recomputed for every request. It decides " +
  "whether the grant form and the removal controls are drawn and it decides nothing else: " +
  "every write is refused or accepted by the route whatever this file believed. A console " +
  "that skipped a request because the flag was false would be enforcing a rule in the copy an " +
  "attacker edits, and one that trusted the flag to mean a write will succeed would be " +
  "holding a permission model with no way to know it had gone stale.";

/**
 * Written down because a free-text box for a predicate is the obvious next feature request.
 */
export const A_SCOPE_IS_CHOSEN_BY_NAME_AND_NEVER_TYPED =
  "The grant form offers the scope slugs the Scopes screen answered this reader, and there is " +
  "no box for a predicate. Two reasons and the second is the one that matters. A predicate " +
  "typed into a form is one nobody named, so the review that reads it later has a clause list " +
  "and no word for it. And the offered list is a listing the API already narrowed, so what a " +
  "grantor can choose from is something they have been shown rather than something they " +
  "invent. It narrows nothing on its own: the route refuses a scope wider than the grantor's " +
  "whatever this form offered, and a slug from another install is refused there too.";

/** Where the API keeps each screen. */
export const ROLES_API_PATH = "/govern/roles";
export const CAPABILITIES_API_PATH = "/govern/capabilities";
export const SCOPES_API_PATH = "/govern/scopes";

/** Where a person's page begins, for the addresses built from a literal first segment. */
export const PEOPLE_PATH = "/people";

/**
 * A console address under People, from a constant prefix and an encoded key.
 *
 * GHSA-wrjc-x8rr-h8h6 is an open redirect through a backslash reaching `useNavigate`, it covers
 * every react-router this project can install, and the defence is that the address starts with a
 * literal path segment and the rest is encoded. `skillsQuery` and `memoryQuery` build theirs the
 * same way for the same reason.
 */
export function subjectAddress(subject: string): string {
  return `${PEOPLE_PATH}/${encodeURIComponent(subject)}`;
}

/** The filters the scopes route declares that this screen offers, over values on rows drawn. */
export const SCOPE_FILTERS: readonly FilterChoice<ScopeRowView>[] = [
  {
    column: "is_department",
    label: "Kind",
    everything: "Every scope",
    read: (row) => row.is_department,
    describe: (value) => (value === "true" ? "A department's own" : "Named"),
  },
];

export const SCOPE_SORTS: readonly SortChoice[] = [
  { value: "", label: "By short name" },
  { value: "label", label: "By name" },
];

/** Read `brain.govern_routes.RoleCatalogue` out of a response body. */
export function readRoles(payload: unknown): readonly RoleRow[] {
  if (typeof payload !== "object" || payload === null) {
    return [];
  }
  const roles = (payload as { roles?: unknown }).roles;
  return Array.isArray(roles) ? (roles as RoleRow[]) : [];
}

/** Read `brain.govern_routes.CapabilityCatalogue` out of a response body. */
export function readCapabilities(payload: unknown): readonly CapabilityRow[] {
  if (typeof payload !== "object" || payload === null) {
    return [];
  }
  const found = (payload as { capabilities?: unknown }).capabilities;
  return Array.isArray(found) ? (found as CapabilityRow[]) : [];
}

// ------------------------------------------------- the Approver flag (M1.8.4)

export const MISCONFIGURATIONS_API_PATH = "/govern/roles/misconfigurations";

/** One person whose Approver role and approve permission disagree. */
export interface MisconfigurationRow {
  readonly principal_id: string;
  readonly kind: string;
  readonly sentence: string;
}

export function readMisconfigurations(payload: unknown): readonly MisconfigurationRow[] {
  if (typeof payload !== "object" || payload === null) {
    return [];
  }
  const found = (payload as { items?: unknown }).items;
  return Array.isArray(found) ? (found as MisconfigurationRow[]) : [];
}

// ------------------------------------------------- role holders (M1.3.2, M1.3.3, M1.8.7)

export const HOLDERS_API_PATH = "/govern/roles/holders";
export const APPOINTMENT_API_PATH = "/govern/roles/appointment";
export const DEPUTY_API_PATH = "/govern/roles/deputy";
export const ROLE_REMOVAL_API_PATH = "/govern/roles/removal";

/** The six roles, as the route's `Role` enum spells them. */
export const ROLE_VALUES = [
  "super_admin",
  "department_admin",
  "member",
  "auditor",
  "connector_admin",
  "approver",
] as const;

/** The longest a deputy may run, `brain.identity.roles.DEPUTY_MAX`. */
export const DEPUTY_DAYS = 30;

// ------------------------------------------------- directory group mapping (M1.1.5)

export const GROUP_RULES_API_PATH = "/govern/roles/group-rules";
export const GROUP_RULE_RETIREMENT_API_PATH = "/govern/roles/group-rules/retirement";

/** One group-to-role rule as `GET /api/v1/govern/roles/group-rules` answers it. */
export interface GroupRuleRow {
  readonly id: string;
  readonly idp_group: string;
  readonly role: string;
  readonly created_by: string;
  readonly created_at: string;
}

/** One role the sync wrote from somebody's group membership. */
export interface SyncedRow {
  readonly principal_id: string;
  readonly role: string;
  readonly source_group: string;
  readonly first_seen_at: string;
  readonly last_seen_at: string;
}

export interface GroupRulesPage {
  readonly rules: readonly GroupRuleRow[];
  readonly synced: readonly SyncedRow[];
  readonly editable: boolean;
}

export function readGroupRules(payload: unknown): GroupRulesPage {
  if (typeof payload !== "object" || payload === null) {
    return { rules: [], synced: [], editable: false };
  }
  const found = payload as { rules?: unknown; synced?: unknown; editable?: unknown };
  return {
    rules: Array.isArray(found.rules) ? (found.rules as GroupRuleRow[]) : [],
    synced: Array.isArray(found.synced) ? (found.synced as SyncedRow[]) : [],
    editable: found.editable === true,
  };
}
