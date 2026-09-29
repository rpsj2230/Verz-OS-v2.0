/**
 * What the Requirement checks screen asks `brain.requirement_check_routes` for, and how it reads the
 * answer. No React.
 *
 * The screen is the register's requirements by area, in the owner's words, each with its proof
 * leaves, what the install's acceptance checks said about those leaves, and the newest check a person
 * recorded against it on this install. A check is recorded from one form: which requirement, passed
 * or failed, and a sentence saying what was done and seen. Counts are drawn here, which nearly no
 * other screen does: the register is the same for every reader of this screen, so a count hides
 * nothing from anybody.
 *
 * **Narrowing an area's rows here is honest, which it is not on a paged list.** The route answers an
 * area whole, and every reader of the screen is shown the same register, so a search or a status
 * chosen here narrows the complete answer rather than the part of it that arrived.
 *
 * Task ids: M1.8.8, M2.3.2, M5.6.5, M24.3.6
 */

import type { components } from "../api/schema";

export type ChecksBody = components["schemas"]["RequirementChecksView"];
export type AreaRow = components["schemas"]["RequirementAreaView"];
export type RequirementRow = components["schemas"]["RequirementView"];
export type RecordedCheck = components["schemas"]["RequirementCheckView"];
export type Evidence = components["schemas"]["AcceptanceEvidenceView"];

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

/** Where one requirement stands on this install, from its newest recorded check. */
export type Standing = "unchecked" | "passed" | "failed";

export const STANDINGS: readonly Standing[] = ["unchecked", "passed", "failed"];

export const STANDING_WORDS: Readonly<Record<Standing, string>> = Object.freeze({
  unchecked: "To check",
  passed: "Passed",
  failed: "Failed",
});

export function standingOf(row: RequirementRow): Standing {
  const outcome = row.latest?.outcome;
  return outcome === "passed" || outcome === "failed" ? outcome : "unchecked";
}

/** An acceptance check's outcome as a person reads it. */
export const EVIDENCE_WORDS: Readonly<Record<string, string>> = Object.freeze({
  passed: "Passed",
  failed: "Failed",
  "not run": "Not run",
});

/** The proof leaves the register names for a row, or none from an older API. */
export function proofOf(row: RequirementRow): readonly string[] {
  return Array.isArray(row.proof) ? row.proof : [];
}

/** The acceptance checks proving a row's leaves, or none from an older API. */
export function evidenceOf(row: RequirementRow): readonly Evidence[] {
  return Array.isArray(row.evidence) ? row.evidence : [];
}

/** A row's evidence in a few words: how many checks passed, failed and have not run. */
export function evidenceWords(row: RequirementRow): string {
  const found = evidenceOf(row);
  if (found.length === 0) {
    return "No automatic check";
  }
  const counted = (["passed", "failed", "not run"] as const)
    .map((outcome) => [outcome, found.filter((one) => one.outcome === outcome).length] as const)
    .filter(([, count]) => count > 0)
    .map(([outcome, count]) => `${String(count)} ${(EVIDENCE_WORDS[outcome] ?? outcome).toLowerCase()}`);
  return counted.join(", ");
}

/** How many of an area's requirements have a recorded check. */
export function recordedIn(area: AreaRow): number {
  return area.passed + area.failed;
}

/** Whether a row says every word typed, in its id, its words or its proof leaves. */
export function rowSays(row: RequirementRow, typed: string): boolean {
  const words = typed.toLocaleLowerCase("en-GB").split(/\s+/u).filter((one) => one !== "");
  const said = [row.id, row.requirement, ...proofOf(row)].join(" ").toLocaleLowerCase("en-GB");
  return words.every((one) => said.includes(one));
}

/** A recorded check in one line, for the row it belongs to. */
export function checkLine(check: RecordedCheck, when: (value: string) => string): string {
  const release = check.release_commit === null ? "no release recorded" : `release ${check.release_commit.slice(0, 7)}`;
  return `${OUTCOME_WORDS[check.outcome] ?? check.outcome} by ${check.checked_by}, ${when(check.checked_at)}, ${release}`;
}
