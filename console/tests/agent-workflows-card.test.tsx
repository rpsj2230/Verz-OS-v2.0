/**
 * An agent's Workflows card: the stored workflows it may run, giving it one, taking one off, and
 * running one and reading what each step did. The shapes are read from `brain.workflow_routes`
 * itself, so a renamed field fails here.
 *
 * Task ids: M17.6.5
 */

import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  CHOOSE_A_WORKFLOW,
  GIVE_IT,
  NO_WORKFLOWS,
  WITHDRAW_QUESTION,
} from "../src/pages/agents/AgentWorkflows";
import { agentWorkflowRemovalApiPath, agentWorkflowRunApiPath, agentWorkflowsApiPath, causeWords, outcomeWords, statusWords, WORKFLOWS_API_PATH } from "../src/pages/agents/agentWorkflowsQuery";
import { json, mountPage, type Answer, type Mounted } from "./support/pageHarness";
import { backendModelFields } from "./support/python";
import { installRadixStubs } from "./support/radix";

beforeAll(() => {
  installRadixStubs();
});

const AGENT = "quote-helper";
const ASSIGNED = `GET /api/v1${agentWorkflowsApiPath(AGENT)}`;
const GIVE = `POST /api/v1${agentWorkflowsApiPath(AGENT)}`;
const TAKE = `POST /api/v1${agentWorkflowRemovalApiPath(AGENT)}`;
const RUN = `POST /api/v1${agentWorkflowRunApiPath(AGENT)}`;
const WRITTEN = `GET /api/v1${WORKFLOWS_API_PATH}`;
const ROUTES = "src/brain/workflow_routes.py";

function assigned(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return { agent_id: AGENT, names_shown: true, workflows: ["price-check"], may_change: true, switched_on: true, ...overrides };
}

function written(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    workflows: [
      { workflow_id: "price-check", version: 2, name: "Price check" },
      { workflow_id: "renewal-brief", version: 1, name: "Renewal brief" },
    ],
    switched_on: true,
    ...overrides,
  };
}

function step(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return { step_id: "read_prices", status: "ok", cause: null, detail: "", attempts: 1, seconds: 0.4, ...overrides };
}

function run(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    run_id: "workflow-1",
    workflow_id: "price-check",
    version: 2,
    agent_id: AGENT,
    outcome: "partial",
    failed_step: null,
    steps: [step(), step({ step_id: "write_summary", status: "skipped", cause: "condition_not_met", detail: "total is under 10", attempts: 0, seconds: 0 })],
    candidates_opened: [],
    ...overrides,
  };
}

async function card(answers: Record<string, Answer>): Promise<Mounted> {
  return mountPage(
    "/card",
    async () => {
      const { AgentWorkflows } = await import("../src/pages/agents/AgentWorkflows");
      return (
        <>
          <h1>Card</h1>
          <AgentWorkflows agentId={AGENT} />
        </>
      );
    },
    { [ASSIGNED]: () => json(assigned()), [WRITTEN]: () => json(written()), ...answers },
  );
}

function posts(mounted: Mounted): { readonly path: string; readonly body: unknown }[] {
  return mounted.sent.filter((one) => one.method === "POST").map((one) => ({ path: one.path, body: one.body }));
}

describe("what the workflows card draws", () => {
  test("the workflows the agent may run, each with a run and a withdrawal, and the read-only sentence", async () => {
    // What breaks if this is deleted: a card that lists nothing the route sent, or offers a take-off
    // to somebody the route told it may not change the agent.
    const { container } = await card({});
    expect(container.textContent).toContain("price-check");
    expect(container.querySelector('[aria-label="Run price-check through this agent"]')).not.toBeNull();
    expect(container.querySelector('[aria-label="Withdraw price-check from this agent"]')).not.toBeNull();
    expect(container.textContent).toContain("A step that would change something is not offered");
    const readOnly = await card({ [ASSIGNED]: () => json(assigned({ may_change: false })) });
    expect(readOnly.container.querySelector('[aria-label="Withdraw price-check from this agent"]')).toBeNull();
    expect(readOnly.container.textContent).not.toContain(CHOOSE_A_WORKFLOW);
  });

  test("an agent with none says what would give it one, and a reader told no names is drawn no card", async () => {
    // What breaks if this is deleted: an empty card that says nothing about how a row would appear, or
    // a heading over nothing for somebody who is not told what the agent may run.
    const empty = await card({ [ASSIGNED]: () => json(assigned({ workflows: [] })) });
    expect(empty.container.textContent).toContain(NO_WORKFLOWS);
    expect(empty.container.textContent).toContain("Install, Features");
    const hidden = await card({ [ASSIGNED]: () => json(assigned({ names_shown: false, workflows: [], may_change: false })) });
    expect(hidden.container.textContent).not.toContain("Workflows");
  });

  test("while the switch is off the run is disabled and the server's own sentence is drawn", async () => {
    // What breaks if this is deleted: a run button that the route refuses with a sentence the card
    // never shows, or a sentence typed here that the server could not retire.
    const { container } = await card({ [ASSIGNED]: () => json(assigned({ switched_on: false })) });
    await waitFor(() => {
      expect(container.textContent).toContain("running a stored workflow is switched off on this install");
    });
    expect((container.querySelector('[aria-label="Run price-check through this agent"]') as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("what the card sends", () => {
  test("a workflow chosen is given, and the list is read again", async () => {
    // What breaks if this is deleted: an assignment that names another workflow than the one chosen,
    // or a list that goes on showing what it showed before.
    const mounted = await card({ [GIVE]: () => json(assigned({ workflows: ["price-check", "renewal-brief"] })) });
    const select = within(mounted.container).getByLabelText(CHOOSE_A_WORKFLOW);
    fireEvent.change(select, { target: { value: "renewal-brief" } });
    await act(async () => {
      fireEvent.click(within(mounted.container).getByRole("button", { name: GIVE_IT }));
    });
    await waitFor(() => {
      expect(posts(mounted)).toEqual([{ path: agentWorkflowsApiPath(AGENT).replace(/^/, "/api/v1"), body: { workflow_id: "renewal-brief" } }]);
    });
  });

  test("a withdrawal is confirmed first and sends the workflow it named", async () => {
    // What breaks if this is deleted: an agent losing a workflow on one press, or the wrong one.
    const mounted = await card({ [TAKE]: () => json(assigned({ workflows: [] })) });
    fireEvent.click(within(mounted.container).getByRole("button", { name: "Withdraw price-check from this agent" }));
    const asking = await screen.findByRole("alertdialog", { name: WITHDRAW_QUESTION("price-check") });
    expect(posts(mounted)).toEqual([]);
    await act(async () => {
      fireEvent.click(within(asking).getByRole("button", { name: "Withdraw it" }));
    });
    await waitFor(() => {
      expect(posts(mounted)).toEqual([{ path: `/api/v1${agentWorkflowRemovalApiPath(AGENT)}`, body: { workflow_id: "price-check" } }]);
    });
  });

  test("a run is drawn step by step in words, and a refusal is the route's own sentence", async () => {
    // What breaks if this is deleted: a run drawn as a bare outcome word, steps with no cause, or a
    // refused run drawn as a success.
    const mounted = await card({ [RUN]: () => json(run()) });
    await act(async () => {
      fireEvent.click(within(mounted.container).getByRole("button", { name: "Run price-check through this agent" }));
    });
    await waitFor(() => {
      expect(mounted.container.textContent).toContain(outcomeWords("partial"));
    });
    const text = mounted.container.textContent ?? "";
    expect(text).toContain(statusWords("skipped"));
    expect(text).toContain(causeWords("condition_not_met"));
    expect(text).toContain("total is under 10");
    expect(posts(mounted)).toEqual([{ path: `/api/v1${agentWorkflowRunApiPath(AGENT)}`, body: { workflow_id: "price-check" } }]);

    const refused = await card({ [RUN]: () => json({ outcome: "refused", sentence: "Nothing was started: that agent does not run that workflow." }, 409) });
    await act(async () => {
      fireEvent.click(within(refused.container).getByRole("button", { name: "Run price-check through this agent" }));
    });
    await screen.findByText("Nothing was started: that agent does not run that workflow.");
  });
});

describe("the shapes", () => {
  test("every field the card reads is a field the route declares", () => {
    // What breaks if this is deleted: a field renamed in `brain.workflow_routes` that the card goes on
    // reading, which draws as an empty sentence in production.
    expect(Object.keys(assigned()).sort()).toEqual(backendModelFields(ROUTES, "WorkflowAssignedView").sort());
    expect(Object.keys(written()).sort()).toEqual(backendModelFields(ROUTES, "WorkflowListView").sort());
    expect(Object.keys(run()).sort()).toEqual(backendModelFields(ROUTES, "WorkflowRunView").sort());
    expect(Object.keys(step()).sort()).toEqual(backendModelFields(ROUTES, "WorkflowStepView").sort());
  });
});
