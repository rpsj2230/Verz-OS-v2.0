/**
 * What the coverage statement, the first-connector suggestion and the starter questions built from
 * data ask the API for, and how their answers are read. No React.
 *
 * `brain.adoption_coverage_routes` and `brain.console.adoption_coverage` decide what a reader is
 * told, and this module decides only what the page may do with the answer.
 *
 * **Nothing is totalled, counted or compared here.** A line is a department's own statement about
 * one source, and the answer holds no figure that adds lines together, so a total drawn on this
 * page would be the one number the API does not stand behind. A department with nothing connected
 * is a line, and is drawn as one: see `A_NOT_CONNECTED_DEPARTMENT_IS_A_LINE_AND_NOT_A_GAP`.
 *
 * **A field the API did not send is absent, never defaulted.** A count that did not arrive is
 * drawn as a sentence about it, not as nought, because nought says the system looked and found
 * nothing (`brain.adoption.A_ZERO_AND_A_NOT_CONNECTED_SOURCE_ARE_DIFFERENT_FACTS`).
 *
 * Task ids: M34.1.1.1, M34.1.1.2, M34.1.1.3, M34.1.2.1, M34.1.2.2, M34.1.2.3
 */

import type { components } from "../api/schema";

/** One department's statement about one source, as the API sends it. */
export type CoverageLine = components["schemas"]["CoverageLineView"];

/** One thing a champion could do next. */
export type CoverageAction = components["schemas"]["ActionView"];

/** The whole statement for one reader. */
export type CoverageBody = components["schemas"]["CoverageView"];

/** Where the statement is read. */
export const COVERAGE_API_PATH = "/report/coverage";

/** Where the source to connect first is read. */
export const START_API_PATH = "/console/connector-start";

/** Where the questions built from the person's own department's data are read. */
export const FROM_DATA_API_PATH = "/welcome/from-your-data";

/** Written down because tidying the table is what a person does to a not-connected row. */
export const A_NOT_CONNECTED_DEPARTMENT_IS_A_LINE_AND_NOT_A_GAP =
  "brain.console.adoption_coverage gives every department the reader's usage grant admits a " +
  "line, a department with nothing connected included, so that whether a line appears is a " +
  "fact about the reader's reach. A page that hid the not-connected lines would show only the " +
  "departments something was connected for, and a champion would learn which of their " +
  "departments has nothing from a screen that was careful not to say.";

/** What a department with no records yet reads, where a nought would say it was looked at. */
export const NOT_READ_YET = "Not read to the end yet";

/** What the not-connected line says when nothing on this install could be suggested for it. */
export const NOTHING_TO_SUGGEST = "Nothing on this install can be suggested for it yet";

function isRecord(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function text(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

/** A line the page can draw, with the optional fields kept optional. */
export interface CoverageRow {
  readonly department: string;
  readonly source: string | undefined;
  readonly sourceLabel: string | undefined;
  readonly state: string;
  readonly stateWords: string;
  readonly records: number | undefined;
  readonly lastSync: string | undefined;
}

/** A shopping-list action the page can draw. */
export interface ActionRow {
  readonly department: string;
  readonly source: string;
  readonly sourceLabel: string;
  readonly words: string;
}

/** What the statement says, read defensively. `null` when the body is not the route's shape. */
export interface Coverage {
  readonly switchedOn: boolean;
  readonly rows: readonly CoverageRow[];
  readonly actions: readonly ActionRow[];
  readonly note: string;
}

export function readCoverage(payload: unknown): Coverage | null {
  if (!isRecord(payload) || typeof payload["switched_on"] !== "boolean") {
    return null;
  }
  const lines = Array.isArray(payload["lines"]) ? (payload["lines"] as readonly unknown[]) : [];
  const shopping = Array.isArray(payload["shopping"]) ? (payload["shopping"] as readonly unknown[]) : [];
  const rows: CoverageRow[] = [];
  for (const one of lines) {
    if (!isRecord(one)) {
      continue;
    }
    const department = text(one["department"]);
    const state = text(one["state"]);
    const stateWords = text(one["state_words"]);
    if (department === undefined || state === undefined || stateWords === undefined) {
      continue;
    }
    rows.push({
      department,
      source: text(one["source"]),
      sourceLabel: text(one["source_label"]),
      state,
      stateWords,
      records: typeof one["records"] === "number" ? one["records"] : undefined,
      lastSync: text(one["last_sync"]),
    });
  }
  const actions: ActionRow[] = [];
  for (const one of shopping) {
    if (!isRecord(one)) {
      continue;
    }
    const department = text(one["department"]);
    const source = text(one["source"]);
    const words = text(one["words"]);
    if (department === undefined || source === undefined || words === undefined) {
      continue;
    }
    actions.push({ department, source, sourceLabel: text(one["source_label"]) ?? source, words });
  }
  return {
    switchedOn: payload["switched_on"],
    rows,
    actions,
    note: text(payload["note"]) ?? "",
  };
}

/** The source to connect first: its label, or `undefined` when none is suggested. */
export function readStart(payload: unknown): { readonly source: string; readonly label: string } | undefined {
  if (!isRecord(payload)) {
    return undefined;
  }
  const source = text(payload["source"]);
  return source === undefined ? undefined : { source, label: text(payload["label"]) ?? source };
}

/** One question built from data, with the system to check its answer in. */
export interface FromData {
  readonly question: string;
  readonly checkIn: string;
}

export function readFromData(payload: unknown): readonly FromData[] {
  if (!isRecord(payload) || !Array.isArray(payload["questions"])) {
    return [];
  }
  const found: FromData[] = [];
  for (const one of payload["questions"] as readonly unknown[]) {
    if (!isRecord(one)) {
      continue;
    }
    const question = text(one["question"]);
    const checkIn = text(one["check_in"]);
    if (question !== undefined && checkIn !== undefined) {
      found.push({ question, checkIn });
    }
  }
  return found;
}
