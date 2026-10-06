/**
 * What the Department page asks for its budget against pace and its knowledge coverage, and how
 * each answer is read and put into words. No React.
 *
 * **Both are the API's figures and the page draws them as sent.** `brain.department_view_routes`
 * decides who is a head, asks `brain.console.scoped_authority.department_pace` and
 * `department_coverage`, and answers anybody else with the one 404, which the page reads as "this
 * block is not yours" and leaves the block out. Nothing here divides, sums or compares: the two
 * fractions, whether spend is ahead of time, and the count in each freshness band all arrive
 * computed, so a reader's browser cannot arrive at a figure the server did not send.
 *
 * **The area is never drawn by its short name.** A department's coverage is one area, the
 * department itself, so the page shows its bands under the department's own heading rather than
 * repeating the slug the rest of the page keeps in Advanced.
 *
 * **No total is drawn because none is sent.** A coverage row is what this reader may read in the
 * department, and the pace carries two fractions and no amount; the ceiling and the sum are the
 * Budget screen's.
 *
 * Task ids: M33.2.1.3, M33.2.1.4
 */

import type { components } from "../../api/schema";

/** `brain.department_view_routes.DepartmentPaceView`. */
export type DepartmentPaceBody = components["schemas"]["DepartmentPaceView"];
/** One ceiling against its period. */
export type PaceBody = components["schemas"]["PaceView"];
/** `brain.department_view_routes.DepartmentCoverageView`. */
export type DepartmentCoverageBody = components["schemas"]["DepartmentCoverageView"];
/** One area's documents by freshness. */
export type CoverageAreaBody = components["schemas"]["CoverageAreaView"];

/** Where the API keeps the head's pace, under `brain.department_view_routes.PACE_PATH`. */
export const DEPARTMENT_PACE_API_PATH = "/console/department/pace";

/** Where the API keeps the head's coverage, under `brain.department_view_routes.COVERAGE_PATH`. */
export const DEPARTMENT_COVERAGE_API_PATH = "/console/department/coverage";

/** The freshness bands in the order a reader reads them, `brain.console.operate.COVERAGE_BANDS`. */
export const COVERAGE_BANDS = ["live", "ageing", "stale", "unstated"] as const;

/** What each band is called on the page. */
export const BAND_WORDS: Readonly<Record<(typeof COVERAGE_BANDS)[number], string>> = Object.freeze({
  live: "Checked recently",
  ageing: "Due a look",
  stale: "Not checked in a year",
  unstated: "Never checked",
});

/** What each period is called on the page. */
export const PERIOD_WORDS: Readonly<Record<string, string>> = Object.freeze({ day: "Today", month: "This month" });

/** What a period's elapsed fraction is the fraction of. */
const PERIOD_NOUNS: Readonly<Record<string, string>> = Object.freeze({ day: "the day", month: "the month" });

export function departmentPaceApiPath(department: string): string {
  return `${DEPARTMENT_PACE_API_PATH}?${new URLSearchParams({ department }).toString()}`;
}

export function departmentCoverageApiPath(department: string): string {
  return `${DEPARTMENT_COVERAGE_API_PATH}?${new URLSearchParams({ department }).toString()}`;
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function readPaceLine(value: unknown): PaceBody | null {
  if (typeof value !== "object" || value === null) {
    return null;
  }
  const one = value as Record<string, unknown>;
  if (
    !isString(one["period"]) ||
    !isString(one["started_at"]) ||
    !isString(one["ends_at"]) ||
    typeof one["spent_fraction"] !== "number" ||
    typeof one["elapsed_fraction"] !== "number" ||
    typeof one["ahead"] !== "boolean"
  ) {
    return null;
  }
  return value as PaceBody;
}

/** The pace as sent, or null for a body this page cannot read. */
export function readPace(payload: unknown): DepartmentPaceBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as Record<string, unknown>;
  const paces = body["paces"];
  const unrecorded = body["not_recorded"];
  if (
    !isString(body["department"]) ||
    !Array.isArray(paces) ||
    !paces.every((one) => readPaceLine(one) !== null) ||
    !Array.isArray(unrecorded) ||
    !unrecorded.every((one) => typeof one === "object" && one !== null && isString((one as Record<string, unknown>)["why"]))
  ) {
    return null;
  }
  return payload as DepartmentPaceBody;
}

function readArea(value: unknown): CoverageAreaBody | null {
  if (typeof value !== "object" || value === null) {
    return null;
  }
  const one = value as Record<string, unknown>;
  const bands = one["by_freshness"];
  if (
    !isString(one["area"]) ||
    typeof one["items"] !== "number" ||
    typeof bands !== "object" ||
    bands === null ||
    !COVERAGE_BANDS.every((band) => typeof (bands as Record<string, unknown>)[band] === "number")
  ) {
    return null;
  }
  return value as CoverageAreaBody;
}

/** The coverage as sent, or null for a body this page cannot read. */
export function readCoverage(payload: unknown): DepartmentCoverageBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as Record<string, unknown>;
  const areas = body["areas"];
  if (!isString(body["department"]) || !Array.isArray(areas) || !areas.every((one) => readArea(one) !== null) || !isString(body["unread"])) {
    return null;
  }
  return payload as DepartmentCoverageBody;
}

/** A fraction the API sent, as a whole percentage. Rounded for reading, never recomputed. */
export function percentOf(fraction: number): string {
  return `${String(Math.round(fraction * 100))}%`;
}

/** One ceiling's pace in a sentence: how much has gone against how much of its period has. */
export function paceWords(one: PaceBody): string {
  const noun = PERIOD_NOUNS[one.period] ?? "the period";
  return `${percentOf(one.spent_fraction)} of the budget spent, ${percentOf(one.elapsed_fraction)} of ${noun} gone`;
}

/** The label a ceiling is listed under. */
export function periodLabel(period: string): string {
  return PERIOD_WORDS[period] ?? period;
}
