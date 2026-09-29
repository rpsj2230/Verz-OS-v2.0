/**
 * What the Departments and teams pages ask the API and read out of its answers.
 *
 * **One department is asked of the list route, by its short name.** `GET /govern/departments` takes
 * `filter=slug:<slug>` (M27.11.1), so a department's page is the row the list would show this reader
 * for that short name, decided by `brain.console.organisation` exactly as the list is: a department
 * out of reach and one that does not exist are one empty answer, and the page says one sentence for
 * both. There is no second route answering a department by key.
 *
 * The readers are `governPeopleQuery.readOrganisation`'s, reused rather than restated, so the list,
 * the page and the older screens read one shape one way.
 *
 * Task ids: M27.11.1, M27.16.1
 */

import { listPath, NO_QUESTION } from "../../components/listing";
import { readOrganisation, type DepartmentRow } from "../governPeopleQuery";

export {
  ADD_TEAM_API_PATH,
  DEPARTMENTS_API_PATH,
  DEPARTMENT_FILTERS,
  DEPARTMENT_SORTS,
  DRAW_SCOPE_API_PATH,
  FOUND_API_PATH,
  LEAD_API_PATH,
  MEMBERSHIP_API_PATH,
  RENAME_DEPARTMENT_API_PATH,
  RENAME_TEAM_API_PATH,
  RETIRE_DEPARTMENT_API_PATH,
  RETIRE_SCOPE_API_PATH,
  RETIRE_TEAM_API_PATH,
  readOrganisation,
  type DepartmentRow,
  type MemberRow,
  type Organisation,
  type TeamRow,
  type UnplacedRow,
} from "../governPeopleQuery";

/**
 * The departments the staff source names that are not created yet, and creating the confirmed ones
 * (M27.7.4). Read for a reader who may create departments; everybody else is answered none.
 */
export const SOURCE_DEPARTMENTS_API_PATH = "/govern/departments/from-staff-source";

/** One department the staff source names, as it spells it, with the short name it would get. */
export interface SourceDepartment {
  readonly name: string;
  readonly slug: string;
}

/** What is offered, or nothing for an unreadable body. */
export function readSourceDepartments(payload: unknown): { readonly to_found: readonly SourceDepartment[] } {
  if (typeof payload !== "object" || payload === null) {
    return { to_found: [] };
  }
  const found = (payload as { to_found?: unknown }).to_found;
  return { to_found: Array.isArray(found) ? (found as SourceDepartment[]) : [] };
}

/** What one press created and the names it could not, or neither for an unreadable body. */
export function readFounded(payload: unknown): { readonly created: readonly SourceDepartment[]; readonly missed: readonly string[] } {
  if (typeof payload !== "object" || payload === null) {
    return { created: [], missed: [] };
  }
  const body = payload as { created?: unknown; not_founded?: unknown };
  return {
    created: Array.isArray(body.created) ? (body.created as SourceDepartment[]) : [],
    missed: Array.isArray(body.not_founded) ? (body.not_founded as string[]) : [],
  };
}

/** Renaming a scope's label (M27.11.1). Its short name never changes. */
export const RENAME_SCOPE_API_PATH = "/govern/departments/scopes/rename";
export const SCOPES_API_PATH = "/govern/scopes";

export const DEPARTMENTS_ADDRESS = "/departments";

/** The views of one department's page, in order. The first is the bare address. */
export const DEPARTMENT_VIEWS = ["overview", "teams", "scopes"] as const;
export type DepartmentView = (typeof DEPARTMENT_VIEWS)[number];

export const DEPARTMENT_VIEW_LABELS: Readonly<Record<DepartmentView, string>> = Object.freeze({
  overview: "Overview",
  teams: "Teams",
  scopes: "Scopes",
});

export function departmentAddress(slug: string, view: DepartmentView = "overview"): string {
  const base = `${DEPARTMENTS_ADDRESS}/${encodeURIComponent(slug)}`;
  return view === "overview" ? base : `${base}/${view}`;
}

export function departmentViewNamed(segment: string | undefined): DepartmentView {
  return DEPARTMENT_VIEWS.find((one) => one === segment) ?? "overview";
}

/** The list route asked for one department by its short name. */
export function oneDepartmentApiPath(slug: string): string {
  return listPath("/govern/departments", { ...NO_QUESTION, filters: { slug } }, null, 1);
}

/** The scopes that name one department, as the Scopes screen answers this reader. */
export function scopesNamingApiPath(slug: string): string {
  return listPath(SCOPES_API_PATH, { ...NO_QUESTION, filters: { departments: slug } }, null, 200);
}

/** Every scope the reader may see, for the Scopes tab's choices. */
export function everyScopeApiPath(): string {
  return listPath(SCOPES_API_PATH, NO_QUESTION, null, 200);
}

/** The departments a scope may be drawn over: the Departments route's first page, as names. */
export function departmentChoicesApiPath(): string {
  return listPath("/govern/departments", NO_QUESTION, null, 200);
}

/** The one department an answer carries with this short name, or null. */
export function departmentIn(payload: unknown, slug: string): DepartmentRow | null {
  return readOrganisation(payload).departments.find((one) => one.slug === slug) ?? null;
}

/** Every person listed anywhere in a department: its own people and each team's, once each. */
export function peopleOf(department: DepartmentRow): readonly { readonly principal_id: string; readonly display_name: string; readonly disabled: boolean }[] {
  const seen = new Map<string, { principal_id: string; display_name: string; disabled: boolean }>();
  for (const one of [...department.members, ...department.teams.flatMap((team) => team.members ?? [])]) {
    if (!seen.has(one.principal_id)) {
      seen.set(one.principal_id, { principal_id: one.principal_id, display_name: one.display_name, disabled: one.disabled });
    }
  }
  return [...seen.values()].sort((a, b) => a.display_name.localeCompare(b.display_name));
}

/** One scope as the Scopes route sends it. */
export interface ScopeRow {
  readonly slug: string;
  readonly label: string;
  readonly isDepartment: boolean;
  readonly scope: unknown;
}

export function readScopes(payload: unknown): { readonly scopes: readonly ScopeRow[]; readonly departments: readonly string[] } {
  if (typeof payload !== "object" || payload === null) {
    return { scopes: [], departments: [] };
  }
  const body = payload as { items?: unknown; departments?: unknown };
  const scopes = (Array.isArray(body.items) ? (body.items as readonly unknown[]) : []).flatMap((item) => {
    const row = item as { slug?: unknown; label?: unknown; is_department?: unknown; scope?: unknown };
    return typeof row.slug === "string" && typeof row.label === "string"
      ? [{ slug: row.slug, label: row.label, isDepartment: row.is_department === true, scope: row.scope }]
      : [];
  });
  const departments = Array.isArray(body.departments) ? (body.departments as readonly unknown[]).filter((one): one is string => typeof one === "string") : [];
  return { scopes, departments };
}

/**
 * Whether a scope may be offered for retirement: not a department's own and not the company-wide
 * one, which has no clauses. Presentation only: the route refuses both in a sentence.
 */
export function offersScopeRetirement(row: ScopeRow): boolean {
  const clauses = (row.scope as { clauses?: unknown } | null)?.clauses;
  return !row.isDepartment && Array.isArray(clauses) && clauses.length > 0;
}
