/**
 * An agent's model on its profile: the tier it uses by default, and a provider and model an
 * administrator pinned, tried first with the tier's fallback behind it (M5.7.3).
 *
 * `brain.agent_routes` serves the profile with the pin, and `brain.agent_model_routes` writes it.
 * The pin must name a model a rung on the routing ladder serves; the API says so in its own words
 * when it does not, and this module judges only blankness.
 *
 * Task ids: M5.7.3
 */

import type { FieldProblem } from "../api/errors";

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
export const PIN_MODEL = "Pin this model";
export const CLEAR_PIN = "Go back to the tier alone";
export const KEEP_PIN = "Keep it as it is";

export function tierSentence(choice: ModelChoice): string {
  return choice.tier === null ? "This agent uses its tier's chain." : `This agent uses the ${choice.tier} tier's chain.`;
}

export function pinnedSentence(choice: ModelChoice): string {
  return choice.provider === null || choice.model === null
    ? "No model is pinned."
    : `${choice.provider} ${choice.model} is pinned and tried first, with the tier's chain behind it.`;
}

export function pinQuestion(provider: string | null, model: string | null): string {
  return provider === null || model === null
    ? "Take the pin off and use the tier alone?"
    : `Pin ${provider} ${model} for this agent?`;
}

export function pinConsequence(provider: string | null, model: string | null): string {
  return provider === null || model === null
    ? "Every question to this agent goes to its tier's chain from the next call."
    : "Every question to this agent tries this model first from the next call, and falls back to " +
        "its tier's chain on a timeout, a rate limit or a provider fault.";
}

/** A pin with a blank provider or model, as problems beside each field. */
export function blankPinProblems(provider: string, model: string): FieldProblem[] {
  const found: FieldProblem[] = [];
  if (provider.trim() === "") {
    found.push({ field: "provider", code: "blank", message: "Name the provider to pin." });
  }
  if (model.trim() === "") {
    found.push({ field: "model", code: "blank", message: "Name the model to pin." });
  }
  return found;
}
