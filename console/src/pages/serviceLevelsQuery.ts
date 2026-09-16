/**
 * What the service levels screen asks the API for, and how a reading is read. No React.
 *
 * The split is `matrixQuery.ts`'s and for its reason: what a screen does with a figure it must
 * not compute cannot be tested through a component that mounts a page.
 *
 * **Every figure on this screen arrives measured, and this module computes none of them.**
 * `brain.console.service_level_view` decides what a reader may be shown and
 * `brain.ops.service_levels` folds the ledger into a reading; the route copies both onto the
 * response. So there is no arithmetic here: no percentage worked out from a rate, no lane
 * compared against its objective, no total over the lanes. `met` is the API's own boolean, and
 * a console that recomputed it from `p95_ms` and `objective_p95_ms` would be a second
 * implementation of the shortfall rule in the copy nobody keeps in step. See
 * `A_MEASUREMENT_IS_NEVER_RECOMPUTED_IN_A_BROWSER`.
 *
 * **A reading with no lanes is rendered as a reading with no lanes, and nothing is said about
 * why.** A reader whose usage grant names one department is answered the reading an install
 * declaring no objectives produces over a quiet window, and the two bodies are equal. A
 * sentence here saying "you may not see this" would be the console inventing a refusal the API
 * did not make, and it would separate DENIED from ABSENT in the one place a person reads. See
 * `A_READING_WITH_NO_LANES_IS_NOT_EXPLAINED`.
 *
 * Task ids: M27.7.16
 */

import type { components } from "../api/schema";

/** One lane's reading, as `brain.report_routes.LaneReadingView` sends it. */
export type LaneReadingRow = components["schemas"]["LaneReadingView"];

/** A whole reading, as `brain.report_routes.ServiceLevelsView` sends it. */
export type ServiceLevelsBody = components["schemas"]["ServiceLevelsView"];

/**
 * Written down because working a percentage out of a rate is one line and looks like
 * formatting.
 */
export const A_MEASUREMENT_IS_NEVER_RECOMPUTED_IN_A_BROWSER =
  "Every figure on this screen was measured by brain.ops.service_levels against an objective " +
  "brain.ops.reliability declares, and narrowed by brain.console.service_level_view before it " +
  "was sent. A console that decided whether a lane met its objective, or averaged two lanes, " +
  "would hold a second answer to a question the API has already answered, and the two would " +
  "disagree the day either threshold moved. So this module reads fields and formats them, and " +
  "the only numbers it produces are the same numbers with a unit after them.";

/**
 * Written down because an empty table invites a caption, and the caption is the disclosure.
 */
export const A_READING_WITH_NO_LANES_IS_NOT_EXPLAINED =
  "A reading with no lanes reaches a reader for two reasons that must stay indistinguishable: " +
  "their usage grant does not cover the install, or the install promises nothing over a quiet " +
  "window. The API answers one body for both. A sentence here naming a grant, or even saying " +
  "that something was narrowed, would separate them in the one place a person reads, so the " +
  "screen says only that there is nothing to show.";

/** Where the API keeps a reading. */
export const SERVICE_LEVELS_API_PATH = "/report/service-levels";

/** The console address for this screen. */
export const SERVICE_LEVELS_PATH = "/service-levels";

/** The window parameter the route declares. */
export const HOURS_PARAMETER = "hours";

/**
 * How long a window this screen asks for.
 *
 * A day, which is the route's own default, sent explicitly rather than left out so that the
 * request says what the screen is showing. Below `MAX_READING_HOURS`, which the route bounds
 * at four weeks: a console asking for more is refused with `HTTPValidationError`, which reaches
 * a person as the least useful sentence this console has, and it would do so on every load.
 */
export const READING_HOURS = 24;

/** The whole request this screen makes, query string included. */
export function serviceLevelsApiPath(): string {
  return `${SERVICE_LEVELS_API_PATH}?${HOURS_PARAMETER}=${String(READING_HOURS)}`;
}

/**
 * Read a reading out of a response body.
 *
 * Null for a body that is not one, rather than an empty reading, and the difference is what
 * the page does about it: an empty reading is a real answer and would be drawn as one, so a
 * console that turned a malformed body into it would tell a reader the install promises
 * nothing on the strength of a parse failure. `readMatrixPage` returns an empty page instead,
 * and the difference between the two is exactly this: a page of rungs that is empty says
 * nothing, and a reading that is empty says something.
 */
export function readServiceLevels(payload: unknown): ServiceLevelsBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { start?: unknown; end?: unknown; lanes?: unknown };
  if (typeof body.start !== "string" || typeof body.end !== "string") {
    return null;
  }
  if (!Array.isArray(body.lanes)) {
    return null;
  }
  return payload as ServiceLevelsBody;
}

/**
 * A success rate as a percentage, to one decimal place, or an em-free dash for an absent one.
 *
 * The only computation in this module and it is a unit change rather than a figure: the API
 * sends a share of one, people read percentages, and the multiplication introduces no fact.
 * A rate of null means there were no requests in the lane, which
 * `brain.ops.service_levels.LaneReading` states as a decision rather than as a gap, so it is
 * rendered as nothing rather than as zero. Zero would say every request failed.
 */
export function ratePercent(rate: number | null | undefined): string {
  if (rate === null || rate === undefined) {
    return NOT_MEASURED;
  }
  return `${(rate * 100).toFixed(1)}%`;
}

/** Milliseconds, or nothing where the sample could not support a rank. */
export function milliseconds(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return NOT_MEASURED;
  }
  return `${Math.round(value).toString()} ms`;
}

/**
 * What is shown where a figure was not measured.
 *
 * A dash and no sentence. "Too few requests" would be a count with words instead of digits:
 * it says the sample was below a threshold, and a reader watching the figure appear learns
 * where the threshold is. The lane's own `requests` is on the screen beside it, which is the
 * honest version of the same information and is a figure about rows the reader may see.
 */
export const NOT_MEASURED = "-";
