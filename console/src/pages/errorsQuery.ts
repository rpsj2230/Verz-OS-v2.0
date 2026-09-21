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
 * Task ids: none
 */

import type { components } from "../api/schema";

export type ErrorsBody = components["schemas"]["ErrorsPage"];

export const ERRORS_API_PATH = "/errors";
export const ERRORS_PATH = "/errors";
export const ERRORS_LABEL = "Errors";
export const ERRORS_CRUMB = "Operate › Errors";
export const ERRORS_LEDE =
  "Scheduled jobs that failed and questions that failed or degraded, newest first. A person told " +
  "that something went wrong is shown a reference, and it is the reference listed here.";

export const READING_ERRORS = "Reading the failures.";
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";
export const UNREADABLE_ANSWER =
  "The API answered in a shape this console does not read, so no failure is listed. The console " +
  "and the API are probably from different releases.";

export const JOBS_HEADING = "Failed scheduled jobs";
export const JOBS_CAPTION = "Scheduled jobs whose run failed, newest first";
export const NO_JOB_FAILURES = "No scheduled job this screen can show you failed in this window.";
export const REQUESTS_HEADING = "Failed questions";
export const REQUESTS_CAPTION = "Questions that failed or degraded, newest first";
export const NO_REQUEST_FAILURES =
  "No question this screen can show you failed or degraded in this window.";
export const FULL_LIST =
  "This list came back full, so there were more failures in this window than it shows. Choose a " +
  "shorter window to see the rest.";
export const LOG_HEADING = "What this screen cannot show";
export const PROCESS_LOG_IS_NOT_KEPT =
  "The application's own log is written to its container's standard output on the server and is " +
  "not kept anywhere this console can read, so it is not shown here.";
export const LOG_IS_ON_THE_LOGS_SCREEN =
  "The application's own warnings and errors, with every value taken out, are on the Logs screen.";
export const LOGS_LINK = "Open the Logs screen";
export const FAILURE_MESSAGES_STAY_ON_THE_SERVER =
  "A failed job's message is kept in its run record on the server and not shown here, because a " +
  "message can quote a value.";

/** The windows offered, in hours. The API's own bound is four weeks. */
export const WINDOWS: readonly { readonly hours: number; readonly label: string }[] = [
  { hours: 24, label: "The last day" },
  { hours: 24 * 7, label: "The last week" },
  { hours: 24 * 28, label: "The last four weeks" },
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
