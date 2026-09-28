/**
 * An agent's model on its profile: the level it uses by default, and a provider and model an
 * administrator pinned, tried first with the level's steps behind it (M5.7.3).
 *
 * `brain.agent_routes` serves the profile with the pin, and `brain.agent_model_routes` writes it.
 *
 * **The order is drawn, not described.** Until 2026-09-28 the profile said "the main tier's chain"
 * and offered two free-text boxes, so an administrator had to know a provider's slug and a model's
 * exact name, and could not see that a pin goes first with the level behind it. Now the profile
 * draws the order a question to this agent tries, the pin as step 1 and the level's steps after
 * it, in the failover matrix's own words, and the pin is chosen from the models the matrix serves.
 *
 * **The order is the executor's, read off the matrix.** `brain.models.calls` walks the rung
 * serving the pinned pair first, passes over a pin no step in use serves, and leaves the pinned
 * rung out of the level's chain afterwards so it is never tried twice. `agentSteps` draws exactly
 * that from `GET /routing/rungs`, and a step taken out of use on the routing screen is not drawn,
 * because nothing tries it. See `A_PIN_NO_STEP_SERVES_IS_PASSED_OVER`.
 *
 * **A pin is chosen among the models the matrix serves**, which is the API's own rule
 * (`brain.agent_model_routes.A_PIN_CHOOSES_AMONG_THE_LADDERS_MODELS`). The choices are every pair
 * a step in use names, in any level, so the select cannot offer one the API would refuse.
 *
 * Task ids: M5.7.3
 */

import type { FieldProblem } from "../api/errors";
import type { RungRow } from "./matrixQuery";
import { levelName, providerName } from "./modelsQuery";

/** Written down because a pin that looks stored and is never tried is the failure to avoid. */
export const A_PIN_NO_STEP_SERVES_IS_PASSED_OVER =
  "The executor tries a pinned model through the step that serves it, and passes over a pin no " +
  "step in use serves. The profile draws such a pin with that said beside it, so a pin taken out " +
  "of use on the routing screen is not drawn as the model every question tries first.";

/** Where one agent's pin is written. Encoded, because the id travels in the address. */
export function modelPinApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/model-pin`;
}

export interface ModelChoice {
  readonly tier: string | null;
  readonly provider: string | null;
  readonly model: string | null;
}

/** The profile's tier and pin, or null for a reader the workspace gave no profile. */
export function readModelChoice(payload: unknown): ModelChoice | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const profile = (payload as { profile?: unknown }).profile;
  if (typeof profile !== "object" || profile === null) {
    return null;
  }
  const fields = profile as Record<string, unknown>;
  return {
    tier: typeof fields["tier"] === "string" ? fields["tier"] : null,
    provider: typeof fields["model_pin_provider"] === "string" ? fields["model_pin_provider"] : null,
    model: typeof fields["model_pin_model"] === "string" ? fields["model_pin_model"] : null,
  };
}

export const MODEL_HEADING = "Model";
export const STEPS_CAPTION = "The order a question to this agent tries models";
export const PIN_MODEL = "Pin this model";
export const CLEAR_PIN = "Go back to the level alone";
export const KEEP_PIN = "Keep it as it is";
export const CHOOSE_A_MODEL = "Choose a model";
export const PIN_LABEL = "Model to try first";
export const NOTHING_TO_PIN = "No step on the failover matrix is in use, so there is no model to pin.";
export const PINNED_ROLE = "pinned for this agent";
export const PASSED_OVER = "passed over: no step in use serves it";

/** The level this agent answers at, in the failover matrix's words. */
export function levelSentence(choice: ModelChoice): string {
  return choice.tier === null
    ? "This agent answers at its level on the failover matrix."
    : `This agent answers at the ${levelName(choice.tier)} level on the failover matrix.`;
}

/** Whether a pin is set, and what that does to the order. */
export function pinnedSentence(choice: ModelChoice): string {
  const level = choice.tier === null ? "its level's" : `the ${levelName(choice.tier)} level's`;
  return choice.provider === null || choice.model === null
    ? `No model is pinned, so ${level} steps answer in order.`
    : `${providerName(choice.provider)} ${choice.model} is pinned: it is tried first, and ${level} ` +
        "steps follow if it fails.";
}

/** One row of the order this agent tries. */
export interface AgentStep {
  readonly key: string;
  readonly step: number;
  readonly provider: string;
  readonly model: string;
  readonly role: string;
  /** Said beside the pin when nothing would try it. */
  readonly note: string | null;
}

/**
 * The order a question to this agent tries: the pin first, then the level's steps in use by
 * position, leaving out the pinned pair so it is not drawn twice. See the module docstring.
 */
export function agentSteps(choice: ModelChoice, rungs: readonly RungRow[]): AgentStep[] {
  const inUse = rungs.filter((one) => one.enabled);
  const pinned = choice.provider !== null && choice.model !== null;
  const found: AgentStep[] = [];
  if (pinned) {
    const served = inUse.some((one) => one.provider === choice.provider && one.model === choice.model);
    found.push({
      key: "pin",
      step: 1,
      provider: providerName(choice.provider ?? ""),
      model: choice.model ?? "",
      role: PINNED_ROLE,
      note: served ? null : PASSED_OVER,
    });
  }
  const level = inUse
    .filter((one) => one.tier === choice.tier)
    .filter((one) => !(pinned && one.provider === choice.provider && one.model === choice.model))
    .slice()
    .sort((a, b) => a.position - b.position);
  level.forEach((one, index) => {
    found.push({
      key: one.id,
      step: found.length + 1,
      provider: providerName(one.provider),
      model: one.model,
      role: `${levelName(one.tier)} level, step ${String(index + 1)}`,
      note: null,
    });
  });
  return found;
}

/** A model the select offers: a provider and model a step in use serves. */
export interface PinChoice {
  readonly provider: string;
  readonly model: string;
  readonly label: string;
}

/** Every pair a step in use serves, once each, in level order and then by position. */
export function pinChoices(rungs: readonly RungRow[], levels: readonly string[]): PinChoice[] {
  const order = (tier: string) => {
    const at = levels.indexOf(tier);
    return at === -1 ? levels.length : at;
  };
  const seen = new Set<string>();
  const found: PinChoice[] = [];
  for (const one of rungs
    .filter((row) => row.enabled)
    .slice()
    .sort((a, b) => order(a.tier) - order(b.tier) || a.position - b.position)) {
    const key = JSON.stringify([one.provider, one.model]);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    found.push({ provider: one.provider, model: one.model, label: `${providerName(one.provider)}: ${one.model}` });
  }
  return found;
}

export function pinQuestion(provider: string | null, model: string | null): string {
  return provider === null || model === null
    ? "Take the pin off and use the level alone?"
    : `Pin ${providerName(provider)} ${model} for this agent?`;
}

export function pinConsequence(provider: string | null, model: string | null): string {
  return provider === null || model === null
    ? "Every question to this agent goes to its level's steps from the next call."
    : "Every question to this agent tries this model first from the next call, and falls back to " +
        "its level's steps on a timeout, a rate limit or a provider fault.";
}

/** A pin with no model chosen, as the problem beside the select. */
export function blankPinProblems(chosen: string): FieldProblem[] {
  return chosen === "" ? [{ field: "model_pin", code: "blank", message: "Choose the model to pin." }] : [];
}
