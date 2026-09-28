/**
 * The matrix gate as the Routing screen reads and writes it: the changes it decided, the golden
 * questions it asks, and a step added at the end of a level.
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
 * golden question asked as nobody, or a step naming no provider or model is said beside its field
 * in words to act on; whether a person exists or a provider can be called is the API's to say.
 *
 * **A held change says why, and the steps that get a change through** (the owner, 2026-09-28).
 * Every change is held until a golden question is answered through it, and a golden question
 * counts as answered only when the model writes an answer from documents the person it is asked
 * as can read, so a new install with no documents can never change its matrix. That rule is the
 * owner's safety rule and is not weakened here; what was missing was the screen saying it where a
 * change is made. `heldWhy`, `GOLDEN_COUNTS_WHEN` and `STEPS_TO_PASS` are those sentences, and
 * a golden question is asked as a person chosen by name (`ASKERS_API_PATH`), never by an id.
 *
 * **Plain words**: a step and a level (Simple, Medium, Complex), never a rung, a ladder or a tier.
 *
 * Task ids: M5.6.2, M5.7.2, M5.3.3
 */

import type { FieldProblem } from "../api/errors";
import { levelName, providerName } from "./modelsQuery";

export const CHANGES_API_PATH = "/routing/changes";
export const GOLDEN_API_PATH = "/routing/golden-questions";
export const ADD_RUNG_API_PATH = "/routing/rungs";
/** The people a golden question may be asked as, by name: `brain.routing_routes.golden_askers`. */
export const ASKERS_API_PATH = "/routing/golden-questions/askers";

/** The case id every permission check's finding is recorded under: `brain.ops.matrix_gate.CANARY_CASE`. */
export const CANARY_CASE = "canary";

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
  readonly kind: "edit" | "add" | "retire" | "move";
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
  /** The person's name, or null when the directory no longer holds them. */
  readonly asked_as_name: string | null;
  readonly expect: "answer" | "refuse";
  readonly created_by: string;
}

/** One person a golden question may be asked as. */
export interface AskerRow {
  readonly id: string;
  readonly name: string;
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
    (kind !== "edit" && kind !== "add" && kind !== "retire" && kind !== "move") ||
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
    const { id, question, asked_as, asked_as_name, expect, created_by } = one;
    if (
      typeof id !== "string" ||
      typeof question !== "string" ||
      typeof asked_as !== "string" ||
      (expect !== "answer" && expect !== "refuse") ||
      typeof created_by !== "string"
    ) {
      return [];
    }
    return [
      { id, question, asked_as, asked_as_name: typeof asked_as_name === "string" ? asked_as_name : null, expect, created_by },
    ];
  });
}

/** The people page, dropping anything that is not a person. */
export function readAskers(payload: unknown): AskerRow[] {
  if (!isRecord(payload) || !Array.isArray(payload["items"])) {
    return [];
  }
  return payload["items"].flatMap((one: unknown) =>
    isRecord(one) && typeof one["id"] === "string" && typeof one["name"] === "string"
      ? [{ id: one["id"], name: one["name"] }]
      : [],
  );
}

/** Who a golden question is asked as, by name, or by the stored id when no name is known. */
export function askedAsWords(row: GoldenRow): string {
  return row.asked_as_name ?? row.asked_as;
}

// ------------------------------------------------------------------------------ the words

export const GATE_HEADING = "Changes, and the checks they must pass";
export const GATE_LEDE =
  "A change to a step, or a new step, is first tried against the golden questions below and the " +
  "permission checks. It is used only if nothing got worse; otherwise it is held here with what failed.";
export const NO_CHANGES = "No change to the failover matrix has been decided yet.";
export const APPLIED = "Applied";
export const HELD = "Held";
export const GOLDEN_HEADING = "Golden questions";
export const GOLDEN_LEDE =
  "Each question is asked as the person named, the way their own questions are asked, with the change " +
  "in place. A question that must be refused is a permission check: one that gets answered is enough " +
  "to hold a change.";
export const NO_GOLDEN =
  "No golden questions are recorded yet, so every change to the failover matrix is held until one is.";
export const GOLDEN_COUNTS_WHEN =
  "A golden question counts as answered only when the model writes an answer from documents the " +
  "person it is asked as can read. On an install with no documents yet, no change can pass until " +
  "there are some.";
export const HOW_TO_PASS = "To get a change through:";
/** The steps, in order. The first names Knowledge, where a document is added. */
export const STEPS_TO_PASS: readonly string[] = [
  "On Knowledge, add a document that the person you will choose can read.",
  "Below, under Golden questions, add a question that document answers, asked as that person, chosen by name.",
  "Save the change again.",
];
export const ADD_GOLDEN = "Add this golden question";
export const RETIRE_GOLDEN = "Retire";
export const KEEP_GOLDEN = "Keep the question";
export const ADD_RUNG_HEADING = "Add a step";
export const ADD_RUNG = "Add this step";
export const KEEP_LADDER = "Keep the matrix as it is";
export const ASKED_AS_LABEL = "Asked as";
export const CHOOSE_A_PERSON = "Choose a person";
export const NOBODY_LISTED = "No person is in the directory yet, so there is nobody to ask a golden question as.";
export const MORE_PEOPLE = "The list is cut short: there are more people than it shows.";
export const DETAILS = "Details";

/** What a held change says, in one sentence, before why. */
export function heldSentence(change: ChangeRow): string {
  switch (change.kind) {
    case "add":
      return "The new step was held and is not on the failover matrix.";
    case "retire":
      return "The retirement was held and the step stays on the failover matrix.";
    case "move":
      return "The move was held and the step stays where it was.";
    case "edit":
      return "The change was held and the step keeps its old numbers.";
  }
}

/** What a change did, in a few words, for the list of recent changes. */
export function changeWords(kind: ChangeRow["kind"]): string {
  switch (kind) {
    case "add":
      return "A new step";
    case "retire":
      return "A step retired";
    case "move":
      return "A step moved";
    case "edit":
      return "A change to a step";
  }
}

/** Whether a failing case is a permission check's finding rather than a golden question. */
export function isCanary(caseId: string): boolean {
  return caseId === CANARY_CASE || caseId.startsWith(`${CANARY_CASE}-`);
}

/**
 * Why a change was held, in one plain sentence, from its failing cases and whether any golden
 * question is recorded. The steps that get a change through follow it wherever it is drawn.
 */
export function heldWhy(change: ChangeRow, goldenCount: number | null): string {
  if (change.failing.some((one) => isCanary(one.case))) {
    return "It was held because a permission check found a problem. The alert it raised says where.";
  }
  const golden = change.failing.filter((one) => !isCanary(one.case));
  if (golden.some((one) => one.reason.startsWith("answered a question it must refuse"))) {
    return "It was held because a question that must be refused was answered.";
  }
  if (golden.length > 0) {
    return "It was held because a golden question was not answered.";
  }
  if (goldenCount === 0) {
    return "It was held because there are no golden questions yet.";
  }
  return "It was held because the checks could not show that questions are still answered.";
}

/** Whether a held change's explanation should carry the steps to add a document and a question. */
export function needsGoldenSteps(change: ChangeRow): boolean {
  return change.status === "held" && !change.failing.some((one) => isCanary(one.case));
}

/** Why a golden question failed, in plain words. "not entitled" and "nothing retrieved" are one sentence. */
export function caseReasonWords(reason: string): string {
  if (reason.startsWith("answered a question it must refuse")) {
    return "it was answered, and it must be refused";
  }
  if (reason.startsWith("a permission canary")) {
    return "a permission check found a problem; its alert says where";
  }
  const detail = reason.startsWith("did not answer: ") ? reason.slice("did not answer: ".length) : reason;
  switch (detail) {
    case "nothing retrieved":
    case "not entitled":
      // One sentence for both: a record withheld and a record that is not there are never told apart.
      return "no document this person can read answers it";
    case "retrieved but not answering":
      return "the documents found do not answer it";
    case "nothing connected":
      return "no source of documents is connected";
    case "refused":
      return "the model declined to answer it";
    default:
      return detail.startsWith("the lane raised") ? "asking it failed with an error" : "no answer came back";
  }
}

/** A failing case named by its question's text when it is a golden question on the list. */
export function caseWords(caseId: string, golden: readonly GoldenRow[]): string {
  if (isCanary(caseId)) {
    return "A permission check";
  }
  const found = golden.find((one) => one.id === caseId);
  return found === undefined ? "A golden question since retired" : `"${found.question}"`;
}

/** What an expectation is called. */
export function expectWords(expect: GoldenRow["expect"]): string {
  return expect === "answer" ? "Must be answered" : "Must be refused";
}

export function addGoldenQuestion(name: string): string {
  return `Add a golden question asked as ${name}?`;
}

export function addGoldenConsequence(asked: GoldenAsked, name: string): string {
  return (
    `Every later change to the failover matrix asks it as ${name} and needs it ` +
    `${asked.expect === "answer" ? "answered" : "refused"} before the change is used.`
  );
}

export function retireGoldenQuestion(row: GoldenRow): string {
  return `Retire the golden question asked as ${askedAsWords(row)}?`;
}

export const RETIRE_GOLDEN_CONSEQUENCE =
  "Later changes to the failover matrix are no longer asked it. Changes already decided keep their record.";

export function addRungQuestion(asked: RungAsked): string {
  return `Add a step for ${providerName(asked.provider)} ${asked.model} at the end of the ${levelName(asked.tier)} level?`;
}

export function addRungConsequence(asked: RungAsked): string {
  return (
    "It is tried against the golden questions and the permission checks first. If nothing gets " +
    `worse it becomes the ${levelName(asked.tier)} level's last step, with ${String(asked.attempts)} ` +
    `attempt${asked.attempts === 1 ? "" : "s"} and a ${String(asked.timeout_seconds)} second timeout; ` +
    "otherwise it is held below with what failed."
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
    found.push({ field: "asked_as", code: "blank", message: "Choose the person it is asked as." });
  }
  return found;
}

/** A step with a blank provider or model, or a number that is not one, as problems. */
export function blankRungProblems(provider: string, model: string, numbers: readonly [string, string, string]): FieldProblem[] {
  const found: FieldProblem[] = [];
  if (provider.trim() === "") {
    found.push({ field: "provider", code: "blank", message: "Name the provider the step calls." });
  }
  if (model.trim() === "") {
    found.push({ field: "model", code: "blank", message: "Name the model the step calls." });
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
