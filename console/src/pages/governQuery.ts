/**
 * What the four govern screens ask the API for, and what may be sent back. No React.
 *
 * The split is `recordsQuery.ts`'s and `matrixQuery.ts`'s, and the same one `paging.ts` makes:
 * this decides what may be asked and what a column is, the pages render it. The reason is the
 * case that is always wrong. What a form does about a field it must not send cannot be tested
 * through a component that mounts a form library and a table.
 *
 * **One query module for four screens, and the reason is that they are one API surface.**
 * `brain.govern_routes` serves all four and the two writes, with one refusal shape and one set
 * of rules about counts; four modules would be four places to keep that in step, and the first
 * one to drift would be whichever screen somebody edited last.
 *
 * **Nothing here decides who may see what.** The request is identical for every caller, the API
 * answers from grants this browser never receives, and a refusal comes back as a value rendered
 * in the API's own words. `editable` on the people page decides whether a control is drawn and
 * decides nothing else. See `A_HIDDEN_CONTROL_IS_NOT_A_REFUSAL`.
 *
 * **No screen here renders a number about its own rows.** Not a total, not a page number, not
 * the count of what arrived, and these are the screens where that rule earns its keep: every
 * listing behind them is filtered per caller, so "showing 3" is the subtraction `CLAUDE.md`
 * forbids rather than a footer. `truncated` is a flag and says a page came back full.
 *
 * **A grant is proposed at a named scope, and the names offered are the ones the Scopes screen
 * showed.** There is no control here for typing a predicate, because
 * `brain.govern_routes.GrantProposal` has no field one could travel in: the body carries a
 * slug. See `A_SCOPE_IS_CHOSEN_BY_NAME_AND_NEVER_TYPED`.
 *
 * Task ids: M27.7.3, M27.7.4, M27.7.5, M27.7.6, M27.7.7
 */

import type { RJSFSchema, UiSchema } from "@rjsf/utils";
import type { components } from "../api/schema";
import { NO_QUESTION, listPath, type FilterChoice, type SortChoice } from "../components/listing";

/** One subject and what this reader may be told they hold, as `PersonView` sends it. */
export type PersonRow = components["schemas"]["PersonView"];
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
export const PEOPLE_API_PATH = "/govern/people";
export const ROLES_API_PATH = "/govern/roles";
export const CAPABILITIES_API_PATH = "/govern/capabilities";
export const SCOPES_API_PATH = "/govern/scopes";
export const GRANTS_API_PATH = "/govern/grants";
export const REMOVAL_API_PATH = "/govern/grants/removal";

/** The console addresses. The first is also where a subject's own page begins. */
export const PEOPLE_PATH = "/people";
export const ROLES_PATH = "/roles";
export const CAPABILITIES_PATH = "/capabilities";
export const SCOPES_PATH = "/scopes";

/** The one query parameter the people and scopes routes declare. */
export const LIMIT_PARAMETER = "limit";

/**
 * How many scopes the grant form asks for to offer as slugs: the most one page may carry, which is
 * also every scope the route loads. Asserted against the route's declared maximum in
 * `tests/govern-pages.test.tsx`, because a size the route refuses is a form that never loads.
 */
export const SCOPE_CHOICES_PAGE_SIZE = 200;

/** The request the grant form makes for the scopes it may offer. No search, no filter. */
export function scopeChoicesApiPath(): string {
  return listPath(SCOPES_API_PATH, NO_QUESTION, null, SCOPE_CHOICES_PAGE_SIZE);
}

/**
 * The request for one subject's row, when a subject is open.
 *
 * A filter on the subject the address names, so the open subject is found whichever page of the
 * list it would sit on. The route answers it over the subjects this reader may see, so a key that
 * matches nothing is the same answer as a key nobody holds.
 */
export function subjectApiPath(subject: string): string {
  return listPath(PEOPLE_API_PATH, { ...NO_QUESTION, filters: { subject } }, null, 1);
}

/** The filters the people route declares that this screen offers, over values on rows drawn. */
export const PEOPLE_FILTERS: readonly FilterChoice<PersonRow>[] = [
  { column: "capabilities", label: "Capability", everything: "Any capability", read: (row) => row.capabilities },
];

export const PEOPLE_SORTS: readonly SortChoice[] = [
  { value: "", label: "By subject" },
  { value: "-subject", label: "By subject, last first" },
];

/** The filters the scopes route declares that this screen offers, over values on rows drawn. */
export const SCOPE_FILTERS: readonly FilterChoice<ScopeRowView>[] = [
  {
    column: "is_department",
    label: "Kind",
    everything: "Every scope",
    read: (row) => row.is_department,
    describe: (value) => (value === "true" ? "A department" : "Named"),
  },
];

export const SCOPE_SORTS: readonly SortChoice[] = [
  { value: "", label: "By slug" },
  { value: "label", label: "By label" },
];

/**
 * The console address for one subject's page.
 *
 * Built from a constant prefix and an encoded key, for the reason `rungAddress` gives:
 * GHSA-wrjc-x8rr-h8h6 is an open redirect through a backslash reaching `useNavigate`, it
 * covers every react-router this project can install, and the defence is that the address
 * starts with a literal path segment. The key is `principal:u_1`, so the encoding is not
 * decoration either: a bare colon in a path segment is legal and a bare one in some of the
 * shapes a subject key can take is not.
 */
export function subjectAddress(subject: string): string {
  return `${PEOPLE_PATH}/${encodeURIComponent(subject)}`;
}

/**
 * The principal id inside a subject key, or null when the key is not a principal's.
 *
 * `brain.identity.teams.PrincipalSubject.key` is `principal:<id>` and `TeamSubject`'s is
 * `team:<path>`. A removal names a principal, because `gate.capability_grant` has a
 * `principal_id` column and no column for a team, so a team's row is one this console can show
 * and cannot offer a control on. Returning null rather than guessing is what makes that a
 * decision here instead of a request the API refuses for a reason nobody can see.
 */
export const PRINCIPAL_PREFIX = "principal:";

export function principalIn(subject: string): string | null {
  return subject.startsWith(PRINCIPAL_PREFIX) ? subject.slice(PRINCIPAL_PREFIX.length) : null;
}

/** One page of people, as this console holds it. Three fields, deliberately. */
export interface PeoplePage {
  readonly people: readonly PersonRow[];
  /** Whether this caller may write a grant. Presentation only. */
  readonly editable: boolean;
  /** The page came back full. Never how much more there is. */
  readonly truncated: boolean;
}

const NO_PEOPLE: PeoplePage = Object.freeze({ people: [], editable: false, truncated: false });

/**
 * Read `brain.govern_routes.PeoplePage` out of a response body.
 *
 * **`total` and `next_cursor` stop here**, in the same way and for the same reason
 * `readMatrixPage` drops the total: not "we agree not to render it" but no path from the
 * payload to a renderer. `PeoplePage` inherits `total` from `brain.api.Page` and never
 * populates it, and a screen holding the field is a screen one line away from showing it.
 *
 * An unreadable body yields an empty page rather than throwing, which is `readMatrixPage`'s
 * choice and for its reason: the shape is fixed by a response model in this repository, so a
 * body that is not a page is a console built against a different API and there is no sentence
 * worth composing about it.
 */
export function readPeoplePage(payload: unknown): PeoplePage {
  if (typeof payload !== "object" || payload === null) {
    return NO_PEOPLE;
  }
  const body = payload as { items?: unknown; editable?: unknown; truncated?: unknown };
  if (!Array.isArray(body.items)) {
    return NO_PEOPLE;
  }
  return {
    people: body.items as PersonRow[],
    editable: body.editable === true,
    truncated: body.truncated === true,
  };
}

/** One page of scopes, and the department names a filter may offer. */
export interface ScopesPage {
  readonly scopes: readonly ScopeRowView[];
  readonly departments: readonly string[];
  readonly truncated: boolean;
}

const NO_SCOPES: ScopesPage = Object.freeze({ scopes: [], departments: [], truncated: false });

/** Read `brain.govern_routes.ScopePage` out of a response body. See `readPeoplePage`. */
export function readScopesPage(payload: unknown): ScopesPage {
  if (typeof payload !== "object" || payload === null) {
    return NO_SCOPES;
  }
  const body = payload as { items?: unknown; departments?: unknown; truncated?: unknown };
  if (!Array.isArray(body.items)) {
    return NO_SCOPES;
  }
  return {
    scopes: body.items as ScopeRowView[],
    departments: Array.isArray(body.departments) ? (body.departments as string[]) : [],
    truncated: body.truncated === true,
  };
}

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

/** The subject with this key among the ones on the page, or null. */
export function personIn(people: readonly PersonRow[], subject: string): PersonRow | null {
  return people.find((one) => one.subject === subject) ?? null;
}

/**
 * The bounds and the grammar `POST /api/v1/govern/grants` declares, copied here so the form can
 * refuse a value without spending a request.
 *
 * A copy, and therefore checked against the original rather than against itself: the test reads
 * the request body schema out of the generated OpenAPI document, which is produced from
 * `brain.app.create_app` and carries the bounds pydantic derived from the route's own model.
 */
export const MAX_PRINCIPAL_CHARS = 128;
export const MAX_REASON_CHARS = 500;
export const MIN_SLUG_CHARS = 2;
export const MAX_SLUG_CHARS = 60;

/** The fields a grant proposal may send, in the order the form shows them. */
export const PROPOSAL_FIELDS = [
  "principal_id",
  "capability",
  "scope_slug",
  "reason",
] as const;

/**
 * The form a grant is written through.
 *
 * **A schema written here, from the route's own request model, and not one the API sent.** The
 * same honesty `RECORDS_QUERY_SCHEMA` states about itself: no route returns a JSON Schema, so
 * the form is exercised over a document this console assembled. What makes it more than a
 * hand-written form is that every bound in it is the route's bound and is checked against the
 * route's own description.
 *
 * There is no `granted_by` and no `scope`. The first is the caller, taken from the token by the
 * route, and a box for it would be a grant attributable to whoever the browser named; the
 * second is the predicate, and see `A_SCOPE_IS_CHOSEN_BY_NAME_AND_NEVER_TYPED`. `not_after` is
 * absent too and that is a gap rather than a rule: an expiry is a datetime and this console has
 * no control for one, so every grant written from this screen is unbounded, which the page says
 * in words rather than leaving a person to discover.
 *
 * Frozen and built once per scope list, because `SchemaForm` memoises on the schema's identity
 * and the ajv validator recompiles whenever it changes.
 */
export function proposalSchema(slugs: readonly string[]): RJSFSchema {
  return Object.freeze<RJSFSchema>({
    type: "object",
    required: [...PROPOSAL_FIELDS],
    properties: {
      principal_id: {
        type: "string",
        title: "principal_id",
        minLength: 1,
        maxLength: MAX_PRINCIPAL_CHARS,
      },
      capability: { type: "string", title: "capability", minLength: 1 },
      // An enumeration rather than a text box, and the members are what the Scopes screen
      // answered this reader. A slug they were not offered is refused by the route, so this is
      // presentation; what it buys is that the ordinary case needs no typing and no guessing.
      scope_slug: {
        type: "string",
        title: "scope_slug",
        minLength: MIN_SLUG_CHARS,
        maxLength: MAX_SLUG_CHARS,
        ...(slugs.length > 0 ? { enum: [...slugs] } : {}),
      },
      reason: { type: "string", title: "reason", minLength: 1, maxLength: MAX_REASON_CHARS },
    },
  });
}

/** Presentation only. The submit text is the sentence, so the button says what it does. */
export const PROPOSAL_UI: UiSchema = Object.freeze<UiSchema>({
  "ui:submitButtonOptions": { submitText: "Write this grant" },
});

/** The body of one grant, as the route's `GrantProposal` model declares it. */
export interface GrantProposal {
  readonly principal_id: string;
  readonly capability: string;
  readonly scope_slug: string;
  readonly reason: string;
}

/**
 * What the form submitted, or null if it was not a proposal.
 *
 * **Assembled from four named keys rather than passed through.** That is the difference between
 * a body this console composed and a body the form library handed over: a `granted_by` or a
 * `scope` in the form's state, from a schema change, a merge or a browser extension, has
 * nowhere here to travel. The route forbids both keys as well, and both are wanted: the route
 * stops them arriving and this stops them being sent, so a person never sees a 422 about a
 * field they did not fill in.
 *
 * Null means the shape was not what this screen asked for, and the caller does nothing. A write
 * assembled out of values nobody recognised is a write nobody meant to make, and a grant is the
 * most expensive wrong write in this console.
 */
export function submittedProposal(data: unknown): GrantProposal | null {
  if (typeof data !== "object" || data === null) {
    return null;
  }
  const fields = data as Record<string, unknown>;
  const principal = fields["principal_id"];
  const capability = fields["capability"];
  const slug = fields["scope_slug"];
  const reason = fields["reason"];
  if (
    typeof principal !== "string" ||
    typeof capability !== "string" ||
    typeof slug !== "string" ||
    typeof reason !== "string"
  ) {
    return null;
  }
  if (principal === "" || capability === "" || slug === "" || reason === "") {
    return null;
  }
  return { principal_id: principal, capability, scope_slug: slug, reason };
}

/** The body of one removal, as the route's `GrantRemoval` model declares it. */
export interface GrantRemoval {
  readonly principal_id: string;
  readonly capability: string;
}
