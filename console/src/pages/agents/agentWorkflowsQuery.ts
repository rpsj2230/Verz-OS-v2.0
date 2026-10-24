/**
 * Stored workflows as the console asks for and says them: the ones written, the ones an agent may
 * run, a run's steps and the runs kept (M17.6.5). No React.
 *
 * Every word on a step is a word from a closed list the server keeps (`Status` and `Cause` in
 * `brain.orchestration.workflow_run`), so a step is told by a status and a cause and never by a
 * value or a message: a trace has none to give. An unfamiliar word is drawn as it came, which says
 * the server is newer than this console and hides nothing.
 *
 * Task ids: M17.6.5
 */

import type { components } from "../../api/schema";

export type AssignedWorkflows = components["schemas"]["WorkflowAssignedView"];
export type WorkflowList = components["schemas"]["WorkflowListView"];
export type WorkflowRun = components["schemas"]["WorkflowRunView"];
export type WorkflowStep = components["schemas"]["WorkflowStepView"];
export type KeptWorkflowRuns = components["schemas"]["WorkflowKeptRunsPage"];
export type WorkflowDefinition = components["schemas"]["WorkflowDefinitionView"];
export type SavedWorkflow = components["schemas"]["WorkflowSavedView"];

/** Where the workflows written are asked for, under the API base. */
export const WORKFLOWS_API_PATH = "/workflows";
export const WORKFLOW_RUNS_API_PATH = "/workflow-runs";

export function agentWorkflowsApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/workflows`;
}

export function agentWorkflowRemovalApiPath(agentId: string): string {
  return `${agentWorkflowsApiPath(agentId)}/removals`;
}

export function agentWorkflowRunApiPath(agentId: string): string {
  return `/agents/${encodeURIComponent(agentId)}/workflow-runs`;
}

export function workflowApiPath(workflowId: string): string {
  return `${WORKFLOWS_API_PATH}/${encodeURIComponent(workflowId)}`;
}

function isObject(payload: unknown): payload is Record<string, unknown> {
  return typeof payload === "object" && payload !== null && !Array.isArray(payload);
}

/** The workflows an agent may run, or null when the body is not that. */
export function readAssigned(payload: unknown): AssignedWorkflows | null {
  if (!isObject(payload) || typeof payload["agent_id"] !== "string" || !Array.isArray(payload["workflows"])) {
    return null;
  }
  return {
    agent_id: payload["agent_id"],
    names_shown: payload["names_shown"] === true,
    workflows: (payload["workflows"] as unknown[]).filter((one): one is string => typeof one === "string"),
    may_change: payload["may_change"] === true,
    switched_on: payload["switched_on"] === true,
  };
}

/** The workflows written, or null when the body is not that. */
export function readWorkflowList(payload: unknown): WorkflowList | null {
  if (!isObject(payload) || !Array.isArray(payload["workflows"])) {
    return null;
  }
  const workflows = (payload["workflows"] as unknown[]).flatMap((one) =>
    isObject(one) && typeof one["workflow_id"] === "string" && typeof one["version"] === "number" && typeof one["name"] === "string"
      ? [{ workflow_id: one["workflow_id"], version: one["version"], name: one["name"] }]
      : [],
  );
  return { workflows, switched_on: payload["switched_on"] === true };
}

function readSteps(value: unknown): WorkflowStep[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return (value as unknown[]).flatMap((one) =>
    isObject(one) && typeof one["step_id"] === "string" && typeof one["status"] === "string"
      ? [
          {
            step_id: one["step_id"],
            status: one["status"],
            cause: typeof one["cause"] === "string" ? one["cause"] : null,
            detail: typeof one["detail"] === "string" ? one["detail"] : "",
            attempts: typeof one["attempts"] === "number" ? one["attempts"] : 0,
            seconds: typeof one["seconds"] === "number" ? one["seconds"] : 0,
          },
        ]
      : [],
  );
}

/** One run, or null when the body is not one. */
export function readRun(payload: unknown): WorkflowRun | null {
  if (
    !isObject(payload) ||
    typeof payload["run_id"] !== "string" ||
    typeof payload["workflow_id"] !== "string" ||
    typeof payload["outcome"] !== "string"
  ) {
    return null;
  }
  return {
    run_id: payload["run_id"],
    workflow_id: payload["workflow_id"],
    version: typeof payload["version"] === "number" ? payload["version"] : 0,
    agent_id: typeof payload["agent_id"] === "string" ? payload["agent_id"] : "",
    outcome: payload["outcome"],
    failed_step: typeof payload["failed_step"] === "string" ? payload["failed_step"] : null,
    steps: readSteps(payload["steps"]),
    candidates_opened: Array.isArray(payload["candidates_opened"])
      ? (payload["candidates_opened"] as unknown[]).filter((one): one is string => typeof one === "string")
      : [],
  };
}

/** The runs kept, or null when the body is not that. */
export function readKeptRuns(payload: unknown): KeptWorkflowRuns | null {
  if (!isObject(payload) || !Array.isArray(payload["runs"])) {
    return null;
  }
  const runs = (payload["runs"] as unknown[]).flatMap((one) => {
    const run = readRun(one);
    return run !== null && isObject(one) && typeof one["run_by"] === "string" && typeof one["started_at"] === "string"
      ? [{ ...run, run_by: one["run_by"], started_at: one["started_at"] }]
      : [];
  });
  return { runs };
}

/** How a run ended, in words. */
export function outcomeWords(outcome: string): string {
  switch (outcome) {
    case "success":
      return "Every step finished";
    case "partial":
      return "Finished, with a step recorded as a gap";
    case "failure":
      return "Stopped on a failed step";
    default:
      return outcome;
  }
}

/** What became of one step, in words. */
export function statusWords(status: string): string {
  switch (status) {
    case "ok":
      return "Done";
    case "failed":
      return "Failed";
    case "skipped":
      return "Skipped";
    default:
      return status;
  }
}

/** Why a step did not complete, in words. */
export function causeWords(cause: string): string {
  switch (cause) {
    case "condition_not_met":
      return "its condition was not met";
    case "handler_not_needed":
      return "the step it stands in for did not fail";
    case "run_stopped":
      return "an earlier step stopped the run";
    case "input_missing":
      return "an earlier step gave it nothing to read";
    case "refused":
      return "the gate refused the call";
    case "failed_after_retries":
      return "it failed every time it was tried";
    case "invalid_output":
      return "what it returned was not what the workflow named";
    case "write_not_offered":
      return "it would change something, which a workflow run is not offered";
    default:
      return cause.replaceAll("_", " ");
  }
}

/** The body of a save: the slug and the definition read out of the text a person wrote. */
export function saveBody(workflowId: string, text: string): { workflow_id: string; definition: Record<string, unknown> } | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return null;
  }
  return isObject(parsed) ? { workflow_id: workflowId.trim(), definition: parsed } : null;
}
