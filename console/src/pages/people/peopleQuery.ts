/**
 * What the People pages ask the API and read out of its answers: the directory of every person, one
 * person's page, and the bodies of the writes made from them.
 *
 * **Every person, not every grant holder.** The old People screen listed `GET /govern/people`,
 * which is built from grant rows, so somebody holding nothing was on no list and could not be
 * granted anything from this console. `GET /govern/directory` lists every person the reader may be
 * shown (`brain.console.organisation.nameable` over where each sits), grant or none.
 *
 * **Read as sent, and absent as absent.** Every reader here carries a field only when the body gave
 * it in the declared shape, and a row without an id or a name is not drawn, which is
 * `agents/AgentsPage.readAgentRows`' rule. A figure the API did not send is not invented: the second
 * factor and the last sign-in are null both when nothing recorded them and when the reader may not
 * be told, and the page draws the two the same way.
 *
 * **No total reaches a component.** A `total` on the wire has no field to land in.
 *
 * Task ids: M27.11.2, M27.11.3, M27.15.18, M27.16.1
 */

import { listPath, NO_QUESTION, type FilterChoice, type SortChoice } from "../../components/listing";

// ------------------------------------------------------------------------------ addresses

/** The directory of every person, and where a person is added by hand. */
export const DIRECTORY_API_PATH = "/govern/directory";

/** One person's page, under the API base. */
export function personApiPath(principalId: string): string {
  return `${DIRECTORY_API_PATH}/${encodeURIComponent(principalId)}`;
}

/** Where a person's work email is added (`brain.directory_routes.WORK_EMAIL_PATH`, M1.10.4). */
export function workEmailApiPath(principalId: string): string {
  return `${personApiPath(principalId)}/work-email`;
}

export const GRANTS_API_PATH = "/govern/grants";
export const REMOVAL_API_PATH = "/govern/grants/removal";
export const SEVERAL_GRANTS_API_PATH = "/govern/grants/several";
export const PACKS_API_PATH = "/govern/packs";
export const PACK_ASSIGNMENT_API_PATH = "/govern/packs/assignment";
/** A pack is taken away by the access review's decision, which retires the assignment. */
export const REVIEW_DECISION_API_PATH = "/govern/access-review/decision";
export const DISABLE_API_PATH = "/govern/people/disable";
export const ENABLE_API_PATH = "/govern/people/enable";
export const SESSIONS_API_PATH = "/govern/sessions";
export const END_SESSION_API_PATH = "/govern/sessions/end";
export const END_SESSIONS_API_PATH = "/govern/sessions/end-several";
export const SIGN_INS_API_PATH = "/govern/sign-ins";
export const UNLINK_API_PATH = "/govern/sign-ins/unlink";
export const HOLDERS_API_PATH = "/govern/roles/holders";
export const AGENTS_API_PATH = "/agents";
export const TRANSFERS_API_PATH = "/govern/staff_sources/transfers";
export const HISTORY_API_PATH = "/audit/history";
export const SCOPES_API_PATH = "/govern/scopes";
export const CAPABILITIES_API_PATH = "/govern/capabilities";
export const ME_API_PATH = "/me";

/** Taking over a leaver's agent. The reader becomes its steward. */
export function transferApiPath(agentId: string): string {
  return `${TRANSFERS_API_PATH}/${encodeURIComponent(agentId)}`;
}

/** The most one list request may carry, which the routes' `limit` allows. */
export const ONE_PAGE = 50;

/** The scope choices a grant form offers: the Scopes screen's own answer to this reader. */
export const SCOPE_CHOICES = 200;

/** A list route asked about one person by its `principal_id` (or another) filter. */
export function aboutPerson(path: string, column: string, principalId: string, size: number = ONE_PAGE): string {
  return listPath(path, { ...NO_QUESTION, filters: { [column]: principalId } }, null, size);
}

export function scopeChoicesApiPath(): string {
  return listPath(SCOPES_API_PATH, NO_QUESTION, null, SCOPE_CHOICES);
}

/** One person's history in the ledger, oldest first, as `brain.audit_routes.audit_history` reads it. */
export function historyApiPath(principalId: string): string {
  const query = new URLSearchParams({ subject_kind: "principal", subject_id: principalId });
  return `${HISTORY_API_PATH}?${query.toString()}`;
}

// ------------------------------------------------------------------------------ console addresses

export const PEOPLE_ADDRESS = "/people";

/** The views of one person's page, in order. The first is the bare address. */
export const PERSON_VIEWS = ["overview", "access", "grants", "sessions", "placements", "history"] as const;
export type PersonView = (typeof PERSON_VIEWS)[number];

export const PERSON_VIEW_LABELS: Readonly<Record<PersonView, string>> = Object.freeze({
  overview: "Overview",
  access: "Access",
  grants: "Grants",
  sessions: "Sign-ins",
  placements: "Placements",
  history: "History",
});

/**
 * One person's page, or one view of it. A literal first segment and an encoded id, for
 * `governQuery.subjectAddress`' reason: the address starts with a path segment nobody typed.
 */
export function personAddress(principalId: string, view: PersonView = "overview"): string {
  const base = `${PEOPLE_ADDRESS}/${encodeURIComponent(principalId)}`;
  return view === "overview" ? base : `${base}/${view}`;
}

/** The view an address names. An address naming anything else opens the Overview, saying nothing. */
export function viewNamed(segment: string | undefined): PersonView {
  return PERSON_VIEWS.find((one) => one === segment) ?? "overview";
}

/**
 * The person an address names. The old People screen's addresses carried `principal:<id>`, and a
 * link somebody saved from it still opens the same person.
 */
export function principalFromAddress(segment: string): string {
  return segment.startsWith("principal:") ? segment.slice("principal:".length) : segment;
}

// ------------------------------------------------------------------------------ reading

type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(value: unknown): Fields | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  // A cast at the boundary, where proving a structural match buys nothing: every field is read
  // back through one of the readers below.
  return value as Fields;
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function listOf(value: unknown): readonly unknown[] {
  return Array.isArray(value) ? (value as readonly unknown[]) : [];
}

function words(value: unknown): readonly string[] {
  return listOf(value)
    .map(said)
    .filter((one): one is string => one !== undefined);
}

/** One person on the directory, as `brain.directory_routes.DirectoryPersonView` sends one. */
export interface PersonRow {
  readonly principalId: string;
  readonly displayName: string;
  readonly department?: string;
  readonly departmentName?: string;
  readonly employment?: string;
  readonly standing: "live" | "disabled";
  /** True or false only when a session recorded it and the reader may be told. */
  readonly secondFactor?: boolean;
  readonly lastSignedInAt?: string;
  readonly packs: readonly string[];
  /** Where the staff list says they stand, when a list is read and names them (M1.6.13). */
  readonly staffStatus?: string;
  /** The employment type the staff list records, when it records one. */
  readonly employmentType?: string;
}

export function readPerson(value: unknown): PersonRow | null {
  const entry = fieldsOf(value);
  const principalId = said(entry?.["principal_id"]);
  const displayName = said(entry?.["display_name"]);
  if (entry === null || principalId === undefined || displayName === undefined) {
    return null;
  }
  const department = said(entry["department"]);
  const departmentName = said(entry["department_name"]);
  const employment = said(entry["employment"]);
  const lastSignedInAt = said(entry["last_signed_in_at"]);
  const secondFactor = entry["second_factor"];
  const staffStatus = said(entry["staff_status"]);
  const employmentType = said(entry["employment_type"]);
  return {
    principalId,
    displayName,
    ...(department === undefined ? {} : { department }),
    ...(departmentName === undefined ? {} : { departmentName }),
    ...(employment === undefined ? {} : { employment }),
    standing: entry["standing"] === "disabled" ? "disabled" : "live",
    ...(typeof secondFactor === "boolean" ? { secondFactor } : {}),
    ...(lastSignedInAt === undefined ? {} : { lastSignedInAt }),
    packs: words(entry["packs"]),
    ...(staffStatus === undefined ? {} : { staffStatus }),
    ...(employmentType === undefined ? {} : { employmentType }),
  };
}

/** The directory's rows out of a body: each once, in the order sent, and only those that name somebody. */
export function readPeople(payload: unknown): readonly PersonRow[] {
  const seen = new Set<string>();
  const rows: PersonRow[] = [];
  for (const item of listOf(fieldsOf(payload)?.["items"])) {
    const row = readPerson(item);
    if (row === null || seen.has(row.principalId)) {
      continue;
    }
    seen.add(row.principalId);
    rows.push(row);
  }
  return rows;
}

/** What the directory's first page says about the reader and the page. Presentation only. */
export interface DirectoryFacts {
  readonly editable: boolean;
  readonly mayDisable: boolean;
  readonly mayAdd: boolean;
  readonly adding?: string;
  readonly disabling?: string;
  /** With a staff list read: the sentence to pass on to somebody whose account the sync made. */
  readonly accountReady?: string;
}

export function readDirectoryFacts(payload: unknown): DirectoryFacts {
  const body = fieldsOf(payload);
  const adding = said(body?.["adding"]);
  const disabling = said(body?.["disabling"]);
  const accountReady = said(body?.["account_ready"]);
  return {
    editable: body?.["editable"] === true,
    mayDisable: body?.["may_disable"] === true,
    mayAdd: body?.["may_add"] === true,
    ...(adding === undefined ? {} : { adding }),
    ...(disabling === undefined ? {} : { disabling }),
    ...(accountReady === undefined ? {} : { accountReady }),
  };
}

/** Where a person sits, as `PlacementView` sends it. */
export interface Placements {
  readonly department?: { readonly slug: string; readonly name: string };
  readonly teams: readonly { readonly department: string; readonly slug: string; readonly name: string }[];
  readonly leads: readonly { readonly slug: string; readonly name: string }[];
}

/** One thing a person holds: a direct grant or a pack, as `HeldView` sends it. */
export interface Held {
  readonly kind: "grant" | "pack";
  readonly rowId: string;
  readonly capabilities: readonly string[];
  readonly pack?: string;
  readonly packLabel?: string;
  readonly packVersion?: number;
  readonly scopeSlug?: string;
  readonly scopeLabel?: string;
  readonly scope: unknown;
  readonly grantedBy?: string;
  readonly grantedByName?: string;
  readonly reason?: string;
  readonly grantedAt?: string;
  readonly notAfter?: string;
}

/** One person's page, as `PersonDetail` sends it. */
export interface PersonDetail {
  readonly person: PersonRow;
  readonly placements: Placements;
  readonly held: readonly Held[];
  readonly editable: boolean;
  readonly mayDisable: boolean;
  readonly mayOrganise: boolean;
  readonly disabling?: string;
  readonly fromAPack?: string;
  /** Why the staff list keeps them from signing in or asking, in the API's words (M1.6.14). */
  readonly keptOut?: string;
  /** Whether this reader may add their work email (M1.10.4). */
  readonly mayAddWorkEmail: boolean;
}

function readPlacements(value: unknown): Placements {
  const fields = fieldsOf(value);
  const department = fieldsOf(fields?.["department"]);
  const departmentSlug = said(department?.["slug"]);
  const departmentName = said(department?.["name"]);
  const teams = listOf(fields?.["teams"])
    .map(fieldsOf)
    .flatMap((one) => {
      const slug = said(one?.["slug"]);
      const name = said(one?.["name"]);
      const within = said(one?.["department"]);
      return slug === undefined || name === undefined || within === undefined ? [] : [{ department: within, slug, name }];
    });
  const leads = listOf(fields?.["leads"])
    .map(fieldsOf)
    .flatMap((one) => {
      const slug = said(one?.["slug"]);
      const name = said(one?.["name"]);
      return slug === undefined || name === undefined ? [] : [{ slug, name }];
    });
  return {
    ...(departmentSlug === undefined || departmentName === undefined
      ? {}
      : { department: { slug: departmentSlug, name: departmentName } }),
    teams,
    leads,
  };
}

function readHeld(value: unknown): Held | null {
  const entry = fieldsOf(value);
  const kind = entry?.["kind"];
  const rowId = said(entry?.["row_id"]);
  const capabilities = words(entry?.["capabilities"]);
  if (entry === null || (kind !== "grant" && kind !== "pack") || rowId === undefined || capabilities.length === 0) {
    return null;
  }
  const optional: Record<string, string> = {};
  for (const [key, from] of [
    ["pack", "pack"],
    ["packLabel", "pack_label"],
    ["scopeSlug", "scope_slug"],
    ["scopeLabel", "scope_label"],
    ["grantedBy", "granted_by"],
    ["grantedByName", "granted_by_name"],
    ["reason", "reason"],
    ["grantedAt", "granted_at"],
    ["notAfter", "not_after"],
  ] as const) {
    const one = said(entry[from]);
    if (one !== undefined) {
      optional[key] = one;
    }
  }
  const version = entry["pack_version"];
  return {
    kind,
    rowId,
    capabilities,
    scope: entry["scope"],
    ...optional,
    ...(typeof version === "number" ? { packVersion: version } : {}),
  };
}

export function readPersonDetail(payload: unknown): PersonDetail | null {
  const body = fieldsOf(payload);
  const person = readPerson(body?.["person"]);
  if (body === null || person === null) {
    return null;
  }
  const disabling = said(body["disabling"]);
  const fromAPack = said(body["from_a_pack"]);
  const keptOut = said(body["kept_out"]);
  return {
    person,
    placements: readPlacements(body["placements"]),
    held: listOf(body["held"])
      .map(readHeld)
      .filter((one): one is Held => one !== null),
    editable: body["editable"] === true,
    mayDisable: body["may_disable"] === true,
    mayOrganise: body["may_organise"] === true,
    mayAddWorkEmail: body["may_add_work_email"] === true,
    ...(disabling === undefined ? {} : { disabling }),
    ...(fromAPack === undefined ? {} : { fromAPack }),
    ...(keptOut === undefined ? {} : { keptOut }),
  };
}

/** A grant from an elevation, which the route writes with a reason naming the request. */
export function fromElevation(held: Held): boolean {
  return held.kind === "grant" && (held.reason ?? "").startsWith("elevation ");
}

// ------------------------------------------------------------------------------ the list's controls

export const STANDING_WORDS: Readonly<Record<string, string>> = Object.freeze({ live: "Live", disabled: "Disabled" });

/** Where the staff list says somebody stands, as `brain.identity.staff_source.EmploymentStatus`. */
export const STAFF_STATUS_WORDS: Readonly<Record<string, string>> = Object.freeze({
  active: "Active",
  suspended: "Suspended",
  left: "Left",
  not_activated: "Not activated",
});

/** The employment types the staff list records, as `brain.identity.staff_source.EmploymentType`. */
export const EMPLOYMENT_TYPE_WORDS: Readonly<Record<string, string>> = Object.freeze({
  regular: "Regular",
  intern: "Intern",
  outsourced: "Outsourced",
  labour_dispatch: "Labour dispatch",
  consultant: "Consultant",
  contractor: "Contractor",
  other: "Other",
});

export const PEOPLE_FILTERS: readonly FilterChoice<PersonRow>[] = [
  {
    column: "department",
    label: "Department",
    everything: "All departments",
    read: (row) => row.department,
  },
  {
    column: "standing",
    label: "Standing",
    everything: "Any standing",
    read: (row) => row.standing,
    describe: (value) => STANDING_WORDS[value] ?? value,
  },
  {
    column: "staff_status",
    label: "On the staff list",
    everything: "Any status",
    read: (row) => row.staffStatus,
    describe: (value) => STAFF_STATUS_WORDS[value] ?? value,
  },
  {
    column: "employment_type",
    label: "Employment type",
    everything: "Any type",
    read: (row) => row.employmentType,
    describe: (value) => EMPLOYMENT_TYPE_WORDS[value] ?? value,
  },
  {
    column: "second_factor",
    label: "Second factor",
    everything: "Any sign-in",
    read: (row) => row.secondFactor,
    describe: (value) => (value === "true" ? "Seen" : "Not seen"),
  },
];

export const PEOPLE_SORTS: readonly SortChoice[] = [
  { value: "", label: "Name" },
  { value: "department", label: "Department" },
  { value: "-last_signed_in_at", label: "Last sign-in" },
];

// ------------------------------------------------------------------------------ other reads

/** One live session of a person, from the Sessions screen's own route. */
export interface SessionRow {
  readonly sessionId: string;
  readonly secondFactor: boolean;
  readonly signedInAt?: string;
  readonly lapsesAt?: string;
  readonly yours: boolean;
  readonly endable: boolean;
}

export function readSessions(payload: unknown, principalId: string): readonly SessionRow[] {
  return listOf(fieldsOf(payload)?.["items"])
    .map(fieldsOf)
    .flatMap((one) => {
      const sessionId = said(one?.["session_id"]);
      if (one === null || sessionId === undefined || one["principal_id"] !== principalId) {
        return [];
      }
      const signedInAt = said(one["signed_in_at"]);
      const lapsesAt = said(one["lapses_at"]);
      return [
        {
          sessionId,
          secondFactor: one["second_factor"] === true,
          ...(signedInAt === undefined ? {} : { signedInAt }),
          ...(lapsesAt === undefined ? {} : { lapsesAt }),
          yours: one["yours"] === true,
          endable: one["endable"] === true,
        },
      ];
    });
}

/** A person's sign-in link, from the Sign-in links screen's own route. */
export interface LinkRow {
  readonly linkedAt?: string;
  readonly lastAdministrator: boolean;
  readonly yours: boolean;
}

export function readLink(payload: unknown, principalId: string): LinkRow | null {
  for (const one of listOf(fieldsOf(payload)?.["items"]).map(fieldsOf)) {
    if (one !== null && one["principal_id"] === principalId) {
      const linkedAt = said(one["linked_at"]);
      return {
        ...(linkedAt === undefined ? {} : { linkedAt }),
        lastAdministrator: one["last_administrator"] === true,
        yours: one["yours"] === true,
      };
    }
  }
  return null;
}

/** A role a person holds, from the Roles screen's holders route. */
export interface RoleHeld {
  readonly id: string;
  readonly role: string;
  readonly deputyOf?: string;
  readonly notAfter?: string;
  readonly scope: unknown;
}

export function readRolesHeld(payload: unknown, principalId: string): readonly RoleHeld[] {
  return listOf(fieldsOf(payload)?.["items"])
    .map(fieldsOf)
    .flatMap((one) => {
      const id = said(one?.["id"]);
      const role = said(one?.["role"]);
      if (one === null || id === undefined || role === undefined || one["principal_id"] !== principalId) {
        return [];
      }
      const deputyOf = said(one["deputy_of"]);
      const notAfter = said(one["not_after"]);
      return [
        {
          id,
          role,
          scope: one["scope"],
          ...(deputyOf === undefined ? {} : { deputyOf }),
          ...(notAfter === undefined ? {} : { notAfter }),
        },
      ];
    });
}

/** An agent a person stewards, from the roster filtered by owner. */
export interface OwnedAgent {
  readonly agentId: string;
  readonly displayName: string;
  readonly state?: string;
}

export function readOwnedAgents(payload: unknown, principalId: string): readonly OwnedAgent[] {
  return listOf(fieldsOf(payload)?.["items"])
    .map(fieldsOf)
    .flatMap((one) => {
      const agentId = said(one?.["agent_id"]);
      const displayName = said(one?.["display_name"]);
      if (one === null || agentId === undefined || displayName === undefined || one["owner_id"] !== principalId) {
        return [];
      }
      const state = said(one["state"]);
      return [{ agentId, displayName, ...(state === undefined ? {} : { state }) }];
    });
}

/** A leaver's agent this reader may take on, from the staff source's transfers route. */
export interface Waiting {
  readonly agentId: string;
  readonly displayName: string;
  readonly running: boolean;
}

export function readWaiting(payload: unknown, principalId: string): readonly Waiting[] {
  return listOf(fieldsOf(payload)?.["transfers"])
    .map(fieldsOf)
    .flatMap((one) => {
      const agentId = said(one?.["agent_id"]);
      const displayName = said(one?.["display_name"]);
      if (one === null || agentId === undefined || displayName === undefined || one["owner_id"] !== principalId) {
        return [];
      }
      return [{ agentId, displayName, running: one["running"] === true }];
    });
}

/** One entry of a person's history. */
export interface HistoryEvent {
  readonly at: string;
  readonly action: string;
  readonly actorId: string;
  readonly details: Readonly<Record<string, unknown>>;
}

export function readHistory(payload: unknown): { readonly events: readonly HistoryEvent[]; readonly full: boolean } {
  const body = fieldsOf(payload);
  const events = listOf(body?.["events"])
    .map(fieldsOf)
    .flatMap((one) => {
      const at = said(one?.["at"]);
      const action = said(one?.["action"]);
      const actorId = said(one?.["actor_id"]);
      if (one === null || at === undefined || action === undefined || actorId === undefined) {
        return [];
      }
      return [{ at, action, actorId, details: fieldsOf(one["details"]) ?? {} }];
    });
  return { events, full: body?.["full"] === true };
}

/** One pack a grantor may assign. */
export interface PackChoice {
  readonly slug: string;
  readonly label: string;
  readonly capabilities: readonly string[];
}

export function readPackChoices(payload: unknown): readonly PackChoice[] {
  return listOf(fieldsOf(payload)?.["packs"])
    .map(fieldsOf)
    .flatMap((one) => {
      const slug = said(one?.["slug"]);
      if (one === null || slug === undefined) {
        return [];
      }
      return [{ slug, label: said(one["label"]) ?? slug, capabilities: words(one["capabilities"]) }];
    });
}

/** One scope a grant may be bounded by: its short name and its label. */
export interface ScopeChoice {
  readonly slug: string;
  readonly label: string;
}

export function readScopeChoices(payload: unknown): readonly ScopeChoice[] {
  return listOf(fieldsOf(payload)?.["items"])
    .map(fieldsOf)
    .flatMap((one) => {
      const slug = said(one?.["slug"]);
      return one === null || slug === undefined ? [] : [{ slug, label: said(one["label"]) ?? slug }];
    });
}

/** The capabilities the vocabulary offers, for the grant form's suggestions. */
export function readVocabulary(payload: unknown): readonly string[] {
  return listOf(fieldsOf(payload)?.["capabilities"])
    .map(fieldsOf)
    .map((one) => said(one?.["capability"]))
    .filter((one): one is string => one !== undefined);
}

/** What `/me` says about the reader, for the Access view's own-sign-in block. */
export interface Me {
  readonly principalId?: string;
  readonly withheldVerbs: readonly string[];
  readonly secondFactorNeeded: boolean;
}

export function readMe(payload: unknown): Me {
  const body = fieldsOf(payload);
  const principalId = said(body?.["principal_id"]);
  return {
    ...(principalId === undefined ? {} : { principalId }),
    withheldVerbs: words(body?.["withheld_verbs"]),
    secondFactorNeeded: body?.["second_factor_needed"] === true,
  };
}

// ------------------------------------------------------------------------------ the writes' bodies

/** One grant, as `brain.govern_routes.GrantProposal` declares it. */
export interface GrantBody {
  readonly principal_id: string;
  readonly capability: string;
  readonly scope_slug: string;
  readonly reason: string;
  readonly not_after?: string;
}

/** One grant to several people, all or nothing, as `SeveralGrantProposal` declares it. */
export interface SeveralBody {
  readonly principal_ids: readonly string[];
  readonly capability: string;
  readonly scope_slug: string;
  readonly reason: string;
  readonly not_after?: string;
}

/** One pack assigned, as `PackProposal` declares it. */
export interface PackAssignmentBody {
  readonly principal_id: string;
  readonly pack_slug: string;
  readonly scope_slug: string;
  readonly reason: string;
  readonly not_after?: string;
}

/** One person added by hand, as `PersonAdding` declares it. */
export interface PersonAddingBody {
  readonly display_name: string;
  readonly department?: string;
  readonly employment: string;
  readonly not_after?: string;
}

/** The most people one grant to several may name: `brain.listing.MAX_SEVERAL`. */
export const MOST_GRANTED_AT_ONCE = 50;

/** The employments a person may be added with, as `brain.core.principal.Employment` spells them. */
export const EMPLOYMENTS: readonly { readonly value: string; readonly label: string; readonly bounded: boolean }[] = [
  { value: "staff", label: "Staff", bounded: false },
  { value: "contractor", label: "Contractor", bounded: true },
  { value: "partner", label: "Partner", bounded: true },
];
