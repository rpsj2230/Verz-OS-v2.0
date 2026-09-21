/**
 * The matrix gate as the Routing screen reads and writes it: the changes it decided, the golden
 * questions it asks, and a rung added at the end of a tier.
 *
 * `brain.routing_routes` serves all of it and `brain.ops.matrix_gate` decides it. A change to the
 * matrix is run against the install's golden questions and the permission canaries through the
 * answer lane before it takes traffic, and a regression holds it with the failing cases shown
 * (M5.6.2). This module holds the addresses, the readers and the words; the page draws them.
 *
 * **A held change is shown with the cases that held it, by id and reason, and never with an
 * answer.** The route stores no answer text and this module has nowhere to put one.
 *
 * **Blank is judged here before a confirmation opens, and only blank.** A question with no text, a
 * golden question asked as nobody, or a rung naming no provider or model is said beside its field
 * in words to act on; whether a principal exists or a provider can be called is the API's to say.
 *
 * Task ids: M5.6.2, M5.7.2
 */

import type { FieldProblem } from "../api/errors";

export const CHANGES_API_PATH = "/routing/changes";
export const GOLDEN_API_PATH = "/routing/golden-questions";
export const ADD_RUNG_API_PATH = "/routing/rungs";

/** Where one golden question is retired. Encoded, because the id travels in the address. */
export function retireGoldenApiPath(questionId: string): string {
  return `${GOLDEN_API_PATH}/${encodeURIComponent(questionId)}/retire`;
}

export interface FailingCase {
  readonly case: string;
  readonly reason: string;
}

export interface ChangeRow {
  readonly id: string;
  readonly kind: "edit" | "add";
  readonly status: "held" | "applied";
  readonly rung_id: string | null;
  readonly failing: readonly FailingCase[];
  readonly reasons: readonly string[];
  readonly quality_share: number | null;
  readonly proposed_by: string;
  readonly decided_at: string;
}

export interface GoldenRow {
  readonly id: string;
  readonly question: string;
  readonly asked_as: string;
  readonly expect: "answer" | "refuse";
  readonly created_by: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** One change as the route answered it, or null when it is not one. */
export function readChange(value: unknown): ChangeRow | null {
  if (!isRecord(value)) {
    return null;
  }
  const { id, kind, status, rung_id, failing, reasons, quality_share, proposed_by, decided_at } = value;
  if (
    typeof id !== "string" ||
    (kind !== "edit" && kind !== "add") ||
    (status !== "held" && status !== "applied") ||
    !Array.isArray(failing) ||
    !Array.isArray(reasons) ||
    typeof proposed_by !== "string" ||
    typeof decided_at !== "string"
  ) {
    return null;
  }
  return {
    id,
    kind,
    status,
    rung_id: typeof rung_id === "string" ? rung_id : null,
    failing: failing.flatMap((one: unknown) =>
      isRecord(one) && typeof one["case"] === "string" && typeof one["reason"] === "string"
        ? [{ case: one["case"], reason: one["reason"] }]
        : [],
    ),
    reasons: reasons.filter((one: unknown): one is string => typeof one === "string"),
    quality_share: typeof quality_share === "number" ? quality_share : null,
    proposed_by,
    decided_at,
  };
}

/** The changes page, newest first, dropping anything that is not a change. */
export function readChanges(payload: unknown): ChangeRow[] {
  if (!isRecord(payload) || !Array.isArray(payload["items"])) {
    return [];
  }
  return payload["items"].flatMap((one: unknown) => {
    const change = readChange(one);
    return change === null ? [] : [change];
  });
}

/** The golden questions page, dropping anything that is not one. */
export function readGolden(payload: unknown): GoldenRow[] {
  if (!isRecord(payload) || !Array.isArray(payload["items"])) {
    return [];
  }
  return payload["items"].flatMap((one: unknown) => {
    if (!isRecord(one)) {
      return [];
    }
    const { id, question, asked_as, expect, created_by } = one;
    if (
      typeof id !== "string" ||
      typeof question !== "string" ||
      typeof asked_as !== "string" ||
      (expect !== "answer" && expect !== "refuse") ||
      typeof created_by !== "string"
    ) {
      return [];
    }
    return [{ id, question, asked_as, expect, created_by }];
  });
}

// ------------------------------------------------------------------------------ the words

export const GATE_HEADING = "Changes and the matrix gate";
export const GATE_LEDE =
  "A change to a rung, or a new rung, is first run against the golden questions below and the " +
  "permission canaries. It takes traffic only if nothing regressed; otherwise it is held here with " +
  "the cases that failed.";
export const NO_CHANGES = "No change to the matrix has been decided yet.";
export const APPLIED = "Applied";
export const HELD = "Held";
export const GOLDEN_HEADING = "Golden questions";
export const GOLDEN_LEDE =
  "Each question is asked as the person named, through the same lane their own questions take, " +
  "with the changed ladder. A question that must be refused is a permission case: one answered is " +
  "enough to hold a change.";
export const NO_GOLDEN =
  "No golden questions are recorded, so every change to the matrix is held until some are.";
export const ADD_GOLDEN = "Add this golden question";
export const RETIRE_GOLDEN = "Retire";
export const KEEP_GOLDEN = "Keep the question";
export const ADD_RUNG_HEADING = "Add a rung";
export const ADD_RUNG = "Add this rung";
export const KEEP_LADDER = "Keep the ladder as it is";

/** What a held change says, in one sentence, before its cases. */
export function heldSentence(change: ChangeRow): string {
  return change.kind === "add"
    ? "The new rung was held and is not on the ladder."
    : "The edit was held and the rung keeps its old numbers.";
}

/** What an expectation is called. */
export function expectWords(expect: GoldenRow["expect"]): string {
  return expect === "answer" ? "Must be answered" : "Must be refused";
}

export function addGoldenQuestion(asked: GoldenAsked): string {
  return `Add a golden question asked as ${asked.asked_as}?`;
}

export function addGoldenConsequence(asked: GoldenAsked): string {
  return (
    `Every later change to the matrix asks it as ${asked.asked_as} and needs it ` +
    `${asked.expect === "answer" ? "answered" : "refused"} before the change takes traffic.`
  );
}

export function retireGoldenQuestion(row: GoldenRow): string {
  return `Retire the golden question asked as ${row.asked_as}?`;
}

export const RETIRE_GOLDEN_CONSEQUENCE =
  "Later changes to the matrix are no longer asked it. Changes already decided keep their record.";

export function addRungQuestion(asked: RungAsked): string {
  return `Add a rung for ${asked.provider} ${asked.model} at the end of the ${asked.tier} tier?`;
}

export function addRungConsequence(asked: RungAsked): string {
  return (
    "It is run against the golden questions and the permission canaries first. If nothing " +
    `regresses it becomes the ${asked.tier} tier's last fallback, with ${String(asked.attempts)} ` +
    `attempt${asked.attempts === 1 ? "" : "s"} and a ${String(asked.timeout_seconds)} second timeout; ` +
    "otherwise it is held below with the cases that failed."
  );
}

// ------------------------------------------------------------------------------ the forms

export interface GoldenAsked {
  readonly question: string;
  readonly asked_as: string;
  readonly expect: "answer" | "refuse";
}

export interface RungAsked {
  readonly tier: "small" | "main" | "heavy";
  readonly provider: string;
  readonly model: string;
  readonly attempts: number;
  readonly timeout_seconds: number;
  readonly max_concurrency: number;
}

export const TIERS: readonly RungAsked["tier"][] = ["small", "main", "heavy"];

/** A golden question with a blank field, as the problems a person is told beside each field. */
export function blankGoldenProblems(question: string, askedAs: string): FieldProblem[] {
  const found: FieldProblem[] = [];
  if (question.trim() === "") {
    found.push({ field: "question", code: "blank", message: "Write the question as a person would ask it." });
  }
  if (askedAs.trim() === "") {
    found.push({
      field: "asked_as",
      code: "blank",
      message: "Name the person it is asked as, by their principal id.",
    });
  }
  return found;
}

/** A rung with a blank provider or model, or a number that is not one, as problems. */
export function blankRungProblems(provider: string, model: string, numbers: readonly [string, string, string]): FieldProblem[] {
  const found: FieldProblem[] = [];
  if (provider.trim() === "") {
    found.push({ field: "provider", code: "blank", message: "Name the provider the rung calls." });
  }
  if (model.trim() === "") {
    found.push({ field: "model", code: "blank", message: "Name the model the rung calls." });
  }
  const [attempts, timeout, concurrency] = numbers;
  if (!(Number(attempts) >= 1)) {
    found.push({ field: "attempts", code: "blank", message: "Give at least one attempt." });
  }
  if (!(Number(timeout) > 0)) {
    found.push({ field: "timeout_seconds", code: "blank", message: "Give a timeout above zero seconds." });
  }
  if (!(Number(concurrency) >= 1)) {
    found.push({ field: "max_concurrency", code: "blank", message: "Allow at least one call at once." });
  }
  return found;
}
