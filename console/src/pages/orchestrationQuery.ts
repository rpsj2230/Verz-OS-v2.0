/**
 * What the plan-weighing panel on the Features page asks for and says. No React.
 *
 * `brain.orchestration_routes` weighs a multi-agent plan an administrator wrote down: it estimates
 * what each subtask would cost, evaluates the six conditions that decide whether the plan is
 * split across agents, keeps the decision, and merges what each subtask returned with a stated gap
 * where one failed. **It starts no agent**, and the panel says so only while the API does
 * (`nothing_is_started`). The API asks for `admin:agent_lifecycle` over everything whatever the page
 * drew.
 *
 * Task ids: M18.2.1, M18.2.2, M18.2.3, M18.2.4, M18.1.3, M18.4.1, M18.4.2, M18.4.3
 */

import type { components } from "../api/schema";

export type DecisionsBody = components["schemas"]["DecisionsPage"];
export type GateRow = components["schemas"]["GateView"];
export type RehearsalBody = components["schemas"]["PlanWeighedView"];

/** Where the API keeps this panel. */
export const REHEARSALS_API_PATH = "/orchestration/weighed-plans";

export const ORCHESTRATION_TITLE = "Multi-agent plans";
export const READING_DECISIONS = "Reading the plans weighed so far.";
export const NO_DECISIONS = "No plan has been weighed on this install.";
export const NO_DECISIONS_TITLE = "No plans weighed";
export const UNREADABLE_DECISIONS =
  "The API answered in a shape this console does not read, so no decision is listed. The console and the API are probably from different releases.";
export const NOTHING_STARTS = "Weighing a plan starts no agent: it says what would be decided and keeps the decision.";
export const SWITCHED_OFF =
  "Weighing plans is switched off. Switch on Weigh a multi-agent plan before it runs in the list above to weigh one. Decisions already kept can still be read.";
export const PLAN_LABEL = "Plan (JSON)";
export const WEIGH = "Weigh plan";
export const NOT_JSON = "That is not JSON, so nothing was sent.";
export const NOT_WEIGHED = "The plan was not weighed";

/** The words for the two verdicts. Single loop is the default and is not a refusal. */
export function verdictWords(verdict: string): string {
  return verdict === "parallel" ? "Split across agents" : "Kept as one loop";
}

/** What the gate found, in one sentence a person can act on. */
export function summary(row: GateRow): string {
  const failed = row.failed.length === 0 ? "none failed" : `failed: ${row.failed.join(", ").replaceAll("_", " ")}`;
  return `${row.branches} could start at once, ${row.speedup.toFixed(1)} times faster, cost ${row.cost_multiplier.toFixed(2)} times; ${failed}.`;
}

/** Read `brain.orchestration_routes.DecisionsPage`, or null for a shape this console does not read. */
export function readDecisions(payload: unknown): DecisionsBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { decisions?: unknown };
  return Array.isArray(body.decisions) ? (payload as DecisionsBody) : null;
}

/** Read one rehearsal's answer, or null. */
export function readRehearsal(payload: unknown): RehearsalBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { run_id?: unknown; gate?: unknown };
  return typeof body.run_id === "string" && typeof body.gate === "object" && body.gate !== null
    ? (payload as RehearsalBody)
    : null;
}

/** The plan a person pasted, or null when it is not a JSON object. */
export function readPlan(text: string): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(text);
    return typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}
