/**
 * The budgets and request windows a person may set on the Rate limits screen, read and set
 * (M22.4.1, M22.1.2).
 *
 * `brain.tuning_routes` serves `GET /install/tuning` and writes `PUT /install/tuning/{name}`, and
 * `brain.ops.tuning` decides every knob's bounds and what is in force. The page draws a control only
 * where the answer's `may_change` says the write would admit this reader; the API refuses without
 * the authority whatever the page drew.
 *
 * **A figure is typed as digits and sent as a whole number.** Blank, a fraction or anything that is
 * not digits is judged here before anything is sent, with the knob's own bounds in the sentence; a
 * figure the API still refuses comes back in its own words.
 *
 * Task ids: M22.4.1, M22.1.2
 */

export const TUNING_API_PATH = "/install/tuning";

/** Where one knob is set. */
export function tunePath(name: string): string {
  return `${TUNING_API_PATH}/${encodeURIComponent(name)}`;
}

export const TUNING_HEADING = "Limits you can change";
export const TUNING_LEDE =
  "Each figure is between bounds the product fixes. A change is recorded in the audit trail under your name.";
export const CHANGE_LIMIT = "Change";
export const SAVE_LIMIT = "Save the new figure";
export const KEEP_LIMIT = "Keep the current figure";
export const NOT_READ = "The limits you can change could not be read.";
export const READING_TUNING = "Loading the limits you can change.";

export interface Knob {
  readonly name: string;
  readonly kind: string;
  readonly label: string;
  readonly unit: string;
  readonly value: number;
  readonly default: number;
  readonly lowest: number;
  readonly highest: number;
  readonly saved: boolean;
  readonly bounds_because: string;
}

export interface TuningBody {
  readonly knobs: readonly Knob[];
  readonly may_change: boolean;
  readonly in_force: string;
}

function whole(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) ? value : null;
}

/** The API's answer, or null for one this page cannot read. */
export function readTuning(payload: unknown): TuningBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { knobs?: unknown; may_change?: unknown; in_force?: unknown };
  if (!Array.isArray(body.knobs) || typeof body.may_change !== "boolean" || typeof body.in_force !== "string") {
    return null;
  }
  const knobs: Knob[] = [];
  for (const one of body.knobs as unknown[]) {
    if (typeof one !== "object" || one === null) {
      return null;
    }
    const row = one as Record<string, unknown>;
    const figures = [row["value"], row["default"], row["lowest"], row["highest"]].map(whole);
    const [value, fallback, lowest, highest] = figures;
    if (
      typeof row["name"] !== "string" ||
      typeof row["label"] !== "string" ||
      value === null ||
      value === undefined ||
      fallback === null ||
      fallback === undefined ||
      lowest === null ||
      lowest === undefined ||
      highest === null ||
      highest === undefined
    ) {
      return null;
    }
    knobs.push({
      name: row["name"],
      kind: typeof row["kind"] === "string" ? row["kind"] : "",
      label: row["label"],
      unit: typeof row["unit"] === "string" ? row["unit"] : "",
      value,
      default: fallback,
      lowest,
      highest,
      saved: row["saved"] === true,
      bounds_because: typeof row["bounds_because"] === "string" ? row["bounds_because"] : "",
    });
  }
  return { knobs, may_change: body.may_change, in_force: body.in_force };
}

/** A figure in the console's number style, with the knob's unit. */
export function figureWords(amount: number, unit: string): string {
  return `${amount.toLocaleString("en-GB")} ${unit}`.trim();
}

export function boundsWords(knob: Knob): string {
  return `${knob.lowest.toLocaleString("en-GB")} to ${knob.highest.toLocaleString("en-GB")}`;
}

export function sourceWords(knob: Knob): string {
  return knob.saved ? "Set here" : "The product's figure";
}

/** Why a typed figure cannot be sent, or null when it can. The API judges again whatever this says. */
export function figureProblem(knob: Knob, typed: string): string | null {
  const text = typed.trim();
  if (text === "") {
    return `Type a figure for ${knob.label.toLowerCase()}.`;
  }
  if (!/^[0-9]+$/.test(text)) {
    return `${knob.label} is a whole number.`;
  }
  const amount = Number(text);
  if (amount < knob.lowest || amount > knob.highest) {
    return `${knob.label} is between ${boundsWords(knob)}.`;
  }
  return null;
}

/** What the confirmation says the change does, before it is sent. */
export function changeConsequence(knob: Knob, amount: number, inForce: string): string {
  return `${knob.label} becomes ${figureWords(amount, knob.unit)} (it is ${figureWords(knob.value, knob.unit)} now). ${inForce}`;
}

export function changedSentence(knob: Knob, amount: number): string {
  return `${knob.label} is now ${figureWords(amount, knob.unit)}.`;
}
