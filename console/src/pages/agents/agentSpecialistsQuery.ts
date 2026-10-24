/**
 * A coordinating agent's specialists and the runs that split a request between them, as the console
 * asks for and says them (M18.5.1, M18.6.2). No React.
 *
 * What a link is and is not is said by the route (`words`), once; the console repeats none of it.
 * A run's figures are estimates until a run is joined to its recorded spend, which the route also
 * says (`cost_note`) and the page draws beside the cost.
 *
 * Task ids: M18.5.1, M18.6.2
 */

import type { components } from "../../api/schema";

export type Coordination = components["schemas"]["CoordinationView"];
export type CoordinationRun = components["schemas"]["CoordinationRunView"];
export type KeptCoordinatedRuns = components["schemas"]["CoordinationKeptRunsPage"];

/** Where the runs kept are asked for, and where a request is split, under the API base. */
export const COORDINATED_RUNS_API_PATH = "/orchestration/coordinated-runs";

export function agentCoordinationApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/coordination`;
}

export function agentCalleesApiPath(agentId: string): string {
  return `${agentCoordinationApiPath(agentId)}/callees`;
}

export function agentCalleeRemovalsApiPath(agentId: string): string {
  return `${agentCalleesApiPath(agentId)}/removals`;
}

export function agentFanOutApiPath(agentId: string): string {
  return `${agentCoordinationApiPath(agentId)}/fan-out`;
}

function isObject(payload: unknown): payload is Record<string, unknown> {
  return typeof payload === "object" && payload !== null && !Array.isArray(payload);
}

/** What a coordinator may call, or null when the body is not that. */
export function readCoordination(payload: unknown): Coordination | null {
  if (!isObject(payload) || typeof payload["agent_id"] !== "string" || !Array.isArray(payload["callees"])) {
    return null;
  }
  const callees = (payload["callees"] as unknown[]).flatMap((one) =>
    isObject(one) && typeof one["agent_id"] === "string" && typeof one["display_name"] === "string"
      ? [{ agent_id: one["agent_id"], display_name: one["display_name"] }]
      : [],
  );
  return {
    agent_id: payload["agent_id"],
    names_shown: payload["names_shown"] === true,
    callees,
    fan_out_enabled: payload["fan_out_enabled"] === true,
    may_change: payload["may_change"] === true,
    switched_on: payload["switched_on"] === true,
    words: typeof payload["words"] === "string" ? payload["words"] : "",
  };
}

/** One coordinated run, or null when the body is not one. */
export function readCoordinatedRun(payload: unknown): CoordinationRun | null {
  if (
    !isObject(payload) ||
    typeof payload["run_id"] !== "string" ||
    typeof payload["mode"] !== "string" ||
    !Array.isArray(payload["children"]) ||
    !isObject(payload["merged"])
  ) {
    return null;
  }
  const merged = payload["merged"];
  const children = (payload["children"] as unknown[]).flatMap((one) =>
    isObject(one) && typeof one["subtask_id"] === "string" && typeof one["callee_id"] === "string"
      ? [
          {
            subtask_id: one["subtask_id"],
            callee_id: one["callee_id"],
            depth: typeof one["depth"] === "number" ? one["depth"] : 0,
            status: typeof one["status"] === "string" ? one["status"] : "",
            seconds: typeof one["seconds"] === "number" ? one["seconds"] : 0,
          },
        ]
      : [],
  );
  const reports = Array.isArray(merged["reports"])
    ? (merged["reports"] as unknown[]).flatMap((one) =>
        isObject(one) && typeof one["subtask_id"] === "string"
          ? [
              {
                subtask_id: one["subtask_id"],
                minor: typeof one["minor"] === "number" ? one["minor"] : 0,
                seconds: typeof one["seconds"] === "number" ? one["seconds"] : 0,
              },
            ]
          : [],
      )
    : [];
  return {
    run_id: payload["run_id"],
    mode: payload["mode"],
    why: Array.isArray(payload["why"]) ? (payload["why"] as unknown[]).filter((one): one is string => typeof one === "string") : [],
    gate: null,
    children,
    merged: {
      values: isObject(merged["values"]) ? (merged["values"] as Record<string, Record<string, unknown>>) : {},
      reports,
      total_minor: typeof merged["total_minor"] === "number" ? merged["total_minor"] : 0,
      currency: typeof merged["currency"] === "string" ? merged["currency"] : "",
      complete: merged["complete"] === true,
      notice: typeof merged["notice"] === "string" ? merged["notice"] : "",
    },
    cost_note: typeof payload["cost_note"] === "string" ? payload["cost_note"] : "",
  };
}

/** The runs kept, or null when the body is not that. */
export function readKeptCoordinatedRuns(payload: unknown): KeptCoordinatedRuns | null {
  if (!isObject(payload) || !Array.isArray(payload["runs"])) {
    return null;
  }
  const runs = (payload["runs"] as unknown[]).flatMap((one) => {
    if (!isObject(one) || typeof one["run_id"] !== "string" || typeof one["coordinator_id"] !== "string") {
      return [];
    }
    const children = Array.isArray(one["children"])
      ? (one["children"] as unknown[]).flatMap((child) =>
          isObject(child) && typeof child["subtask_id"] === "string" && typeof child["callee_id"] === "string"
            ? [
                {
                  subtask_id: child["subtask_id"],
                  callee_id: child["callee_id"],
                  depth: typeof child["depth"] === "number" ? child["depth"] : 0,
                  reach_hash: typeof child["reach_hash"] === "string" ? child["reach_hash"] : "",
                  status: typeof child["status"] === "string" ? child["status"] : "",
                  cost_minor: typeof child["cost_minor"] === "number" ? child["cost_minor"] : 0,
                  seconds: typeof child["seconds"] === "number" ? child["seconds"] : 0,
                },
              ]
            : [],
        )
      : [];
    return [
      {
        run_id: one["run_id"],
        coordinator_id: one["coordinator_id"],
        started_at: typeof one["started_at"] === "string" ? one["started_at"] : "",
        asked_by: typeof one["asked_by"] === "string" ? one["asked_by"] : "",
        mode: typeof one["mode"] === "string" ? one["mode"] : "",
        why: Array.isArray(one["why"]) ? (one["why"] as unknown[]).filter((w): w is string => typeof w === "string") : [],
        children,
        complete: one["complete"] === true,
        total_minor: typeof one["total_minor"] === "number" ? one["total_minor"] : 0,
        currency: typeof one["currency"] === "string" ? one["currency"] : "",
      },
    ];
  });
  return { runs, switched_on: payload["switched_on"] === true };
}

/** How the specialists were run, in words. */
export function modeWords(mode: string): string {
  return mode === "parallel" ? "Run together" : "Run one after another";
}

/** Why the specialists were run one after another, in words. */
export function whyWords(why: string): string {
  switch (why) {
    case "fan_out_not_enabled":
      return "running specialists together is not allowed for this coordinating agent";
    case "gate_declined":
      return "the gate found it would not pay to split the request";
    case "wave_over_the_cap":
      return "more specialists were due at once than one run may have in flight";
    case "no_room":
      return "the install had no room to run them together just now";
    default:
      return why.replaceAll("_", " ");
  }
}

/** What became of one specialist's subtask, in words. */
export function childWords(status: string): string {
  switch (status) {
    case "delivered":
      return "Delivered what it promised";
    case "refused":
      return "Turned away";
    case "timed_out":
      return "Ran out of time";
    case "invalid_result":
      return "Returned something other than what it promised";
    case "not_admitted":
      return "Not started: there was no room";
    case "unreachable":
      return "Could not be reached";
    default:
      return status.replaceAll("_", " ");
  }
}

/** The body of a request to split. */
export function askBody(coordinatorId: string, ask: string): { coordinator_id: string; ask: string } {
  return { coordinator_id: coordinatorId, ask: ask.trim() };
}
