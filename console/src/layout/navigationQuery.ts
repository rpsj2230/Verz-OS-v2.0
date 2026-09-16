/**
 * What the shell asks the API about its own menu, and how the answer becomes one. No React.
 *
 * **The API decides which console a reader is given, and this file decides nothing.**
 * `GET /api/v1/console/navigation` is `brain.navigation_routes`, which projects
 * `brain.console.department_console.console_for`: the company console for a reader who holds some
 * screen across the whole install, and otherwise a department's console, with the menu
 * `docs/screens.html` SCREEN 2 draws narrowed to what the reader holds. This module reads that
 * body and turns it into groups the shell renders. It holds no rule about who sees what, and a
 * body it cannot read is no answer rather than a guess.
 *
 * **An unreadable answer is the same as no answer, and no answer offers only the reader's own
 * work.** `menuFor` returns the company console's groups only when the API said `company`. A
 * pending request, a failed one and a body that is not a navigation all give the Use group alone,
 * because the other default is the company console, which offers every screen about this server
 * to somebody the API has not said may see one. See `A_MENU_NOBODY_ANSWERED_OFFERS_ONLY_YOUR_OWN_WORK`.
 *
 * **Nothing is counted.** The answer carries no total and this file adds none: an entry is drawn or
 * it is not, and a group with nothing in it was never sent.
 *
 * Task ids: M27.7.29
 */

import type { components } from "../api/schema";

/** The body, as `brain.navigation_routes.NavigationView` sends it. */
export type NavigationBody = components["schemas"]["NavigationView"];

/** Written down because the tempting fallback for a menu that has not loaded is the full one. */
export const A_MENU_NOBODY_ANSWERED_OFFERS_ONLY_YOUR_OWN_WORK =
  "Which console a reader is given is the API's answer. Until it arrives, and if it fails or " +
  "cannot be read, the menu lists only the screens about the person's own work, which every " +
  "console has. Showing the company console instead would offer a department admin every " +
  "screen about this server for as long as the request took, and for good if it failed.";

/** Where the API answers, under the API base. */
export const NAVIGATION_API_PATH = "/console/navigation";

/** One entry in the menu. */
export interface NavSection {
  readonly to: string;
  readonly label: string;
}

/** A heading in the menu and the entries under it. */
export interface NavGroup {
  readonly heading: string;
  readonly sections: readonly NavSection[];
}

/** Which console the API gave this reader, as this shell holds it. */
export interface ConsoleAnswer {
  readonly console: "company" | "department";
  /** The departments the reader's own grants name. Empty for the company console. */
  readonly departments: readonly string[];
  /** The department console's groups, in the order sent. Empty for the company console. */
  readonly groups: readonly NavGroup[];
}

function isText(value: unknown): value is string {
  return typeof value === "string" && value !== "";
}

function readSection(value: unknown): NavSection | null {
  if (typeof value !== "object" || value === null) {
    return null;
  }
  const entry = value as { to?: unknown; label?: unknown };
  if (!isText(entry.to) || !entry.to.startsWith("/") || !isText(entry.label)) {
    return null;
  }
  return { to: entry.to, label: entry.label };
}

function readGroup(value: unknown): NavGroup | null {
  if (typeof value !== "object" || value === null) {
    return null;
  }
  const section = value as { heading?: unknown; entries?: unknown };
  if (!isText(section.heading) || !Array.isArray(section.entries)) {
    return null;
  }
  const sections = section.entries.map(readSection);
  if (sections.length === 0 || sections.some((one) => one === null)) {
    return null;
  }
  return { heading: section.heading, sections: sections as NavSection[] };
}

/**
 * The answer out of a response body, or `null` when the body is not a navigation.
 *
 * All or nothing: one malformed group makes the whole body unreadable rather than a menu with a
 * group missing, because a partial menu is a menu the API did not send.
 */
export function readNavigation(payload: unknown): ConsoleAnswer | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { console?: unknown; departments?: unknown; sections?: unknown };
  if (body.console !== "company" && body.console !== "department") {
    return null;
  }
  if (!Array.isArray(body.departments) || !body.departments.every(isText)) {
    return null;
  }
  if (!Array.isArray(body.sections)) {
    return null;
  }
  const groups = body.sections.map(readGroup);
  if (groups.some((one) => one === null)) {
    return null;
  }
  return {
    console: body.console,
    departments: body.departments as string[],
    groups: groups as NavGroup[],
  };
}

/**
 * The groups the shell draws for an answer, given the company console's own groups and the Use
 * group every console ends with.
 *
 * The company console is its constant whole. A department's console is the groups the API sent,
 * then Use. No answer is Use alone.
 */
export function menuFor(
  answer: ConsoleAnswer | null,
  company: readonly NavGroup[],
  own: NavGroup,
): readonly NavGroup[] {
  if (answer === null) {
    return [own];
  }
  if (answer.console === "company") {
    return company;
  }
  return [...answer.groups, own];
}
