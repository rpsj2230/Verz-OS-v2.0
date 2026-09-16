/**
 * What the Retention and erasure screen asks the API for and sends it, how a hold is checked before
 * it is sent, and what a release is said to act on. No React.
 *
 * Two routes answer this screen. `brain.retention_routes` serves the newest retention report and
 * takes the four writes, and `brain.erasure_routes` says who may be drawn which control, what each
 * act does in words, how long each kind of thing is kept, and that the export log and the deletion
 * queue are not recorded. Neither is a decision this module makes again: a flag decides whether a
 * control is drawn, and the write route decides whether it is accepted.
 *
 * **A hold is checked here against the route's own request body before it is sent.** The patterns
 * below are `brain.audit.ledger.IDENTIFIER` and `FIELD_NAME` as the route declares them, and
 * `tests/retention-page.test.tsx` reads them out of the generated OpenAPI document, so a pattern
 * that drifted is a failed test rather than a 422 in front of an administrator. Each problem is a
 * sentence saying what to do about it, which is `docs/admin-console.md`'s rule about validation.
 *
 * **A release names the numbers it will act on, from the report the reader is looking at.** The
 * confirmation joins those counts to `brain.erasure_routes.RELEASING`, so the person agreeing reads
 * what the sweep found and what it will then do, in the API's words. The counts are the whole
 * estate's, and only a reader the report is shown to at all can see them, because
 * `brain.console.govern_surfaces.retention_view` withholds the report from anybody else.
 *
 * Task ids: none
 */

import type { components } from "../api/schema";

export type RetentionAnswer = components["schemas"]["RetentionAnswer"];
export type Report = components["schemas"]["ReportView"];
export type StoreLine = components["schemas"]["StoreLine"];
export type CitedHold = components["schemas"]["CitedHoldView"];
export type Controls = components["schemas"]["RetentionControlsView"];
export type Kept = components["schemas"]["KeptView"];
export type HoldBody = components["schemas"]["HoldBody"];
export type LiftBody = components["schemas"]["LiftBody"];
export type ReleaseBody = components["schemas"]["ReleaseBody"];

export const RETENTION_API_PATH = "/govern/retention";
export const CONTROLS_API_PATH = "/govern/retention/controls";
export const RELEASE_API_PATH = "/govern/retention/release";
export const WITHDRAWAL_API_PATH = "/govern/retention/withdrawal";
export const HOLD_API_PATH = "/govern/legal-holds";
export const LIFT_API_PATH = "/govern/legal-holds/lift";

/** A reference: what a hold, a subject and an actor must look like. `IDENTIFIER`. */
export const IDENTIFIER_PATTERN = "^[A-Za-z0-9_.@-]{1,128}$";
/** A reason code: a field name, never prose. `FIELD_NAME`. */
export const REASON_CODE_PATTERN = "^[a-z][a-z0-9_]*(?:\\.[a-z][a-z0-9_]*)*$";
export const REASON_CODE_MAX = 80;
/** How many people one hold may name. A company-wide hold is one switch instead. */
export const MAX_HELD_NAMES = 500;

const IDENTIFIER = new RegExp(IDENTIFIER_PATTERN);
const REASON_CODE = new RegExp(REASON_CODE_PATTERN);

/** The report, or null for no report, whichever of the reasons there is none. */
export function reportOf(payload: RetentionAnswer | null): Report | null {
  return payload?.report ?? null;
}

// ----------------------------------------------------------------------------- a release
/** Whether a release may be offered on this report at all, before anybody's authority. */
export function releasable(report: Report | null): report is Report {
  return report !== null && report.report_only && report.failure === null && !report.released;
}

function sum(lines: readonly StoreLine[], pick: (line: StoreLine) => number): number {
  return lines.reduce((total, line) => total + pick(line), 0);
}

/**
 * What the report says a release will act on, in one sentence of numbers.
 *
 * Only reached stores are named, because a store the sweep could not reach is one it leaves alone
 * whether or not it is released, and naming it beside a removal would read as a store it empties.
 */
export function releaseCounts(report: Report, asOf: string): string {
  const reached = report.stores.filter((line) => line.reached);
  const removing = reached.filter((line) => line.due > 0).map((line) => line.store);
  const due = sum(reached, (line) => line.due);
  const queued = sum(reached, (line) => line.queued);
  const held = sum(reached, (line) => line.held);
  const where = removing.length === 0 ? "" : ` in ${removing.join(", ")}`;
  return (
    `As of ${asOf}, ${String(due)} items were past their window${where}; ` +
    `${String(queued)} were queued for the rule that removes them and ${String(held)} were held.`
  );
}

// ---------------------------------------------------------------------------------- a hold
export interface HoldForm {
  readonly holdId: string;
  readonly reasonCode: string;
  /** People the hold covers, as references, separated by spaces, commas or lines. */
  readonly subjects: string;
  /** People whose actions the hold covers, the same way. */
  readonly actors: string;
  readonly everybody: boolean;
}

export const EMPTY_HOLD: HoldForm = {
  holdId: "",
  reasonCode: "",
  subjects: "",
  actors: "",
  everybody: false,
};

/** The references typed into a box, in the order typed, each once. */
export function names(text: string): readonly string[] {
  return [...new Set(text.split(/[\s,]+/).filter((one) => one !== ""))];
}

/** Everything wrong with a hold before it is sent, each a sentence saying what to do. */
export function holdProblems(form: HoldForm): readonly string[] {
  const problems: string[] = [];
  if (!IDENTIFIER.test(form.holdId)) {
    problems.push(
      "Give the hold a reference of up to 128 letters, digits, dots, dashes, underscores or at " +
        "signs, with no spaces, such as the matter number it is for.",
    );
  }
  if (form.reasonCode.length > REASON_CODE_MAX || !REASON_CODE.test(form.reasonCode)) {
    problems.push(
      "Give a reason code in lower case with underscores, such as litigation or " +
        "regulator.request, and no names: the code outlives every other record.",
    );
  }
  const subjects = names(form.subjects);
  const actors = names(form.actors);
  const bad = [...subjects, ...actors].filter((one) => !IDENTIFIER.test(one));
  if (bad.length > 0) {
    problems.push(`These are not references to a person: ${bad.join(", ")}.`);
  }
  if (subjects.length > MAX_HELD_NAMES || actors.length > MAX_HELD_NAMES) {
    problems.push(
      `Name at most ${String(MAX_HELD_NAMES)} people in each box, or hold everybody instead.`,
    );
  }
  if (!form.everybody && subjects.length === 0 && actors.length === 0) {
    problems.push(
      "Name at least one person the hold covers or whose actions it covers, or hold everybody. " +
        "A hold that names nobody holds nothing.",
    );
  }
  return problems;
}

/** The request body for a hold that has no problems. */
export function holdBody(form: HoldForm): HoldBody {
  return {
    hold_id: form.holdId,
    reason_code: form.reasonCode,
    subjects: [...names(form.subjects)],
    actors: [...names(form.actors)],
    all_subjects: form.everybody,
  };
}

/** The question a hold's confirmation asks, naming what it covers. */
export function holdQuestion(body: HoldBody): string {
  if (body.all_subjects) {
    return `Place legal hold ${body.hold_id} over everybody?`;
  }
  const subjects = body.subjects ?? [];
  const actors = body.actors ?? [];
  const covered = [
    subjects.length === 0 ? "" : `${String(subjects.length)} named people`,
    actors.length === 0 ? "" : `the actions of ${String(actors.length)} named people`,
  ]
    .filter((one) => one !== "")
    .join(" and ");
  return `Place legal hold ${body.hold_id} over ${covered}?`;
}

/** Whether a hold reference to lift is well formed. */
export function liftProblems(holdId: string): readonly string[] {
  return IDENTIFIER.test(holdId)
    ? []
    : ["Give the reference of the hold to lift, exactly as it was placed."];
}
