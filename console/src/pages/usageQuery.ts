/**
 * What the Usage and cost screen asks the API for, how its answer is read, and how the person
 * table is searched, ordered and paged. No React.
 *
 * `brain.console.usage_screen` decides the screen and `brain.console.usage_view` decides which
 * axes a reader may break usage down by. This module reads what they sent and adds nothing to
 * it, and the split from the page is `skillsQuery.ts`': what a screen does about a figure the API
 * cannot send is testable without mounting a table.
 *
 * **The design names this screen and draws none of it.** `docs/screens.html` puts "Usage & cost"
 * under Report on the company overview and "Usage" on the department console, and draws the
 * figures elsewhere: questions per department beside spend on the overview, a questions figure
 * with the number of people who asked out of a headcount on the department console, and a week's
 * cost on the models screen. So this screen takes those figures and that vocabulary, questions by
 * department and by person, and cost as a link to the Spend screen that already draws it. The
 * headcount is not drawn: a headcount beside the askers is a denominator, and `brain.adoption`
 * refuses one.
 *
 * **Tokens, the model and the agent are named as not measured, never drawn empty.** The API sends
 * `not_measured` from the request ledger's own record of the fields nothing fills, and the page
 * says one sentence for each. See `A_MEASURE_NOTHING_FILLS_IS_A_SENTENCE_AND_NEVER_A_ZERO`.
 *
 * **The total is the API's and is never added up here**, which is `spendQuery.ts`'
 * `A_TOTAL_IS_READ_AND_NEVER_ADDED_UP_HERE` and the read module's own assertion. The person table
 * is paged in the browser over every line the API sent, so the total above it is always the total
 * of the whole list and a page is never a list the total fails to describe.
 *
 * **No count of what a reader was not shown.** No "of", no "others", no number of automated
 * questions. The page counts pages of lines the reader holds and nothing else.
 *
 * Task ids: M27.7.14
 */

import type { components } from "../api/schema";

/** The whole screen, as `brain.report_routes.UsageView` sends it. */
export type UsageBody = components["schemas"]["UsageView"];
/** One department's line. */
export type DepartmentUsageRow = components["schemas"]["DepartmentUsageView"];
/** One person's line. */
export type PersonUsageRow = components["schemas"]["PersonUsageView"];

/** Written down because a column of zeros is the obvious way to draw a missing measure. */
export const A_MEASURE_NOTHING_FILLS_IS_A_SENTENCE_AND_NEVER_A_ZERO =
  "The design asks for tokens by person, department, model and agent, and the request ledger " +
  "leaves the token, model and agent fields empty on every row because nothing calls a model. " +
  "A token column of zeros would say nobody used any tokens, which is a figure and a false " +
  "one, so the page says in words which measures are not taken, and the API stops sending " +
  "the words on the day the ledger fills the field.";

/** Where the API keeps this screen. */
export const USAGE_API_PATH = "/report/usage";

/** The console address, at the screen's own key in `brain.console.screens`. */
export const USAGE_PATH = "/usage";

/** The window parameter the route declares, in days. */
export const DAYS_PARAMETER = "days";

/**
 * The windows this screen offers, shortest first. A week is the route's default and the design's
 * own "Last 7 days". Each is inside the route's bound, which `tests/report-screens.test.tsx`
 * reads out of the API's own document.
 */
export const PERIODS = [7, 30, 90] as const;
export type Period = (typeof PERIODS)[number];

/** The person lines drawn on one page. */
export const PEOPLE_PER_PAGE = 25;

/** The whole request this screen makes for one window. */
export function usageApiPath(days: Period): string {
  return `${USAGE_API_PATH}?${DAYS_PARAMETER}=${String(days)}`;
}

/** The words each window is offered under. */
export function periodLabel(days: Period): string {
  return `Last ${String(days)} days`;
}

/**
 * Read the screen out of a response body, or null for a body that is not one.
 *
 * Null rather than an empty screen, for `readSpendReport`'s reason: an absent table is a real
 * answer about a reader's reach, so turning a malformed payload into one would tell somebody they
 * may not see usage on the strength of a parse failure.
 */
export function readUsage(payload: unknown): UsageBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as {
    departments?: unknown;
    people?: unknown;
    questions?: unknown;
    not_measured?: unknown;
    machine_included?: unknown;
  };
  const tableOrNull = (value: unknown): boolean => value === null || Array.isArray(value);
  if (!tableOrNull(body.departments) || !tableOrNull(body.people)) {
    return null;
  }
  if (!(body.questions === null || typeof body.questions === "number")) {
    return null;
  }
  if (!Array.isArray(body.not_measured) || typeof body.machine_included !== "boolean") {
    return null;
  }
  return payload as UsageBody;
}

/** The sentence said for each measure the API names as not measured. */
export const NOT_MEASURED_SENTENCES: Readonly<Record<string, string>> = Object.freeze({
  tokens:
    "Tokens are not measured on this install. Nothing calls a model yet, so no request has a " +
    "token count to record.",
  model:
    "Which model answered is not measured on this install. No request has been answered by a " +
    "model yet.",
  agent:
    "Which agent answered is not measured on this install. No agent runs on the path questions " +
    "are answered on yet.",
});

/** One sentence for a measure, including one this console has no sentence for yet. */
export function notMeasuredSentence(measure: string): string {
  return NOT_MEASURED_SENTENCES[measure] ?? `${measure} is not measured on this install.`;
}

/** How the person table is narrowed, ordered and paged. Nothing here reaches the API. */
export interface PeopleView {
  /** Part of a person's reference, compared without regard to case. Empty matches everybody. */
  readonly search: string;
  /** Most questions first, as the API ordered them, or by reference. */
  readonly sort: "questions" | "person";
  /** Which page, counted from one. */
  readonly page: number;
}

export const EVERYBODY: PeopleView = Object.freeze({ search: "", sort: "questions", page: 1 });

/** One page of the person table. */
export interface PeoplePage {
  readonly rows: readonly PersonUsageRow[];
  readonly page: number;
  readonly hasPrevious: boolean;
  readonly hasNext: boolean;
}

/**
 * The person lines on one page of the view, from the lines the API sent and nothing else.
 *
 * A page past the end is clamped to the last page, so a search that narrows the list while a
 * later page is open shows the last page of the narrowed list rather than an empty one that reads
 * as nobody matching.
 */
export function peoplePage(lines: readonly PersonUsageRow[], view: PeopleView): PeoplePage {
  const wanted = view.search.trim().toLowerCase();
  const kept = lines.filter((line) => wanted === "" || line.person.toLowerCase().includes(wanted));
  const ordered =
    view.sort === "person"
      ? [...kept].sort((a, b) => (a.person < b.person ? -1 : a.person > b.person ? 1 : 0))
      : kept;
  const pages = Math.max(1, Math.ceil(ordered.length / PEOPLE_PER_PAGE));
  const page = Math.min(Math.max(1, view.page), pages);
  const first = (page - 1) * PEOPLE_PER_PAGE;
  return {
    rows: ordered.slice(first, first + PEOPLE_PER_PAGE),
    page,
    hasPrevious: page > 1,
    hasNext: page < pages,
  };
}
