/**
 * What the Stop screen and the header's Stop control ask for and say. No React.
 *
 * `brain.halt_routes` answers what is stopped this reader may see, stops at once and resumes with
 * a written reason, and `brain.ops.halt_store` decides all of it. Nothing here decides who may stop
 * what: a reader who may not open the screen is answered 404 and the control is not drawn, and a
 * stop outside the reader's scope is refused by the API whatever this page drew.
 *
 * **Stopping is one press and says nothing.** The control and the screen's stop send no reason
 * unless the person typed one, and the API stores the fixed sentence `STOPPED_FROM_THE_CONSOLE`
 * with who pressed it and when (`brain.ops.halt_store.A_STOP_NEEDS_NO_WORDS_AND_A_RESUME_DOES`).
 * Resuming needs a written reason, said before anything is sent.
 *
 * Task ids: M27.12.4, M27.15.14, M27.2.8
 */

import type { components } from "../api/schema";
import type { StopOffer } from "../layout/navigationQuery";

export type HaltsBody = components["schemas"]["HaltsView"];
export type HaltRow = components["schemas"]["StoppedView"];
export type Resumed = components["schemas"]["ResumedView"];
export type HaltScope = HaltRow["scope"];

/** Where the API keeps the halts, under the API base. The console's routes name the same two. */
export const HALTS_API_PATH = "/halts";
export const RESUME_API_PATH = "/halts/resume";

/** The console address of the Stop screen. */
export const STOP_PATH = "/stop";

/** The sentence a stop with no reason is stored with, as `brain.ops.halt_store` holds it. */
export const STOPPED_FROM_THE_CONSOLE = "Stopped from the console Stop control";

/** The shortest reason a resume may carry, as `brain.ops.halt.MINIMUM_REASON` holds it. */
export const MINIMUM_REASON = 12;

export const STOP_HEADING = "Stop";
export const STOP_LEDE =
  "Stop work at once: everything, one department, one person or one connector. A stop takes one press and never ends on its own. Resuming needs a written reason.";
export const READING_HALTS = "Reading what is stopped.";
export const NOTHING_STOPPED = "Nothing you may see is stopped.";
export const NOTHING_STOPPED_TITLE = "Nothing is stopped";
export const CANNOT_TELL =
  "The list of stops cannot be read just now, so the Brain is treating everything as stopped and is starting no new work. Nothing is being lost.";
export const UNREADABLE_ANSWER =
  "The API answered in a shape this console does not read, so nothing is listed. The console and the API are probably from different releases.";

export const STOP_LABEL = "Stop";
export const STOP_EVERYTHING = "Stop everything";
export const STOPPING = "Stopping.";
export const STOPPED_STATUS = "Stopped";
export const STOP_FORM_LABEL = "Stop something";
export const SCOPE_LABEL = "What to stop";
export const TARGET_LABEL = "Which one";
export const TARGET_HINT = "A department's short name, a person's id, or a connector's name.";
export const REASON_LABEL = "Why, if you want to say";
export const REASON_HINT = "Optional. Without one, the stop is recorded as stopped from the console, with your name and the time.";
export const NAME_ONE = "Say which one to stop.";

export const RESUME_LABEL = "Resume";
export const RESUME_REASON_LABEL = "Why it is safe to resume";
export const RESUME_REASON_HINT = `Required, at least ${String(MINIMUM_REASON)} characters. The next person to read it needs to know whether the cause was fixed.`;
export const SAY_WHY = `Write why it is safe to resume, in at least ${String(MINIMUM_REASON)} characters.`;
export const KEEP_IT_STOPPED = "Keep it stopped";
export const NOT_RESUMED = "It was not resumed";
export const NOT_STOPPED = "It was not stopped";

/** The axes nothing asks yet, said rather than offered. */
export const NOT_ASKED_YET_LEAD = "Cannot be stopped yet, because nothing that starts work asks it:";

/** The scope's name in words. */
export const SCOPE_WORDS: Readonly<Record<HaltScope, string>> = {
  everything: "Everything",
  department: "One department",
  person: "One person",
  connector: "One connector",
  agent: "One agent",
};

/** One stop in words: what it covers. */
export function haltTitle(row: Pick<HaltRow, "scope" | "target">): string {
  return row.scope === "everything" ? "Everything" : `${SCOPE_WORDS[row.scope]}: ${row.target}`;
}

/** The body that stops one thing, with the reason only when the person gave one. */
export function stopBody(scope: HaltScope, target: string, reason: string): { scope: HaltScope; target: string; reason?: string } {
  const said = reason.trim();
  return said === "" ? { scope, target: target.trim() } : { scope, target: target.trim(), reason: said };
}

/** The body that resumes one stop. */
export function resumeBody(row: Pick<HaltRow, "scope" | "target">, reason: string): { scope: HaltScope; target: string; reason: string } {
  return { scope: row.scope, target: row.target, reason: reason.trim() };
}

/** The confirmation question for a resume, naming what it lifts. */
export function resumeQuestion(row: Pick<HaltRow, "scope" | "target">): string {
  return `Resume ${haltTitle(row).toLowerCase()}?`;
}

/** What a resume does, said in the confirmation. */
export function resumeConsequence(row: Pick<HaltRow, "declared_by">): string {
  return `New work starts again at once. This lifts a stop ${row.declared_by} made, and your reason is recorded beside it.`;
}

/** Why a resume cannot be sent yet, or null. */
export function resumeProblem(reason: string): string | null {
  return reason.trim().length < MINIMUM_REASON ? SAY_WHY : null;
}

/** Why a stop cannot be sent yet, or null. */
export function stopProblem(scope: HaltScope, target: string): string | null {
  return scope !== "everything" && target.trim() === "" ? NAME_ONE : null;
}

function isRow(value: unknown): value is HaltRow {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const row = value as Record<string, unknown>;
  return (
    typeof row.scope === "string" &&
    row.scope in SCOPE_WORDS &&
    typeof row.target === "string" &&
    typeof row.declared_by === "string" &&
    typeof row.at === "string" &&
    typeof row.reason === "string"
  );
}

/** `HaltsView`, or null when the body is not one. */
export function readHalts(payload: unknown): HaltsBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as Record<string, unknown>;
  if (
    typeof body.known !== "boolean" ||
    typeof body.may_stop_everything !== "boolean" ||
    !Array.isArray(body.halts) ||
    !body.halts.every(isRow) ||
    !Array.isArray(body.gaps) ||
    !body.gaps.every((one) => typeof one === "string") ||
    !Array.isArray(body.not_asked_yet) ||
    !body.not_asked_yet.every((one) => typeof one === "string" && one in SCOPE_WORDS)
  ) {
    return null;
  }
  return body as unknown as HaltsBody;
}

/** `ResumedView`, or null. */
export function readResumed(payload: unknown): Resumed | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as Record<string, unknown>;
  if (typeof body.said !== "string" || typeof body.overrides_somebody_else !== "boolean") {
    return null;
  }
  return { said: body.said, overrides_somebody_else: body.overrides_somebody_else };
}

/** The scopes a reader may choose on the stop form: every scope something asks. */
export function offeredScopes(body: HaltsBody): HaltScope[] {
  const order: HaltScope[] = ["everything", "department", "person", "connector", "agent"];
  return order.filter((one) => !body.not_asked_yet.includes(one) && (one !== "everything" || body.may_stop_everything));
}

/**
 * What one press of the header's control stops, from the menu's offer: everything, or each
 * department the reader's console names. Empty for no offer, and no control is then drawn.
 */
export function oneTouchStops(stop: StopOffer, departments: readonly string[]): Array<{ scope: HaltScope; target: string }> {
  if (stop === "everything") {
    return [{ scope: "everything", target: "" }];
  }
  return stop === "departments" ? departments.map((one) => ({ scope: "department" as const, target: one })) : [];
}
