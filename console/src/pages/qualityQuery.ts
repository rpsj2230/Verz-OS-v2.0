/**
 * What the Quality and canaries screen asks the API for, and how its answer is read. No React.
 *
 * `brain.console.quality_view` decides the screen. This module reads what it sent and adds
 * nothing, and the split from the page is `skillsQuery.ts`'.
 *
 * **The design draws a green light and an install cannot support one.** `docs/screens.html`
 * draws the permission canaries as a card of synthetic users under test, assertions per run, the
 * last run "all green", and what happens on a red one, and the overview repeats "Permission
 * canaries green". An install records when a canary run started and how it ended, in the words of
 * the table that records every scheduled control: finished, failed, declined or unfinished. It
 * records nothing about what a run found. So a finished run is drawn as finished and the page says
 * that finished is not passed. See `A_FINISHED_RUN_IS_NEVER_DRAWN_AS_A_PASS`.
 *
 * **A reader who may not see a run is sent the body of an install with none**, and this module
 * reads both the same way. The sentence for no run is true of both.
 *
 * Task ids: M27.7.19
 */

import type { components } from "../api/schema";

/** The whole screen, as `brain.report_routes.QualityView` sends it. */
export type QualityBody = components["schemas"]["QualityView"];
/** One canary run. */
export type CanaryRunBody = components["schemas"]["CanaryRunView"];

/** Written down because green is the colour the design gives this card. */
export const A_FINISHED_RUN_IS_NEVER_DRAWN_AS_A_PASS =
  "The API sends how a canary run ended, and a run that finished is one that returned rather " +
  "than raised. A run that found a leak and returned to report it finished. Nothing records what " +
  "a run found, so the page draws the state in the API's word and says a finished run is not a " +
  "passing one, rather than drawing green on the screen somebody reads before deciding not to " +
  "worry.";

/** Where the API keeps this screen. */
export const QUALITY_API_PATH = "/report/quality";

/** The console address, at the screen's own key in `brain.console.screens`. */
export const QUALITY_PATH = "/quality";

/** How each state the API sends is said. Never passed and never green. */
export const RUN_STATE_WORDS: Readonly<Record<string, string>> = Object.freeze({
  finished: "finished",
  failed: "failed",
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
