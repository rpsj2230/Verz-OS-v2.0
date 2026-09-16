/**
 * What the spend screen asks the API for, and how a breakdown is read. No React.
 *
 * `brain.console.spend_report_view` reads the materialised view at one reader's reach and
 * grades the age of the figures on `brain.gate.provenance`'s scale;
 * `brain.console.spend_view.Report` asserts that the total is the sum of the lines beside it.
 * This module reads those fields and adds nothing to them.
 *
 * **The total is the API's and is never added up here.** That is not a preference. A renderer
 * that sums the rows it drew will one day be handed a list it did not draw all of, and the
 * figure it prints is then the one nobody can reconcile, which is the argument
 * `brain.console.spend_view.Report` makes for holding the total on the object. So `total_minor`
 * is read, and `A_TOTAL_IS_READ_AND_NEVER_ADDED_UP_HERE` says why in the place somebody would
 * write the loop.
 *
 * **A view nobody has refreshed is not a company that spent nothing.** The API answers
 * `built: false` with no lines and a null total, and this screen says the report has not been
 * built rather than drawing a zero. A zero would be a figure, and a false one, on the screen
 * somebody checks before deciding not to worry. See `AN_UNBUILT_REPORT_IS_NOT_A_ZERO`.
 *
 * **The age of the figures is a field and is shown beside them.** `freshness` is the same word
 * an answer's citation carries, on the same scale, which is
 * `A_REPORTS_AGE_IS_GRADED_ON_THE_SCALE_AN_ANSWERS_IS`. This module renders the word the API
 * sent and does not translate it: "overdue" beside an answer described as "ageing" would be a
 * second vocabulary for one fact.
 *
 * Task ids: M27.7.15
 */

import type { components } from "../api/schema";

/** One line of a breakdown, as `brain.report_routes.SpendLineView` sends it. */
export type SpendLineRow = components["schemas"]["SpendLineView"];

/** A whole breakdown, as `brain.report_routes.SpendReportView` sends it. */
export type SpendReportBody = components["schemas"]["SpendReportView"];

/** Written down because summing the rows on screen is one line and reads as a convenience. */
export const A_TOTAL_IS_READ_AND_NEVER_ADDED_UP_HERE =
  "brain.console.spend_view.Report asserts in its constructor that its total is the sum of " +
  "its own lines, because a renderer that adds them up itself will one day be handed a list " +
  "it did not draw all of. A console that computed the total would be that renderer, and the " +
  "day a page is bounded the figure on screen would quietly stop being the figure the API " +
  "stands behind. So the total is a field, read and printed.";

/** Written down because an empty breakdown and an unbuilt one look identical in a loop. */
export const AN_UNBUILT_REPORT_IS_NOT_A_ZERO =
  "A materialised view created with no data holds nothing, and a report built over nothing " +
  "says the company spent nothing. The API answers built: false with a null total for exactly " +
  "that case, and this screen says the report has not been built yet. Drawing a zero would be " +
  "a figure, and a false one, on the screen somebody reads before deciding not to worry.";

/** Where the API keeps a breakdown. */
export const SPEND_API_PATH = "/report/spend";

/** The console address for this screen. */
export const SPEND_PATH = "/spend";

/** The dimension parameter the route declares. */
export const DIMENSION_PARAMETER = "dimension";

/**
 * Which dimension this screen asks for.
 *
 * Department, which is the route's own default and the one dimension every reader's grant is
 * written in: every key on the page is a value the reader could have named themselves. The
 * other four are a control this screen does not yet have, and adding one is a change to the
 * request rather than to what is drawn.
 */
export const SPEND_DIMENSION = "department";

/** The whole request this screen makes, query string included. */
export function spendApiPath(): string {
  return `${SPEND_API_PATH}?${DIMENSION_PARAMETER}=${SPEND_DIMENSION}`;
}

/**
 * Read a breakdown out of a response body.
 *
 * Null for a body that is not one, for `readServiceLevels`' reason: an empty breakdown is a
 * real answer about a reader's reach, so turning a parse failure into one would tell somebody
 * their departments spent nothing on the strength of a malformed payload.
 */
export function readSpendReport(payload: unknown): SpendReportBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { lines?: unknown; built?: unknown; dimension?: unknown };
  if (!Array.isArray(body.lines) || typeof body.built !== "boolean") {
    return null;
  }
  if (typeof body.dimension !== "string") {
    return null;
  }
  return payload as SpendReportBody;
}

/**
 * Minor units as a decimal figure, with no currency symbol.
 *
 * The ledger holds minor units and nothing on this install says which currency they are: a
 * symbol here would be this console asserting one, and the first company whose ledger is in
 * another currency would read the wrong sign beside a correct number. Two decimal places,
 * because a minor unit is a hundredth in every currency this repository has a price list for,
 * and the division is a unit change rather than a figure.
 */
export function majorUnits(minor: number): string {
  return (minor / 100).toFixed(2);
}

/**
 * How old the figures are, in the API's own word, with the instant it sent beside it.
 *
 * The word is not translated and not coloured. `brain.gate.provenance` grades an answer's
 * citation on this scale with these four words, and a console that called STALE "out of date"
 * would leave a reader unable to tell whether the screen and the answer meant the same thing.
 */
export function freshnessLine(report: SpendReportBody): string {
  if (report.as_of === null) {
    return report.freshness;
  }
  return `${report.freshness}, as of ${report.as_of}`;
}
