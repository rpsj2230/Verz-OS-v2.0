/**
 * What the Departments and teams, Elevation, Access review and Subscribers screens ask for, what the
 * review control may send, and how each list narrows. No React.
 *
 * **One query module for four screens, because they are one API surface.** `brain.govern_people_routes`
 * serves all four with one refusal shape and one rule about counts, which is `governQuery.ts`' reason
 * for serving People, Roles, Capabilities and Scopes from one module.
 *
 * **Nothing here decides who may see or change anything.** The organisation is
 * `brain.console.organisation`'s answer, the landing is `brain.console.elevation`'s, the review rows
 * are `brain.console.govern.recertifiable`'s and the subscriber lines are
 * `brain.console.subscribers`'. Every one is computed on the server per request, and this module
 * reads them and decides only what a control looks like. The review route refuses a decision
 * whatever the page drew.
 *
 * **Filters narrow what was shown and offer only what was shown.** See
 * `A_FILTER_OVER_A_PAGE_OFFERS_THE_PAGE`, which is the Sessions screen's rule: a department dropdown
 * read from anywhere but the rows on the page names places this reader was not shown.
 *
 * **No number about the rows.** No reader here keeps a total, and no screen renders a count.
 *
 * Task ids: M27.7.4, M27.7.8, M27.7.9, M27.7.12
 */

import type { components } from "../api/schema";

export type OrganisationBody = components["schemas"]["OrganisationPage"];
export type DepartmentRow = components["schemas"]["DepartmentView"];
export type MemberRow = components["schemas"]["MemberView"];
export type TeamRow = components["schemas"]["TeamView"];
export type UnplacedRow = components["schemas"]["UnplacedView"];
export type ElevationBody = components["schemas"]["ElevationPage"];
export type ElevationRequestRow = components["schemas"]["ElevationRequestView"];
export type ReviewRow = components["schemas"]["ReviewRowView"];
export type SubscriberRow = components["schemas"]["SubscriberView"];

/** Written down because the obvious dropdown lists every department in the company. */
export const A_FILTER_OVER_A_PAGE_OFFERS_THE_PAGE =
  "Every filter on these screens narrows the rows already on the page and offers the values those " +
  "rows carry. A list read from anywhere else would name places or people this reader was not " +
  "shown, which is the listing the rows were narrowed to avoid.";

/** Where the API keeps each screen and the one control. */
export const DEPARTMENTS_API_PATH = "/govern/departments";
export const MEMBERSHIP_API_PATH = "/govern/departments/membership";
export const LEAD_API_PATH = "/govern/departments/lead";
export const ELEVATION_API_PATH = "/govern/elevation";
export const ELEVATION_REQUESTS_API_PATH = "/govern/elevation/requests";
export const REVIEW_API_PATH = "/govern/access-review";
export const REVIEW_DECISION_API_PATH = "/govern/access-review/decision";
export const SUBSCRIBERS_API_PATH = "/govern/subscribers";

/**
 * The console addresses. The review's is the registry key `access_review`, so
 * `brain.ops.console_screens.routed_screen_keys` matches the route against the registry.
 */
export const DEPARTMENTS_PATH = "/departments";
export const ELEVATION_PATH = "/elevation";
export const REVIEW_PATH = "/access_review";
export const SUBSCRIBERS_PATH = "/subscribers";

/** How many rows a listing asks for. At or below the routes' maximum of 1000; see the test. */
export const GOVERN_PEOPLE_PAGE_SIZE = 500;

export function departmentsApiPath(): string {
  return `${DEPARTMENTS_API_PATH}?limit=${String(GOVERN_PEOPLE_PAGE_SIZE)}`;
}

export function elevationApiPath(): string {
  return `${ELEVATION_API_PATH}?limit=${String(GOVERN_PEOPLE_PAGE_SIZE)}`;
}

/** Where one request's decision is sent. The id is the API's, encoded as a path segment. */
export function elevationDecisionApiPath(requestId: string): string {
  return `${ELEVATION_REQUESTS_API_PATH}/${encodeURIComponent(requestId)}/decision`;
}

export function reviewApiPath(): string {
  return `${REVIEW_API_PATH}?limit=${String(GOVERN_PEOPLE_PAGE_SIZE)}`;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

// ------------------------------------------------------------------ departments

export interface Organisation {
  readonly departments: readonly DepartmentRow[];
  readonly unplaced: readonly UnplacedRow[];
  readonly truncated: boolean;
  /** Whether this reader holds the authority to place anybody. Presentation only. */
  readonly mayOrganise: boolean;
  /** The sentences about what the page shows and who may change it, in the API's words. */
  readonly teams: string;
  readonly leads: string;
  readonly counted: string;
  readonly organising: string;
}

const NO_ORGANISATION: Organisation = Object.freeze({
  departments: [],
  unplaced: [],
  truncated: false,
  mayOrganise: false,
  teams: "",
  leads: "",
  counted: "",
  organising: "",
});

/** Read `brain.govern_people_routes.OrganisationPage` out of a response body. */
export function readOrganisation(payload: unknown): Organisation {
  if (!isObject(payload) || !Array.isArray(payload.departments)) {
    return NO_ORGANISATION;
  }
  return {
    departments: payload.departments as DepartmentRow[],
    unplaced: Array.isArray(payload.unplaced) ? (payload.unplaced as UnplacedRow[]) : [],
    truncated: payload.truncated === true,
    mayOrganise: payload.may_organise === true,
    teams: text(payload.teams),
    leads: text(payload.leads),
    counted: text(payload.counted),
    organising: text(payload.organising),
  };
}

/** The body of a placement, as `MembershipChange` declares it. Four keys and no fifth. */
export interface MembershipBody {
  readonly department: string;
  readonly team: string;
  readonly principal_id: string;
  readonly change: "join" | "leave";
}

export function membershipBody(
  department: string,
  team: string,
  principalId: string,
  change: MembershipBody["change"],
): MembershipBody {
  return { department, team, principal_id: principalId, change };
}

/** The body of a lead change, as `LeadChange` declares it: a person to appoint, or nobody. */
export type LeadBody =
  | { readonly department: string; readonly change: "appoint"; readonly principal_id: string }
  | { readonly department: string; readonly change: "stand_down" };

export function appointBody(department: string, principalId: string): LeadBody {
  return { department, change: "appoint", principal_id: principalId };
}

export function standDownBody(department: string): LeadBody {
  return { department, change: "stand_down" };
}

/** The question a placement's confirmation asks, naming the person and the team. */
export function membershipQuestion(teamName: string, person: string, change: MembershipBody["change"]): string {
  return change === "join" ? `Add ${person} to ${teamName}?` : `Take ${person} out of ${teamName}?`;
}

/** The question a lead change's confirmation asks, naming the person and the department. */
export function leadQuestion(departmentName: string, person: string, change: LeadBody["change"]): string {
  return change === "appoint"
    ? `Appoint ${person} to lead ${departmentName}?`
    : `Stand ${person} down as lead of ${departmentName}?`;
}

/** The people of a department who are not already in a team, by name, for the add control. */
export function teamCandidates(department: DepartmentRow, team: TeamRow): readonly MemberRow[] {
  const inside = new Set((team.members ?? []).map((one) => one.principal_id));
  return department.members.filter((one) => !one.disabled && !inside.has(one.principal_id));
}

/** The people of a department who could be appointed its lead: live, and not the lead already. */
export function leadCandidates(department: DepartmentRow): readonly MemberRow[] {
  const current = department.lead?.principal_id;
  return department.members.filter((one) => !one.disabled && one.principal_id !== current);
}

/**
 * The departments and people a search leaves, in the order the API sent them.
 *
 * A department stays when its name or slug matches, with everybody in it; otherwise it stays with
 * the people whose name or id matches, and it goes when none do. Case does not matter. The search
 * narrows what was shown and asks the API nothing.
 */
export function searchedOrganisation(
  departments: readonly DepartmentRow[],
  search: string,
): readonly DepartmentRow[] {
  const wanted = search.trim().toLowerCase();
  if (wanted === "") {
    return departments;
  }
  const hit = (value: string) => value.toLowerCase().includes(wanted);
  const kept: DepartmentRow[] = [];
  for (const department of departments) {
    if (hit(department.name) || hit(department.slug)) {
      kept.push(department);
      continue;
    }
    const members = department.members.filter((one) => hit(one.display_name) || hit(one.principal_id));
    if (members.length > 0) {
      kept.push({ ...department, members });
    }
  }
  return kept;
}

/** The People and grants address for one person, where their entitlement is. */
export function personAddress(principalId: string): string {
  return `/people/${encodeURIComponent(`principal:${principalId}`)}`;
}

// ------------------------------------------------------------------ elevation

/** Read `brain.govern_people_routes.ElevationPage`, or null when the body is not one. */
export function readElevation(payload: unknown): ElevationBody | null {
  if (!isObject(payload) || typeof payload.prompt !== "string" || !Array.isArray(payload.reasons)) {
    return null;
  }
  return payload as unknown as ElevationBody;
}

/** A reason code as a person reads it: `incident_response` becomes "incident response". */
export function reasonWords(reason: string): string {
  return reason.replaceAll("_", " ");
}

/** What a request asks for, as `ElevationAsked` declares it. Five keys and no sixth. */
export interface ElevationAsk {
  readonly capability: string;
  readonly scope_slug: string;
  readonly reason: string;
  readonly explanation: string;
  readonly hours: number;
}

/** The sentences a blank request is answered with, before anything is sent, by field. */
export const ASK_BLANKS: Readonly<Record<"capability" | "scope_slug" | "reason" | "explanation", string>> =
  Object.freeze({
    capability: "Name the capability you need, such as read:client.name.",
    scope_slug: "Name the scope you need it over, as the Scopes screen spells it.",
    reason: "Choose why you need it.",
    explanation: "Say what you need it for, so whoever decides can judge it.",
  });

/** The fields of a request left blank, in the form's order. Shape is the API's to judge. */
export function askBlanks(ask: ElevationAsk): readonly (keyof typeof ASK_BLANKS)[] {
  return (["capability", "scope_slug", "reason", "explanation"] as const).filter(
    (field) => ask[field].trim() === "",
  );
}

/** The two decisions, as `ElevationDecision` declares them. */
export const ELEVATION_DECISIONS = ["approved", "denied"] as const;
export type ElevationDecisionWord = (typeof ELEVATION_DECISIONS)[number];

/** What each state is called on the page. */
export const STATE_WORDS: Readonly<Record<ElevationRequestRow["state"], string>> = Object.freeze({
  pending: "Waiting for a decision",
  denied: "Denied",
  live: "Given, until it lapses",
  lapsed: "Lapsed",
  ended: "Ended before it lapsed",
});

/** The question a decision's confirmation asks, naming the person, the capability and the hours. */
export function elevationQuestion(row: ElevationRequestRow, decision: ElevationDecisionWord): string {
  const who = row.display_name ?? row.principal_id;
  const verb = decision === "approved" ? "Give" : "Refuse";
  return `${verb} ${who} ${row.capability} over ${row.scope_slug} for ${String(row.hours)} hours?`;
}

/** The question the request's confirmation asks. */
export function askQuestion(ask: ElevationAsk): string {
  return `Ask for ${ask.capability} over ${ask.scope_slug} for ${String(ask.hours)} hours?`;
}

// ------------------------------------------------------------------ access review

export interface Review {
  readonly rows: readonly ReviewRow[];
  readonly truncated: boolean;
  readonly shows: string;
  readonly keeping: string;
  readonly removing: string;
}

const NO_REVIEW: Review = Object.freeze({
  rows: [],
  truncated: false,
  shows: "",
  keeping: "",
  removing: "",
});

/** Read `brain.govern_people_routes.ReviewPage` out of a response body. */
export function readReview(payload: unknown): Review {
  if (!isObject(payload) || !Array.isArray(payload.items)) {
    return NO_REVIEW;
  }
  return {
    rows: payload.items as ReviewRow[],
    truncated: payload.truncated === true,
    shows: text(payload.shows),
    keeping: text(payload.keeping),
    removing: text(payload.removing),
  };
}

/** The two decisions, as the route's `Decision` declares them. */
export const DECISIONS = ["keep", "remove"] as const;
export type ReviewDecisionWord = (typeof DECISIONS)[number];

/** The body of one decision, as `ReviewDecisionAsked` declares it. Three keys and no fourth. */
export interface ReviewDecisionBody {
  readonly kind: ReviewRow["kind"];
  readonly row_id: string;
  readonly decision: ReviewDecisionWord;
}

export function decisionBody(row: ReviewRow, decision: ReviewDecisionWord): ReviewDecisionBody {
  return { kind: row.kind, row_id: row.row_id, decision };
}

/** How far back a decision still counts as recent, for the one filter that asks. */
export const RECENT_DAYS = 90;

/** What a reviewer narrowed the rows to. Empty strings are unset. */
export interface ReviewFilters {
  readonly department: string;
  readonly person: string;
  /** "" for every row, "never" for never decided, "stale" for not decided in `RECENT_DAYS`. */
  readonly decided: "" | "never" | "stale";
}

export const NO_REVIEW_FILTERS: ReviewFilters = Object.freeze({ department: "", person: "", decided: "" });

/** The departments on these rows, each once, in name order. */
export function reviewDepartments(rows: readonly ReviewRow[]): readonly string[] {
  return [...new Set(rows.map((row) => row.department ?? "").filter((one) => one !== ""))].sort();
}

/** The people on these rows, each once, by name. */
export function reviewPeople(rows: readonly ReviewRow[]): readonly { id: string; name: string }[] {
  const seen = new Map<string, string>();
  for (const row of rows) {
    seen.set(row.principal_id, row.display_name ?? row.principal_id);
  }
  return [...seen.entries()]
    .map(([id, name]) => ({ id, name }))
    .sort((a, b) => a.name.localeCompare(b.name) || a.id.localeCompare(b.id));
}

/** The rows these filters keep, in the order the API sent them. `now` is a parameter, not a clock. */
export function narrowedReview(rows: readonly ReviewRow[], filters: ReviewFilters, now: Date): readonly ReviewRow[] {
  const cutoff = now.getTime() - RECENT_DAYS * 24 * 60 * 60 * 1000;
  return rows.filter((row) => {
    if (filters.department !== "" && (row.department ?? "") !== filters.department) {
      return false;
    }
    if (filters.person !== "" && row.principal_id !== filters.person) {
      return false;
    }
    if (filters.decided === "never") {
      return row.last_decided_at === null;
    }
    if (filters.decided === "stale") {
      return row.last_decided_at === null || new Date(row.last_decided_at).getTime() < cutoff;
    }
    return true;
  });
}

/** What a holding is called in a sentence: its capability, or its pack by name. */
export function holdingName(row: ReviewRow): string {
  return row.pack === null ? (row.capabilities[0] ?? "") : `the ${row.pack} pack`;
}

/** The question the confirmation asks, naming the person and the grant. */
export function decisionQuestion(row: ReviewRow, decision: ReviewDecisionWord): string {
  const who = row.display_name ?? row.principal_id;
  return decision === "keep"
    ? `Keep ${holdingName(row)} for ${who}?`
    : `Remove ${holdingName(row)} from ${who}?`;
}

// ------------------------------------------------------------------ subscribers

export interface Subscribers {
  readonly rows: readonly SubscriberRow[];
  readonly findings: readonly string[];
  readonly kinds: readonly string[];
  readonly stopping: string;
  readonly scope: string;
  readonly told: string;
}

const NO_SUBSCRIBERS: Subscribers = Object.freeze({
  rows: [],
  findings: [],
  kinds: [],
  stopping: "",
  scope: "",
  told: "",
});

/** Read `brain.govern_people_routes.SubscribersPage` out of a response body. */
export function readSubscribers(payload: unknown): Subscribers {
  if (!isObject(payload) || !Array.isArray(payload.items)) {
    return NO_SUBSCRIBERS;
  }
  return {
    rows: payload.items as SubscriberRow[],
    findings: Array.isArray(payload.findings) ? (payload.findings as string[]) : [],
    kinds: Array.isArray(payload.kinds) ? (payload.kinds as string[]) : [],
    stopping: text(payload.stopping),
    scope: text(payload.scope),
    told: text(payload.told),
  };
}

/** The rows a kind filter and an active filter keep. "" is every kind; "active" or "off". */
export function narrowedSubscribers(
  rows: readonly SubscriberRow[],
  kind: string,
  state: "" | "active" | "off",
): readonly SubscriberRow[] {
  return rows.filter(
    (row) =>
      (kind === "" || row.kinds.includes(kind)) &&
      (state === "" || (state === "active") === row.active),
  );
}

/** An instant, as the rows show it. */
export function when(value: string | null): string {
  if (value === null) {
    return "";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
