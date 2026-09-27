/**
 * What the Errors screen asks for and says. No React.
 *
 * `brain.error_routes` answers the failures the database keeps: scheduled jobs that failed, by the
 * kind of failure and never its message, and questions that failed or degraded, by the reference a
 * person is shown beside a failure. Each list is narrowed by the decision that already says who may
 * see that record, and neither carries a count.
 *
 * **The process log is not here, and the page says where it is.** The application writes its log
 * to its container's standard output and keeps no copy the console can read, and the answer carries
 * that as a field so the sentence leaves the page on the day a log store exists.
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
