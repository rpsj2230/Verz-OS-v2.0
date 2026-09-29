/**
 * What the Errors screen asks for and says. No React.
 *
 * `brain.error_routes` answers the failures the database keeps: scheduled jobs that failed, by the
 * kind of failure and never its message, and questions that failed or degraded, by the reference a
 * person is shown beside a failure. Each list is narrowed by the decision that already says who may
 * see that record, and neither carries a count.
 *
 * **The process log is not here, and the page says where it is.** Since the log store, the
 * application's own warnings and errors are on the Logs screen, and `process_log_is_not_kept` is
 * false; the older sentence is kept for an API from before it, which sends true.
 *
 * **A failed question shows the whole routing decision its row holds (M3.4.2, M3.6.3)**: the
 * risk score, the lane and the rule that chose it, the agent and the stage that chose it, the tier
 * the model call was routed to and the step that settled it, and the model that answered. Each
 * code is put into words here and nothing is worked out: a code this table does not know is shown
 * as the code, so a newer API's rule is still said rather than dropped.
 *
 * Task ids: M3.4.2, M3.6.3
 */

import type { components } from "../api/schema";

export type ErrorsBody = components["schemas"]["ErrorsPage"];

export const ERRORS_API_PATH = "/errors";
export const ERRORS_PATH = "/errors";
export const ERRORS_LABEL = "Errors";
export const ERRORS_LEDE =
  "Jobs that failed and questions that failed or degraded, newest first. The reference is the one a person was shown.";

export const READING_ERRORS = "Loading the failures.";
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";
export const UNREADABLE_ANSWER =
  "The API answered in a shape this console does not read, so no failure is listed. The console " +
  "and the API are probably from different releases.";

export const JOBS_HEADING = "Failed scheduled jobs";
export const JOBS_CAPTION = "Scheduled jobs whose run failed, newest first";
export const NO_JOB_FAILURES = "No job failed in this window";
export const NO_JOB_FAILURES_MORE = "A job's failed run appears here with its kind of failure.";
export const REQUESTS_HEADING = "Failed questions";
export const REQUESTS_CAPTION = "Questions that failed or degraded, newest first";
export const NO_REQUEST_FAILURES = "No question failed in this window";
export const NO_REQUEST_FAILURES_MORE = "A question that failed or degraded appears here with its reference.";
export const FULL_LIST = "This list came back full: choose a shorter window to see the rest.";
export const PROCESS_LOG_IS_NOT_KEPT = "The application's own log is not kept where this console can read it.";
export const LOG_IS_ON_THE_LOGS_SCREEN = "The application's warnings and errors are on the Logs page.";
export const LOGS_LINK = "Open Logs";
export const FAILURE_MESSAGES_STAY_ON_THE_SERVER = "A failure is shown by its kind; its message stays on the server.";

/** The windows offered, in hours. The API's own bound is ninety days. */
export const WINDOWS: readonly { readonly hours: number; readonly label: string }[] = [
  { hours: 24, label: "Last 24 hours" },
  { hours: 24 * 7, label: "Last 7 days" },
  { hours: 24 * 28, label: "Last 4 weeks" },
];

export const DEFAULT_HOURS = 24 * 7;

export function errorsApiPath(hours: number): string {
  return `${ERRORS_API_PATH}?hours=${String(hours)}`;
}

/** What a request's front-half columns say when the gate's front half did not run for it. */
export const NOT_SCREENED = "Not recorded";

/** How the agent was chosen, in words, from `brain.gate.select.SelectionStage`. */
export const STAGE_WORDS: Readonly<Record<string, string>> = {
  addressed: "named by the person",
  binding: "bound to the channel",
  rule: "chosen by a rule",
  classifier: "chosen by the classifier",
  default: "the default",
};

/** The agent a request was answered as, and how it was chosen (M3.6.3). */
export function agentWords(agent: string | null | undefined, stage: string | null | undefined): string {
  if (!agent) {
    return NOT_SCREENED;
  }
  return stage ? `${agent} (${STAGE_WORDS[stage] ?? stage})` : agent;
}

/** Why the lane was chosen, in words, from `brain.gate.classify.LaneBasis`. */
export const LANE_BASIS_WORDS: Readonly<Record<string, string>> = {
  requested: "asked for by the person",
  exact_intent: "an exact question shape",
  fast_refused: "fast lane asked for, not an exact shape",
  long_question: "a long question",
  task_phrase: "worded as a piece of work",
  default: "the default",
};

/** Why the tier was chosen, in words, from `brain.models.routing.TierBasis`. */
export const TIER_BASIS_WORDS: Readonly<Record<string, string>> = {
  fast_lane: "the fast lane takes no model",
  pinned: "pinned",
  task_lane: "the task lane's tier",
  default: "the default",
  tool_floor: "raised for tool use",
  residency_floor: "raised for residency",
  context: "raised for the prompt's size",
};

/** A routed value and the words for why, or `NOT_SCREENED` when the row holds no value. */
function withBasis(
  value: string | null | undefined,
  basis: string | null | undefined,
  words: Readonly<Record<string, string>>,
): string {
  if (!value) {
    return NOT_SCREENED;
  }
  return basis ? `${value} (${words[basis] ?? basis})` : value;
}

/** The lane a request was routed to, and why (M3.6.3). */
export function laneWords(lane: string | null | undefined, basis: string | null | undefined): string {
  return withBasis(lane, basis, LANE_BASIS_WORDS);
}

/** The tier a request's model call was routed to, and why (M3.6.3). */
export function tierWords(tier: string | null | undefined, basis: string | null | undefined): string {
  return withBasis(tier, basis, TIER_BASIS_WORDS);
}

/** The model that answered and its provider, or `NOT_SCREENED` when none did. */
export function modelWords(model: string | null | undefined, provider: string | null | undefined): string {
  if (!model) {
    return NOT_SCREENED;
  }
  return provider ? `${model} (${provider})` : model;
}

/** How a request ended, in words, from `brain.ops.telemetry.RequestStatus`. */
export const STATUS_WORDS: Readonly<Record<string, string>> = {
  failed: "Failed",
  degraded: "Degraded",
};

export function readErrors(payload: unknown): ErrorsBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { jobs?: unknown; requests?: unknown };
  if (!Array.isArray(body.jobs) || !Array.isArray(body.requests)) {
    return null;
  }
  return payload as ErrorsBody;
}
