/**
 * Whether one agent's learning is paused, and what pausing or resuming it sends: `GET` and `POST
 * /agents/{id}/learning` of `brain.agent_lifecycle_routes` (M16.7.13).
 *
 * **The route opens to a holder of the lifecycle authority over the agent's row and is the one 404
 * for anybody else**, so a reader it refuses is drawn no switch at all, and this file derives no
 * state from that refusal: nothing here turns a 404 into "learning is on".
 *
 * **A pause is the narrow act.** It stops memories forming from the agent's runs from the next turn,
 * and nothing else, so the switch can only narrow what is learned, and the four tiers the Profile
 * lists each go on checking what they apply. The reason is required and travels with the row, in the
 * caller's name.
 *
 * Task ids: M27.11.14
 */

/** Where one agent's learning switch is read and written, under the API base. */
export function agentLearningApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/learning`;
}

export interface AgentLearning {
  readonly agentId: string;
  readonly paused: boolean;
}

/** The switch out of a body, or null when the body is not one. */
export function readLearning(payload: unknown): AgentLearning | null {
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    return null;
  }
  // A cast at the boundary, where proving a structural match buys nothing: both fields are checked
  // below before they are used.
  const fields = payload as Readonly<Record<string, unknown>>;
  const agentId = fields["agent_id"];
  const paused = fields["paused"];
  if (typeof agentId !== "string" || agentId === "" || typeof paused !== "boolean") {
    return null;
  }
  return { agentId, paused };
}

/** The body a pause or a resume sends. */
export function learningBody(paused: boolean, reason: string): { readonly paused: boolean; readonly reason: string } {
  return { paused, reason: reason.trim() };
}
