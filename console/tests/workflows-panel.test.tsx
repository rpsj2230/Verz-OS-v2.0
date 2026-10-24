/**
 * The stored workflows on the Features page: the ones written, writing the next version of one, and
 * the runs kept in words. The shapes are read from `brain.workflow_routes` itself.
 *
 * Task ids: M17.6.5
 */

import { act, fireEvent, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { FEATURES_API_PATH, FEATURES_PATH } from "../src/pages/featuresQuery";
import { causeWords, outcomeWords, statusWords, WORKFLOW_RUNS_API_PATH, WORKFLOWS_API_PATH } from "../src/pages/agents/agentWorkflowsQuery";
import { NO_WORKFLOW_RUNS, NO_WORKFLOWS_WRITTEN, NOT_JSON_WORKFLOW, SAVE_AS_NEXT } from "../src/pages/install/WorkflowsPanel";
import { button, json, mountPage, type Answer } from "./support/pageHarness";
import { backendModelFields } from "./support/python";
import { installRadixStubs } from "./support/radix";

beforeAll(() => {
  installRadixStubs();
});

const FEATURES = `GET /api/v1${FEATURES_API_PATH}`;
const LIST = `GET /api/v1${WORKFLOWS_API_PATH}`;
const SAVE = `POST /api/v1${WORKFLOWS_API_PATH}`;
const RUNS = `GET /api/v1${WORKFLOW_RUNS_API_PATH}`;
const ROUTES = "src/brain/workflow_routes.py";

function listed(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return { workflows: [{ workflow_id: "price-check", version: 3, name: "Price check" }], switched_on: true, ...overrides };
}

function keptRun(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    run_id: "workflow-1",
    workflow_id: "price-check",
    version: 3,
    agent_id: "quote-helper",
    outcome: "failure",
    failed_step: "read_prices",
    steps: [{ step_id: "read_prices", status: "failed", cause: "failed_after_retries", detail: "", attempts: 3, seconds: 1.5 }],
    candidates_opened: [],
    run_by: "u_admin",
    started_at: "2019-03-04T09:00:00Z",
    ...overrides,
  };
}

async function features(answers: Record<string, Answer>) {
  return mountPage(
    FEATURES_PATH,
    async () => {
      const { Features } = await import("../src/pages/Features");
      return <Features />;
    },
    {
      [FEATURES]: () => json({ features: [], components_are_chosen_by_the_profile: true, plugins_have_no_loader: true }),
      [LIST]: () => json(listed()),
      [RUNS]: () => json({ runs: [keptRun()] }),
      ...answers,
    },
  );
}

describe("what the panel draws", () => {
  test("the workflows written with their newest version, and a kept run step by step in words", async () => {
    // What breaks if this is deleted: a workflow listed by id alone, a run drawn as a bare outcome,
    // or a failed step with no cause.
    const { container } = await features({});
    const text = container.textContent ?? "";
    expect(text).toContain("Price check");
    expect(text).toContain("version 3");
    expect(text).toContain(outcomeWords("failure"));
    expect(text).toContain("Run through quote-helper by u_admin");
    expect(text).toContain(`read_prices: ${statusWords("failed")}, ${causeWords("failed_after_retries")}`);
  });

  test("with none written or run it says what would make one, and the server's sentence is drawn while it is off", async () => {
    // What breaks if this is deleted: empty lists with no way forward, or a switch that is off and
    // unmentioned.
    const { container } = await features({
      [LIST]: () => json(listed({ workflows: [], switched_on: false })),
      [RUNS]: () => json({ runs: [] }),
    });
    const text = container.textContent ?? "";
    expect(text).toContain(NO_WORKFLOWS_WRITTEN);
    expect(text).toContain(NO_WORKFLOW_RUNS);
    await waitFor(() => {
      expect(container.textContent).toContain("running a stored workflow is switched off on this install");
    });
  });
});

describe("writing a workflow", () => {
  test("text that is not a JSON object is told so and nothing is sent", async () => {
    // What breaks if this is deleted: a half-typed definition posted, or silence.
    const { container, sent } = await features({});
    fireEvent.change(container.querySelectorAll("input")[0] as HTMLInputElement, { target: { value: "price-check" } });
    fireEvent.change(container.querySelector("textarea") as HTMLTextAreaElement, { target: { value: "[1, 2]" } });
    await act(async () => {
      fireEvent.click(button(container, SAVE_AS_NEXT));
    });
    expect(container.textContent).toContain(NOT_JSON_WORKFLOW);
    expect(sent.filter((one) => one.method === "POST")).toHaveLength(0);
  });

  test("a definition is posted as typed under its name, and the version it became is said", async () => {
    // What breaks if this is deleted: a definition altered on the way, or a save that does not say
    // which version it wrote.
    const { container, sent } = await features({
      [SAVE]: () => json({ workflow_id: "price-check", version: 4, name: "Price check", steps: 1 }, 201),
    });
    fireEvent.change(container.querySelectorAll("input")[0] as HTMLInputElement, { target: { value: " price-check " } });
    fireEvent.change(container.querySelector("textarea") as HTMLTextAreaElement, { target: { value: '{"name": "Price check", "steps": []}' } });
    await act(async () => {
      fireEvent.click(button(container, SAVE_AS_NEXT));
    });
    await waitFor(() => {
      expect(container.textContent).toContain("price-check was saved as version 4.");
    });
    expect(sent.filter((one) => one.method === "POST").map((one) => one.body)).toEqual([
      { workflow_id: "price-check", definition: { name: "Price check", steps: [] } },
    ]);
  });

  test("a definition the reader refuses is told in the route's own words", async () => {
    // What breaks if this is deleted: a refused definition drawn as saved.
    const { container } = await features({
      [SAVE]: () => json({ outcome: "refused", sentence: "Nothing was saved: step read_prices names no tool." }, 409),
    });
    fireEvent.change(container.querySelectorAll("input")[0] as HTMLInputElement, { target: { value: "price-check" } });
    fireEvent.change(container.querySelector("textarea") as HTMLTextAreaElement, { target: { value: "{}" } });
    await act(async () => {
      fireEvent.click(button(container, SAVE_AS_NEXT));
    });
    await waitFor(() => {
      expect(container.textContent).toContain("Nothing was saved: step read_prices names no tool.");
    });
  });
});

describe("the shapes", () => {
  test("every field the panel reads is a field the route declares", () => {
    // What breaks if this is deleted: a field renamed in `brain.workflow_routes` that the panel goes on
    // reading, which draws as an empty sentence in production.
    expect(Object.keys(listed()).sort()).toEqual(backendModelFields(ROUTES, "WorkflowListView").sort());
    // A kept run is a run with who ran it and when, so the route declares it as the run's subclass.
    expect(Object.keys(keptRun()).sort()).toEqual(
      [...backendModelFields(ROUTES, "WorkflowRunView"), ...backendModelFields(ROUTES, "WorkflowKeptRunView")].sort(),
    );
  });
});
