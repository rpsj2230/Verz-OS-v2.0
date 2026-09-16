/**
 * What the Scheduled jobs screen asks for and says. No React.
 *
 * `brain.jobs_routes` answers every job the worker's schedule starts, how each last went, and
 * what a person has done to it, and takes three controls: pause, resume and run now. Each is a
 * row the worker's tick reads (`brain.ops.schedule_control`), so the sentences below say what the
 * worker will do and when, rather than that something happened.
 *
 * **`docs/screens.html` draws Live runs in the Operate menu and no jobs screen**, so this sits
 * directly under Live runs and is drawn in its register: a table, and the facts the table cannot
 * carry said in words beneath it.
 *
 * **A failed run is shown by its kind.** The API sends the exception's type and never its message,
 * because a message can quote a value, and the page says the message is kept on the server.
 *
 * **Nothing here decides who may see or control a job.** `may_control` and
 * `controls_switched_on` only decide whether buttons are drawn; each control asks again.
 *
 * Task ids: M27.8.13
 */

import type { components } from "../api/schema";
import { durationWords } from "./liveRunsQuery";

export type JobsBody = components["schemas"]["JobsPage"];
export type JobRow = components["schemas"]["JobView"];

export const JOBS_API_PATH = "/jobs";
export const JOBS_PATH = "/jobs";
export const JOBS_LABEL = "Scheduled jobs";
export const JOBS_CRUMB = "Operate › Scheduled jobs";
export const JOBS_LEDE =
  "Every job the worker runs on a schedule, how it last went, and the controls to pause one or " +
  "run one now.";

export const READING_JOBS = "Reading the schedule.";
export const NO_JOBS = "There is no scheduled job this screen can show you.";
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";
export const UNREADABLE_ANSWER =
  "The API answered in a shape this console does not read, so no job is listed. The console and " +
  "the API are probably from different releases.";
export const JOBS_CAPTION = "Scheduled jobs, how each last went, and what has been done to it";

export const PAUSE = "Pause";
export const RESUME = "Resume";
export const RUN_NOW = "Run now";
export const KEEP_IT = "Leave it as it is";

export const NEVER_RUN = "Has not run on this install.";
export const STILL_GOING = "Started and has not recorded finishing.";
export const NEVER_SUCCEEDED = "Never";
export const MESSAGE_KEPT_ON_THE_SERVER =
  "The failure's message is kept in the run record on the server and is not shown here, because " +
  "a message can quote a value.";

export const CONTROLS_SWITCHED_OFF =
  "Pausing a job and running one now are switched off on this install. An administrator switches " +
  "them on under Install, Features. A paused job can still be resumed.";
export const CANNOT_HEADING = "What this screen cannot do";
export const NO_RUN_CAN_BE_STOPPED =
  "A run that has started cannot be stopped from here, because nothing in the platform can stop " +
  "one. Pausing a job stops the schedule starting it again.";
export const EVERY_CHANGE_IS_IN_THE_AUDIT_TRAIL =
  "A pause and a request to run show who made them last and when. Every pause, resume and run " +
  "request, and who made it, is kept in the audit trail.";

/** The outcome words, from `brain.tables.schedule.OUTCOMES`. */
export const OUTCOME_WORDS: Readonly<Record<string, string>> = {
  ok: "Finished",
  failed: "Failed",
  refused: "Reported only",
};

export function pausePath(name: string): string {
  return `${JOBS_API_PATH}/${encodeURIComponent(name)}/pause`;
}
export function resumePath(name: string): string {
  return `${JOBS_API_PATH}/${encodeURIComponent(name)}/resume`;
}
export function runPath(name: string): string {
  return `${JOBS_API_PATH}/${encodeURIComponent(name)}/run`;
}

export type JobAction = "pause" | "resume" | "run";

export const ACTION_LABELS: Readonly<Record<JobAction, string>> = {
  pause: PAUSE,
  resume: RESUME,
  run: RUN_NOW,
};

export function actionPath(action: JobAction, name: string): string {
  return action === "pause" ? pausePath(name) : action === "resume" ? resumePath(name) : runPath(name);
}

export function actionQuestion(action: JobAction, row: JobRow): string {
  return action === "pause"
    ? `Pause ${row.control}?`
    : action === "resume"
      ? `Resume ${row.control}?`
      : `Run ${row.control} now?`;
}

/** What happens, to what, including what stops holding while a job is paused. */
export function actionConsequence(action: JobAction, row: JobRow): string {
  if (action === "pause") {
    return (
      `The worker stops starting ${row.control} from its next tick. It stays owed and its lateness ` +
      `keeps growing until it is resumed. While it is paused, this is not being kept true: ${row.keeps_true}`
    );
  }
  if (action === "resume") {
    return `The worker starts ${row.control} again the next time it is owed a run.`;
  }
  return (
    `The worker starts ${row.control} on its next tick, through the same lock and the same run ` +
    "record as a scheduled run, whether or not it is paused."
  );
}

/** Anything further this case has to say. */
export function actionWarning(action: JobAction, row: JobRow): string | undefined {
  if (action === "run" && row.report_only) {
    return "It runs in report-only mode, because nobody has released it: it reports what it would do and does not do it.";
  }
  return undefined;
}

export function doneSentence(action: JobAction, row: JobRow): string {
  return action === "pause"
    ? `${row.control} is paused. The worker will not start it again until it is resumed.`
    : action === "resume"
      ? `${row.control} is resumed.`
      : `${row.control} will be started on the worker's next tick.`;
}

/** The last run, in words. */
export function lastRunWords(row: JobRow): string {
  if (row.last_started_at === null || row.last_started_at === undefined) {
    return NEVER_RUN;
  }
  if (row.last_outcome === null || row.last_outcome === undefined) {
    return STILL_GOING;
  }
  const word = OUTCOME_WORDS[row.last_outcome] ?? row.last_outcome;
  if (row.last_outcome === "failed") {
    return row.last_failure_kind ? `${word}: ${row.last_failure_kind}` : word;
  }
  return row.last_report ? `${word}: ${row.last_report}` : word;
}

/** The state column, in words. Paused first, because it is the one a person did. */
export function stateWords(row: JobRow): string[] {
  const words: string[] = [];
  if (row.paused) {
    words.push(`Paused by ${row.pause_changed_by ?? "somebody"}`);
  }
  if (row.run_pending) {
    words.push(`Run asked for by ${row.run_requested_by ?? "somebody"}`);
  }
  if (row.owed) {
    words.push(
      row.late_by_seconds ? `Owed, late by ${durationWords(row.late_by_seconds)}` : "Owed a run now",
    );
  }
  if (row.report_only) {
    words.push("Report only");
  }
  return words.length === 0 ? ["On schedule"] : words;
}

export function readJobs(payload: unknown): JobsBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { jobs?: unknown; as_of?: unknown };
  if (!Array.isArray(body.jobs) || typeof body.as_of !== "string") {
    return null;
  }
  return payload as JobsBody;
}
