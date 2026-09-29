/**
 * What the Department page asks for and where its views are. No React.
 *
 * **The department is the reader's own, named by their grants.** `GET /navigation` answers the
 * departments the reader administers, read off the scopes their screens are held in and never off
 * the department table (`brain.console.department_console`), so there is no address segment that
 * could name somebody else's. A reader holding several is offered each by the `department`
 * parameter, which chooses only among those; anything else is the first.
 *
 * **Every figure is another route's, narrowed by that route.** The department's name, lead and
 * teams are the Departments list's row for it (`departments/departmentsQuery.oneDepartmentApiPath`),
 * the questions are Usage's line for it, the agents are the roster, the knowledge is the Knowledge
 * list filtered to it, and the history is the audit trail's entries about it. Rejected: an overview
 * route of its own, which would be a second door to five sets of rows under a sixth decision, the
 * shape `brain.operate_routes.A_FIGURE_ANOTHER_ROUTE_SERVES_IS_READ_THERE` refuses.
 *
 * Task ids: M27.7.29, M27.16.1
 */

import { listPath, NO_QUESTION } from "../../components/listing";
import { AUDIT_API_PATH } from "../auditQuery";
import { DOCUMENTS_API_PATH } from "../knowledge/knowledgeDocuments";

/** The console address, which `brain.console.department_console.DEPARTMENT_NAVIGATION` links to. */
export const DEPARTMENT_PATH = "/department";

/** The design's own label for this screen, which the menu and the trail share. */
export const DEPARTMENT_HEADING = "Department";

/** The parameter choosing among the departments a reader administers. */
export const DEPARTMENT_PARAMETER = "department";

/** The window the questions figures read, in days: the design's "Last 7 days". */
export const DEPARTMENT_WINDOW_DAYS = 7;

/** How many documents and history entries the page shows before linking to the full screen. */
export const SHOWN_DOCUMENTS = 5;
export const SHOWN_HISTORY = 20;

/** The views of the page, in order. The first is the bare address. */
export const DEPARTMENT_HOME_VIEWS = ["dashboard", "profile", "about"] as const;
export type DepartmentHomeView = (typeof DEPARTMENT_HOME_VIEWS)[number];

export const DEPARTMENT_HOME_VIEW_LABELS: Readonly<Record<DepartmentHomeView, string>> = Object.freeze({
  dashboard: "Dashboard",
  profile: "Profile",
  about: "About",
});

export function homeViewNamed(segment: string | undefined): DepartmentHomeView {
  return DEPARTMENT_HOME_VIEWS.find((one) => one === segment) ?? "dashboard";
}

/**
 * The console address of one view, carrying the chosen department only when the reader holds
 * several, so the ordinary address stays `/department`.
 */
export function departmentHomeAddress(view: DepartmentHomeView, department: string | null, several: boolean): string {
  const base = view === "dashboard" ? DEPARTMENT_PATH : `${DEPARTMENT_PATH}/${view}`;
  return several && department !== null ? `${base}?${new URLSearchParams({ [DEPARTMENT_PARAMETER]: department }).toString()}` : base;
}

/** The department shown: the one asked for when the reader holds it, else their first, else none. */
export function chosenDepartment(held: readonly string[], asked: string | null): string | null {
  if (asked !== null && held.includes(asked)) {
    return asked;
  }
  return held[0] ?? null;
}

/** The Knowledge list, filtered to the department, newest first, a few rows. */
export function departmentDocumentsApiPath(department: string): string {
  return listPath(DOCUMENTS_API_PATH, { ...NO_QUESTION, filters: { department } }, null, SHOWN_DOCUMENTS);
}

/**
 * The audit trail's entries about departments that mention this one. The route filters by kind and
 * by words, not by subject, so the page keeps the rows whose subject is this department; that
 * narrows rows the reader was sent and adds nothing.
 */
export function departmentHistoryApiPath(department: string): string {
  const query = new URLSearchParams({ subject_kind: "department", q: department, limit: String(SHOWN_HISTORY) });
  return `${AUDIT_API_PATH}?${query.toString()}`;
}
