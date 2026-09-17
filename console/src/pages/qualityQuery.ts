/**
 * What the Quality and canaries screen asks the API for, and how its answer is read. No React.
 *
 * `brain.console.quality_view` decides the screen. This module reads what it sent and adds
 * nothing, and the split from the page is `skillsQuery.ts`'.
 *
 * **A pass is drawn only for a run the API calls passed.** `docs/screens.html` draws the permission
 * canaries as a card of synthetic users under test, assertions per run, the last run "all green",
 * and what happens on a red one. An install records when a canary run started and how it ended.
 * The canary runner raises when a run finds anything, so a red run is recorded as failed and a run
 * recorded as ok found nothing wrong in what it compared, which the API sends as passed. Failed
 * also covers a run that could not finish, and the page says both. What a red run found is never
 * sent: it goes to the operator's alert and is stored nowhere. See
 * `A_PASS_IS_DRAWN_ONLY_FOR_A_RUN_THE_API_CALLS_PASSED`.
 *
 * **A reader who may not see a run is sent the body of an install with none**, including that a
 * run is owed, and this module reads both the same way. The sentence for no run is true of both.
 *
 * Task ids: M27.7.19
 */

import type { components } from "../api/schema";

/** The whole screen, as `brain.report_routes.QualityView` sends it. */
export type QualityBody = components["schemas"]["QualityView"];
/** One canary run. */
export type CanaryRunBody = components["schemas"]["CanaryRunView"];

/** Written down because green is the colour the design gives this card. */
export const A_PASS_IS_DRAWN_ONLY_FOR_A_RUN_THE_API_CALLS_PASSED =
  "The API sends passed only for a run recorded as ok, and the canary runner raises on any " +
  "finding, so a run that found a leak is recorded as failed rather than ok. The page draws the " +
  "API's word and nothing it infers, and says that failed covers a run that could not finish.";

/** Where the API keeps this screen. */
export const QUALITY_API_PATH = "/report/quality";

/** The console address, at the screen's own key in `brain.console.screens`. */
export const QUALITY_PATH = "/quality";

/** How each state the API sends is said. */
export const RUN_STATE_WORDS: Readonly<Record<string, string>> = Object.freeze({
  passed: "passed",
  failed: "failed, because it found something or could not finish,",
  declined: "reached in report-only mode and did not act",
  unfinished: "started and has not finished",
});

/** Read the screen out of a response body, or null for a body that is not one. */
export function readQuality(payload: unknown): QualityBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as {
    last_canary_run?: unknown;
    canaries_owed?: unknown;
    canaries_started?: unknown;
    canary_interval_seconds?: unknown;
    findings_are_recorded?: unknown;
    evaluation_runs_are_recorded?: unknown;
  };
  // `typeof null` is "object", so this admits a run and an absent run and refuses a missing field.
  if (typeof body.last_canary_run !== "object") {
    return null;
  }
  if (
    typeof body.canaries_owed !== "boolean" ||
    typeof body.canaries_started !== "boolean" ||
    typeof body.canary_interval_seconds !== "number" ||
    typeof body.findings_are_recorded !== "boolean" ||
    typeof body.evaluation_runs_are_recorded !== "boolean"
  ) {
    return null;
  }
  return payload as QualityBody;
}

/** One run, as a line: when it started, how it ended, and when, in the API's own instants. */
export function runLine(run: CanaryRunBody): string {
  const state = RUN_STATE_WORDS[run.state] ?? run.state;
  const started = `Started ${run.started_at}, ${state}`;
  return run.finished_at === null ? `${started}.` : `${started} at ${run.finished_at}.`;
}

/** A cadence in seconds, in hours when it is a whole number of them. */
export function cadence(seconds: number): string {
  const hours = seconds / 3600;
  if (Number.isInteger(hours)) {
    return hours === 1 ? "every hour" : `every ${String(hours)} hours`;
  }
  return `every ${String(seconds)} seconds`;
}
