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
 * **Tokens are drawn by every axis the API sends, and an axis it does not send is not mentioned.**
 * Since the executor `brain.models.calls` started calling models, every call is metered onto its
 * request's ledger row, and `brain.console.usage_screen` joins those rows to the questions this
 * reader's tables already count, so `tokens` is one breakdown per axis the reader may have, person,
 * department, model and agent, in that order. An axis withheld is absent from the list rather than
 * empty, and the page draws what is there and says nothing about what is not: a heading saying an
 * axis is hidden is the count of hidden axes in words. `runs` is how many requests with a model call
 * fell in a bucket and is never called questions, which is
 * `RUNS_ARE_REQUESTS_WITH_A_MODEL_CALL_AND_NOT_QUESTIONS`.
 *
 * **A measure the ledger cannot fill is still a sentence, never a zero.** The API goes on naming a
 * measure in `not_measured` for as long as its fields are empty, and the page says one sentence for
 * each. Today it names none. See `A_MEASURE_NOTHING_FILLS_IS_A_SENTENCE_AND_NEVER_A_ZERO`.
 *
 * **Every total is the API's and is never added up here**, which is `spendQuery.ts`'
 * `A_TOTAL_IS_READ_AND_NEVER_ADDED_UP_HERE` and the read module's own assertion. The questions total
 * is `questions`, and each token table's totals row is that breakdown's `total_runs`,
 * `total_tokens_in` and `total_tokens_out`. The person table is paged in the browser over every line
 * the API sent, so the total above it is always the total of the whole list and a page is never a
 * list the total fails to describe.
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
/** Tokens by one axis, `brain.report_routes.TokenBreakdownView`. */
export type TokenBreakdown = components["schemas"]["TokenBreakdownView"];
/** One bucket of one token breakdown. */
export type TokenLine = components["schemas"]["TokenLineView"];

/** Written down because a column of zeros is the obvious way to draw a missing measure. */
export const A_MEASURE_NOTHING_FILLS_IS_A_SENTENCE_AND_NEVER_A_ZERO =
  "The design asks for tokens by person, department, model and agent. Where the request ledger " +
  "leaves a measure's fields empty, a column of zeros would say nobody used any tokens, which is " +
  "a figure and a false one, so the page says in words which measures are not taken, and the API " +
  "stops sending the words on the day the ledger fills the field. It fills all three now, and the " +
  "token tables are drawn in their place.";

/** Written down because "runs" is one rename away from "questions" and the two are different figures. */
export const RUNS_ARE_REQUESTS_WITH_A_MODEL_CALL_AND_NOT_QUESTIONS =
  "A token breakdown's runs are the requests in a bucket that called a model, which is the figure " +
  "its tokens are over. A question answered from a fast-path rule calls none and is not a run, so " +
  "calling the column questions would put a second, smaller question count beside the real one, " +
  "and the difference between the two would read as questions somebody was not shown.";

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
    tokens?: unknown;
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
  if (!Array.isArray(body.tokens) || !body.tokens.every(isBreakdown)) {
    return null;
  }
  return payload as UsageBody;
}

/** Whether one entry of `tokens` has the lines a table is drawn from and the totals under them. */
function isBreakdown(value: unknown): boolean {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const one = value as {
    axis?: unknown;
    lines?: unknown;
    total_runs?: unknown;
    total_tokens_in?: unknown;
    total_tokens_out?: unknown;
  };
  return (
    typeof one.axis === "string" &&
    Array.isArray(one.lines) &&
    typeof one.total_runs === "number" &&
    typeof one.total_tokens_in === "number" &&
    typeof one.total_tokens_out === "number"
  );
}

/** The sentence said for each measure the API names as not measured. */
export const NOT_MEASURED_SENTENCES: Readonly<Record<string, string>> = Object.freeze({
  tokens:
    "Tokens are not measured on this install: the request ledger does not record a token " +
    "count, so no token table is drawn.",
  model:
    "Which model answered is not measured on this install: the request ledger does not record " +
    "it, so no table by model is drawn.",
  agent:
    "Which agent answered is not measured on this install: the request ledger does not record " +
    "it, so no table by agent is drawn.",
});

/** One sentence for a measure, including one this console has no sentence for yet. */
export function notMeasuredSentence(measure: string): string {
  return NOT_MEASURED_SENTENCES[measure] ?? `${measure} is not measured on this install.`;
}

/** The heading and caption of one token table, by the axis the API names. */
export function tokensHeading(axis: string): string {
  return `Tokens by ${axis}`;
}

/** The column heading over a token table's keys, by axis. An axis this console has no word for is named as sent. */
export function tokensKeyHeading(axis: string): string {
  const words: Readonly<Record<string, string>> = {
    person: "Person",
    department: "Department",
    model: "Model",
    agent: "Agent",
  };
  return words[axis] ?? axis;
}

/** The column over `runs`. See `RUNS_ARE_REQUESTS_WITH_A_MODEL_CALL_AND_NOT_QUESTIONS`. */
export const RUNS_HEADING = "Requests with a model call";

/** A breakdown with no lines, which is a period in which no question this reader holds called a model. */
export const NO_MODEL_CALL = "No question in this period called a model.";

/**
 * The at-a-glance tokens, from the first breakdown the API sent, or null when it sent none.
 *
 * The first rather than any sum: every breakdown is one grouping of one row set, so their totals
 * are equal by construction on the API, and adding them up would count each token once per axis.
 */
export function glanceTokens(
  tokens: readonly TokenBreakdown[],
): { readonly tokensIn: number; readonly tokensOut: number } | null {
  const first = tokens[0];
  return first === undefined
    ? null
    : { tokensIn: first.total_tokens_in, tokensOut: first.total_tokens_out };
}

/** The at-a-glance tokens in words. */
export function glanceTokensLine(tokensIn: number, tokensOut: number): string {
  return `${String(tokensIn)} in, ${String(tokensOut)} out`;
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
