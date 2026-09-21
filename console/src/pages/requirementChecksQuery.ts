/**
 * What the Requirement checks screen asks `brain.requirement_check_routes` for, and how it reads the
 * answer. No React.
 *
 * The screen is the register's requirements by area, in the owner's words, each with the newest
 * check a person recorded against it on this install. A check is recorded from one form: which
 * requirement, passed or failed, and a sentence saying what was done and seen. Counts are drawn
 * here, which nearly no other screen does: the register is the same for every reader of this
 * screen, so a count hides nothing from anybody.
 *
 * Task ids: M1.8.8, M2.3.2, M5.6.5, M24.3.6
 */

import type { components } from "../api/schema";

export type ChecksBody = components["schemas"]["RequirementChecksView"];
export type AreaRow = components["schemas"]["RequirementAreaView"];
export type RequirementRow = components["schemas"]["RequirementView"];
export type RecordedCheck = components["schemas"]["RequirementCheckView"];

/** Where the API keeps the screen and takes a check. */
export const CHECKS_API_PATH = "/requirements/checks";

/** The console address and the menu's label. */
export const CHECKS_PATH = "/requirement-checks";
export const CHECKS_LABEL = "Requirement checks";

/** The area in the console address, so a colleague can be sent the tab being worked through. */
export const AREA_PARAMETER = "area";

/** The request the screen makes for one area, or the default area when none is chosen. */
export function checksApiPath(area: string | null): string {
  if (area === null || area === "") {
    return CHECKS_API_PATH;
  }
  return `${CHECKS_API_PATH}?${new URLSearchParams({ area }).toString()}`;
}

/** Read `RequirementChecksView`, or null when the body is not one. */
export function readChecks(payload: unknown): ChecksBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { areas?: unknown; requirements?: unknown; told?: unknown };
  if (!Array.isArray(body.areas) || !Array.isArray(body.requirements) || typeof body.told !== "string") {
    return null;
  }
  return payload as ChecksBody;
}

/** One check to record, as the form holds it. */
export interface CheckDraft {
  readonly requirementId: string;
  readonly outcome: string;
  readonly note: string;
}

export const EMPTY_DRAFT: CheckDraft = Object.freeze({ requirementId: "", outcome: "", note: "" });

export const OUTCOMES = ["passed", "failed"] as const;
export const OUTCOME_WORDS: Readonly<Record<string, string>> = Object.freeze({
  passed: "Passed",
  failed: "Failed",
});

/** What each blank field is told. */
export const DRAFT_PROBLEMS = Object.freeze({
  requirementId: "Choose the requirement you checked.",
  outcome: "Say whether it passed or failed.",
  note: "Say in a sentence what you did and what you saw.",
});

/** The longest note the API keeps, from `brain.tables.requirement_check.NOTE_CHARS`. */
export const NOTE_CHARS = 1000;

/** The blank fields of a draft, in form order. */
export function draftProblems(draft: CheckDraft): readonly (keyof typeof DRAFT_PROBLEMS)[] {
  const problems: (keyof typeof DRAFT_PROBLEMS)[] = [];
  if (draft.requirementId === "") {
    problems.push("requirementId");
  }
  if (!(OUTCOMES as readonly string[]).includes(draft.outcome)) {
    problems.push("outcome");
  }
  if (draft.note.trim() === "") {
    problems.push("note");
  }
  return problems;
}

/** The request body, which is `RequirementCheckAsked` exactly. */
export function checkBody(draft: CheckDraft): Record<string, string> {
  return { requirement_id: draft.requirementId, outcome: draft.outcome, note: draft.note.trim() };
}

/** Where an area stands, in one line. */
export function standing(area: AreaRow): string {
  return `${String(area.passed)} passed, ${String(area.failed)} failed, ${String(area.unchecked)} not yet checked, of ${String(area.requirements)}`;
}

/** A recorded check in one line, for the row it belongs to. */
export function checkLine(check: RecordedCheck, when: (value: string) => string): string {
  const release = check.release_commit === null ? "no release recorded" : `release ${check.release_commit.slice(0, 7)}`;
  return `${OUTCOME_WORDS[check.outcome] ?? check.outcome} by ${check.checked_by}, ${when(check.checked_at)}, ${release}`;
}
