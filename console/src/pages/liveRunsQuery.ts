/**
 * What the Live runs screen asks the API for, and what it says about the runs it cannot show.
 * No React.
 *
 * The split is `skillsQuery.ts`' and `governQuery.ts`': this decides what may be asked and what a
 * row is, the page renders it, so the case that is always wrong can be tested without mounting a
 * table. Here that case is an empty list, which on this screen reads as an idle install whether
 * or not a person is waiting on an answer.
 *
 * **The design draws Live runs in the Operate menu and nowhere else.** `docs/screens.html`
 * SCREEN 1 names it between the overview and the models screen, and no screen draws its body, so
 * this one is built in the register the overview is drawn in: cards, a table per list, and the
 * facts the lists cannot carry said in words under them. `brain.console.screens` gives its
 * purpose as what is executing, with its lane, its agent and how long it has been going.
 *
 * **What it lists is the scheduled controls, and three things it cannot list are said.**
 * `brain.operate_routes` gives the reasons: a question or an agent run is recorded when it
 * finishes and not while it runs, the queue driver's own rows are refused to the application on
 * purpose, and nothing in the platform can stop a run once it has started. Each is a field on the
 * response, so the sentence leaves this screen in the commit that makes it false rather than
 * going on being said. See `A_LIST_OF_RUNS_IS_READ_AS_EVERYTHING_THAT_IS_RUNNING`.
 *
 * **There is no stop control and no path one could be posted to.** See
 * `A_STOP_BUTTON_THAT_REACHES_NOTHING_IS_WORSE_THAN_NONE`.
 *
 * **Nothing here decides who may see a run.** `brain.console.operate.may_watch_unattended`
 * decides, behind the live runs screen's grant for what is running and the queue screen's for
 * what is waiting, and a reader holding neither is answered two empty lists, which is what an
 * install running nothing is answered. So the empty sentences below say nothing about grants.
 *
 * **No count is rendered.** The lists are narrowed per reader, so a number beside one is the
 * subtraction `CLAUDE.md` forbids, and these lists are short enough to read.
 *
 * Task ids: M27.2.2, M27.2.6
 */

import type { components } from "../api/schema";

/** The whole answer, as `brain.operate_routes.LiveRunsView` sends it. */
export type LiveRunsBody = components["schemas"]["LiveRunsView"];
/** One control running now. */
export type RunningControl = components["schemas"]["RunningControlView"];
/** One control owed a run. */
export type OwedControl = components["schemas"]["OwedControlView"];

/** Written down because an empty table on a screen headed live is read as an idle install. */
export const A_LIST_OF_RUNS_IS_READ_AS_EVERYTHING_THAT_IS_RUNNING =
  "A person opening a live runs screen reads the list as everything the install is doing. What " +
  "anything records while it runs is the scheduled controls, so that is what is listed, and the " +
  "work nothing records while it runs is named under the list rather than left to look absent: " +
  "a question being answered, an agent at work and a job in the queue.";

/** Written down because the design's Operate section invites a stop control on this screen. */
export const A_STOP_BUTTON_THAT_REACHES_NOTHING_IS_WORSE_THAN_NONE =
  "A control runs inside the worker holding a lock for its whole run, and nothing in the " +
  "platform ends one: the queue's cancellation is called by nothing, the job states that " +
  "describe cancelling are stored nowhere, and the halt stops new work rather than work in " +
  "progress. A button reaching none of those is refused or ignored every time it is pressed, " +
  "so the page says a run cannot be stopped here instead of offering one.";

/** Where the API keeps this screen. It declares no query parameter. */
export const LIVE_RUNS_API_PATH = "/operate/runs";

/**
 * The console address, which is the screen's key in `brain.console.screens` so that
 * `brain.ops.console_screens.routed_screen_keys` matches the route against the registry.
 */
export const LIVE_RUNS_PATH = "/runs";

/** The heading, in the design's own words from the Operate menu. */
export const LIVE_RUNS_LABEL = "Live runs";

/** Under the heading. */
export const LIVE_RUNS_LEDE =
  "What the install is running now and what is owed a run, with what each one keeps true.";

/** The two tables' headings and captions. */
export const RUNNING_HEADING = "Running now";
export const WAITING_HEADING = "Waiting";
export const RUNNING_CAPTION = "Scheduled controls that have started and not finished";
export const WAITING_CAPTION = "Scheduled controls owed a run and not yet started";
export const CANNOT_SHOW_HEADING = "What this screen cannot show";

/** An empty list, whichever reason it is empty for. Says nothing about grants or other rows. */
export const NOTHING_RUNNING = "Nothing this screen can show you is running.";
export const NOTHING_WAITING = "Nothing this screen can show you is waiting for a run.";

/** The three things the answer says it cannot show, each in words a person can act on. */
export const REQUESTS_IN_FLIGHT_ARE_NOT_RECORDED =
  "Questions being answered and agents at work are not listed, for any agent or any person. " +
  "The platform records a request when it finishes, so the Service levels screen shows it " +
  "afterwards, and nothing records a model call while it is being made.";
export const QUEUE_IS_NOT_READABLE =
  "Jobs waiting in the queue are not listed. The queue's own tables are closed to the " +
  "application on purpose, so this screen cannot read them; what is listed as waiting is the " +
  "schedule's own record of which controls are owed a run.";
export const NO_RUN_CAN_BE_STOPPED =
  "A run cannot be stopped from this screen, because nothing in the platform can stop one once " +
  "it has started. A run that has gone on too long is marked below, and the process holding it " +
  "has to be dealt with on the server.";

/** Beside a run that began longer ago than the scheduler's own line for asking about it. */
export function stalledNote(stalledAfterSeconds: number): string {
  return (
    `Started over ${durationWords(stalledAfterSeconds)} ago and has not recorded finishing: it ` +
    "is still going, or the process running it stopped."
  );
}

/** The mode column. The API's flag, in words. */
export const REPORT_ONLY = "Report only";
export const ACTING = "Acting";

/** The first-run column, in words. */
export const FIRST_RUN = "Never run before";

/** The two failure headings, which are different sentences on purpose. */
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";
export const SOMETHING_DID_NOT_WORK = "That did not work";

/** What is said when the API answered in a shape this console does not read. */
export const UNREADABLE_ANSWER =
  "The API answered in a shape this console does not read, so nothing is listed. The console " +
  "and the API are probably from different releases.";

/**
 * Read `brain.operate_routes.LiveRunsView` out of a response body, or null.
 *
 * Null rather than an empty answer, and the difference is what the page says: an empty answer
 * is a real one and is drawn as nothing running, so a console that turned a malformed body into
 * one would tell a person the install is idle on the strength of a parse failure. That is
 * `serviceLevelsQuery.readServiceLevels`' choice and its reason.
 */
export function readLiveRuns(payload: unknown): LiveRunsBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { as_of?: unknown; running?: unknown; waiting?: unknown };
  if (typeof body.as_of !== "string") {
    return null;
  }
  if (!Array.isArray(body.running) || !Array.isArray(body.waiting)) {
    return null;
  }
  return payload as LiveRunsBody;
}

/**
 * A length of time in words, to the two largest units that are not zero.
 *
 * Words rather than a clock face, because "01:05:00" beside a timestamp reads as another
 * timestamp. Under a minute is said as that rather than as seconds, since a run's age is read to
 * decide whether to worry and a count of seconds invites a precision the tick does not have.
 */
export function durationWords(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  if (whole < 60) {
    return "under a minute";
  }
  const units: readonly (readonly [string, number])[] = [
    ["day", 86_400],
    ["hour", 3_600],
    ["minute", 60],
  ];
  const parts: string[] = [];
  let left = whole;
  for (const [name, size] of units) {
    const count = Math.floor(left / size);
    left -= count * size;
    if (count > 0 && parts.length < 2) {
      parts.push(`${String(count)} ${name}${count === 1 ? "" : "s"}`);
    }
  }
  return parts.join(" ");
}

/**
 * How long a run has been going, measured against the instant the API answered.
 *
 * The server's instant rather than the browser's clock, so a laptop whose clock is wrong does
 * not make a run look stalled or new. A start after `as_of` is a clock the database and the
 * application disagree about, and it is said as under a minute rather than as a negative age.
 */
export function runningFor(startedAt: string, asOf: string): string {
  return durationWords((Date.parse(asOf) - Date.parse(startedAt)) / 1000);
}
