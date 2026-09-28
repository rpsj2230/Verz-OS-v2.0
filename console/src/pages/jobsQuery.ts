/**
 * What the Background jobs pages ask for and say. No React.
 *
 * `brain.jobs_routes` answers every job the worker's schedule starts and how each last went, one
 * job whole with its run figures, and one job's past runs, and takes three controls: pause, resume
 * and run now. Each control is a row the worker's tick reads (`brain.ops.schedule_control`), so the
 * sentences below say what the worker will do and when, rather than that something happened.
 *
 * **A failed run is shown by its kind.** The API sends the exception's type and never its message,
 * because a message can quote a value.
 *
 * **A person is named, never shown as a principal id.** The API sends display names beside the rows
 * that name somebody; an id with no name is said as "somebody", and the id stays out of the text.
 *
 * **Nothing here decides who may see or control a job.** `may_control` and `controls_switched_on`
 * only decide whether a control is drawn; each control asks again.
 *
 * Task ids: M27.8.13, M27.15.47
 */

import type { components } from "../api/schema";
import { durationWords, jobName } from "./operations/parts";

export type JobsBody = components["schemas"]["JobsPage"];
export type JobRow = components["schemas"]["JobView"];
export type JobDetailBody = components["schemas"]["JobDetail"];
export type JobPeriod = components["schemas"]["JobPeriodView"];
export type JobRun = components["schemas"]["JobRunView"];

export const JOBS_API_PATH = "/jobs";
export const JOBS_PATH = "/jobs";
export const JOBS_LABEL = "Background jobs";
export const JOBS_LEDE = "Every job the worker runs on a schedule, how it last went, and what has been done to it.";

export const READING_JOBS = "Loading the schedule.";
export const NO_JOBS = "No background jobs to show";
export const NO_JOBS_MORE = "A job appears here once the worker's schedule starts it and it is offered to you.";
export const JOBS_CAPTION = "Background jobs";

export const PAUSE = "Pause";
export const RESUME = "Resume";
export const RUN_NOW = "Run now";
export const KEEP_IT = "Leave it as it is";

export const NEVER_RUN = "Not run yet";
export const STILL_GOING = "Started, not finished";
export const NEVER_SUCCEEDED = "Never";
export const ON_SCHEDULE = "On schedule";
export const SOMEBODY = "somebody";

export const CONTROLS_SWITCHED_OFF =
  "Pausing a job and running one now are switched off on this install; they are switched on under Features. A paused job can still be resumed.";
export const NO_RUN_CAN_BE_STOPPED = "A run that has started cannot be stopped here; pausing stops the schedule starting it again.";
export const EVERY_CHANGE_IS_IN_THE_AUDIT_TRAIL = "Every pause, resume and run request is kept in the audit log with who made it.";
export const MESSAGE_KEPT_ON_THE_SERVER = "A failure is shown by its kind; its message stays on the server.";

/** The outcome words, from `brain.tables.schedule.OUTCOMES`, and the history's own word for a run with no finish. */
export const OUTCOME_WORDS: Readonly<Record<string, string>> = {
  ok: "Finished",
  failed: "Failed",
  refused: "Report only",
  unfinished: "Not finished",
};

export function outcomeWords(outcome: string): string {
  return OUTCOME_WORDS[outcome] ?? outcome;
}

/** Where one job's page is, and its two other views. */
export function jobAddress(control: string, view?: string): string {
  const base = `${JOBS_PATH}/${encodeURIComponent(control)}`;
  return view === undefined ? base : `${base}/${view}`;
}

export function jobApiPath(control: string): string {
  return `${JOBS_API_PATH}/${encodeURIComponent(control)}`;
}

export function jobRunsApiPath(control: string): string {
  return `${jobApiPath(control)}/runs`;
}

export function pausePath(name: string): string {
  return `${jobApiPath(name)}/pause`;
}
export function resumePath(name: string): string {
  return `${jobApiPath(name)}/resume`;
}
export function runPath(name: string): string {
  return `${jobApiPath(name)}/run`;
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

/** The controls a row offers, in the order they are drawn. Presentation only: each asks again. */
export function actionsFor(row: JobRow, switchedOn: boolean, mayControl: boolean): JobAction[] {
  if (!mayControl) {
    return [];
  }
  const actions: JobAction[] = [];
  if (row.paused) {
    actions.push("resume");
  } else if (switchedOn && row.runnable) {
    actions.push("pause");
  }
  if (switchedOn && row.runnable) {
    actions.push("run");
  }
  return actions;
}

export function actionQuestion(action: JobAction, row: JobRow): string {
  const name = jobName(row.control);
  return action === "pause" ? `Pause ${name}?` : action === "resume" ? `Resume ${name}?` : `Run ${name} now?`;
}

/** What happens, to what, including what stops holding while a job is paused. */
export function actionConsequence(action: JobAction, row: JobRow): string {
  const name = jobName(row.control);
  if (action === "pause") {
    return `The worker stops starting ${name} from its next tick, until it is resumed. While it is paused, this is not kept true: ${row.keeps_true}`;
  }
  if (action === "resume") {
    return `The worker starts ${name} again the next time it is owed a run.`;
  }
  return `The worker starts ${name} on its next tick, whether or not it is paused.`;
}

/** Anything further this case has to say. */
export function actionWarning(action: JobAction, row: JobRow): string | undefined {
  if (action === "run" && row.report_only) {
    return "It runs in report-only mode, because nobody has released it: it reports what it would do and does not do it.";
  }
  return undefined;
}

export function doneSentence(action: JobAction, row: JobRow): string {
  const name = jobName(row.control);
  return action === "pause"
    ? `${name} is paused. The worker will not start it again until it is resumed.`
    : action === "resume"
      ? `${name} is resumed.`
      : `${name} will be started on the worker's next tick.`;
}

/** A person the API named, by their display name, or "somebody" when no name came with the id. */
export function personWords(id: string | null | undefined, people: Readonly<Record<string, string>> | undefined): string {
  if (id === null || id === undefined) {
    return SOMEBODY;
  }
  return people?.[id] ?? SOMEBODY;
}

/** The last run, in words: its outcome and its report or its kind of failure. */
export function lastRunWords(row: JobRow): string {
  if (row.last_started_at === null || row.last_started_at === undefined) {
    return NEVER_RUN;
  }
  if (row.last_outcome === null || row.last_outcome === undefined) {
    return STILL_GOING;
  }
  const word = outcomeWords(row.last_outcome);
  if (row.last_outcome === "failed") {
    return row.last_failure_kind ? `${word}: ${row.last_failure_kind}` : word;
  }
  return word;
}

/** How often a job runs, in words. */
export function everyWords(seconds: number): string {
  return `Every ${durationWords(seconds)}`;
}

/** The state words for a row, paused first because it is the one a person did. */
export interface StateWord {
  readonly word: string;
  readonly tone: "ok" | "warn" | "crit" | "plain";
}

export function stateWords(row: JobRow): StateWord[] {
  const words: StateWord[] = [];
  if (row.paused) {
    words.push({ word: "Paused", tone: "warn" });
  }
  if (!row.runnable) {
    words.push({ word: "Cannot start yet", tone: "plain" });
  }
  if (row.run_pending) {
    words.push({ word: "Run asked for", tone: "plain" });
  }
  if (row.owed) {
    words.push({
      word: row.late_by_seconds ? `Late by ${durationWords(row.late_by_seconds)}` : "Owed a run",
      tone: "warn",
    });
  }
  if (row.report_only) {
    words.push({ word: "Report only", tone: "plain" });
  }
  if (row.last_outcome === "failed") {
    words.push({ word: "Last run failed", tone: "crit" });
  }
  return words.length === 0 ? [{ word: ON_SCHEDULE, tone: "ok" }] : words;
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

export function readJobDetail(payload: unknown): JobDetailBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { job?: unknown; periods?: unknown };
  if (typeof body.job !== "object" || body.job === null || !Array.isArray(body.periods)) {
    return null;
  }
  return payload as JobDetailBody;
}

/** One window's figures, or undefined when the API sent none for it. */
export function periodOf(body: JobDetailBody, range: string): JobPeriod | undefined {
  return body.periods.find((one) => one.range === range);
}
