/**
 * The plan-weighing panel on the Features page: the decisions kept, a plan weighed from pasted JSON
 * and what the gate and the merge say, and that it says nothing starts only while the API says so.
 *
 * Mounted through the Features page, because that is where the panel is drawn. The shapes are read
 * from `brain.orchestration_routes` itself, so a renamed field fails here.
 *
 * Task ids: M18.2.1, M18.2.2, M18.2.3, M18.2.4, M18.4.2, M18.4.3
 */

import { act, fireEvent, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { FEATURES_API_PATH, FEATURES_PATH } from "../src/pages/featuresQuery";
import {
  NOT_JSON,
  NOTHING_STARTS,
  REHEARSALS_API_PATH,
  SWITCHED_OFF,
  summary,
  verdictWords,
} from "../src/pages/orchestrationQuery";
import { button, json, mountPage, type Answer } from "./support/pageHarness";
import { backendModelFields } from "./support/python";
import { installRadixStubs } from "./support/radix";

beforeAll(() => {
  installRadixStubs();
});

const FEATURES = `GET /api/v1${FEATURES_API_PATH}`;
const LIST = `GET /api/v1${REHEARSALS_API_PATH}`;
const WEIGH = `POST /api/v1${REHEARSALS_API_PATH}`;
const ROUTES = "src/brain/orchestration_routes.py";

function gate(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    run_id: "rehearsal-1",
    decided_at: "2019-03-04T09:00:00Z",
    decided_by: "u_admin",
    branches: 4,
    depth: 0,
    cost_multiplier: 1.0,
    speedup: 4.0,
    largest_share: 0.25,
    evaluated: ["enough_branches"],
    failed: [],
    verdict: "parallel",
    ...overrides,
  };
}

function page(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    decisions: [gate()],
    rehearsal_is_on: true,
    weights_note: "WEIGHTS-NOTE",
    ...overrides,
  };
}

function weighed(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    run_id: "rehearsal-2",
    gate: gate({ run_id: "rehearsal-2", verdict: "single_loop", failed: ["enough_branches"], branches: 1, speedup: 1 }),
    merged: null,
    nothing_is_started: true,
    ...overrides,
  };
}

const FEATURE_LIST = { features: [], components_are_chosen_by_the_profile: true, plugins_have_no_loader: true };

async function featuresPage(answers: Record<string, Answer>) {
  return mountPage(
    FEATURES_PATH,
    async () => {
      const { Features } = await import("../src/pages/Features");
      return <Features />;
    },
    { [FEATURES]: () => json(FEATURE_LIST), ...answers },
  );
}

describe("what the plan-weighing panel draws", () => {
  test("a kept decision in words, with what the gate found, and that nothing is started", async () => {
    // What breaks if this is deleted: a verdict drawn as a bare word, or a panel that reads as a
    // running orchestrator when no agent is started.
    const { container } = await featuresPage({ [LIST]: () => json(page()) });
    const text = container.textContent ?? "";
    expect(text).toContain(verdictWords("parallel"));
    expect(text).toContain(summary(gate() as never));
    expect(text).toContain(NOTHING_STARTS);
    expect(text).toContain("WEIGHTS-NOTE");
  });

  test("the verdict words keep a single loop from reading as a refusal", () => {
    // What breaks if this is deleted: a plan kept as one loop shown as failed, which it is not:
    // it is the default and the whole plan still runs.
    expect(verdictWords("single_loop")).toBe("Kept as one loop");
    expect(verdictWords("single_loop")).not.toMatch(/refus|fail|denied/i);
  });

  test("the switch being off says so and offers no form", async () => {
    // What breaks if this is deleted: a form the route will refuse.
    const { container } = await featuresPage({ [LIST]: () => json(page({ rehearsal_is_on: false })) });
    expect(container.textContent).toContain(SWITCHED_OFF);
    expect(container.querySelector("#plan-to-weigh")).toBeNull();
  });
});

describe("weighing a plan", () => {
  test("text that is not JSON is told so and nothing is sent", async () => {
    // What breaks if this is deleted: a half-typed plan posted, or silence.
    const { container, sent } = await featuresPage({ [LIST]: () => json(page()) });
    fireEvent.change(container.querySelector("#plan-to-weigh") as HTMLTextAreaElement, { target: { value: "{no" } });
    await act(async () => {
      fireEvent.click(button(container, "Weigh plan"));
    });
    expect(container.textContent).toContain(NOT_JSON);
    expect(sent.filter((one) => one.method === "POST")).toHaveLength(0);
  });

  test("a plan is posted as typed, the gate's answer is drawn and the list is read again", async () => {
    // What breaks if this is deleted: a plan altered on the way or an answer not shown.
    const { container, sent } = await featuresPage({
      [LIST]: () => json(page()),
      [WEIGH]: () => json(weighed(), 201),
    });
    fireEvent.change(container.querySelector("#plan-to-weigh") as HTMLTextAreaElement, {
      target: { value: '{"subtasks": []}' },
    });
    await act(async () => {
      fireEvent.click(button(container, "Weigh plan"));
    });
    await waitFor(() => {
      expect(container.textContent).toContain(verdictWords("single_loop"));
    });
    expect(container.textContent).toContain("failed: enough branches");
    expect(sent.filter((one) => one.method === "POST").map((one) => one.body)).toEqual([{ subtasks: [] }]);
    expect(sent.filter((one) => one.method === "GET" && one.path.includes("orchestration")).length).toBeGreaterThanOrEqual(2);
  });

  test("a merge with a gap states what is missing and shows each subtask's cost and the total", async () => {
    // What breaks if this is deleted: an incomplete answer drawn as complete, or a total that is
    // not the rows.
    const merged = {
      values: { part_a: { count: 3 } },
      reports: [
        { subtask_id: "part_a", minor: 4, seconds: 2 },
        { subtask_id: "part_d", minor: 7, seconds: 2 },
      ],
      total_minor: 11,
      currency: "USD",
      complete: false,
      notice: "This answer is missing what these would have added: GAP-OBJECTIVE.",
    };
    const { container } = await featuresPage({
      [LIST]: () => json(page()),
      [WEIGH]: () => json(weighed({ merged }), 201),
    });
    fireEvent.change(container.querySelector("#plan-to-weigh") as HTMLTextAreaElement, { target: { value: "{}" } });
    await act(async () => {
      fireEvent.click(button(container, "Weigh plan"));
    });
    await waitFor(() => {
      expect(container.textContent).toContain("GAP-OBJECTIVE");
    });
    expect(container.textContent).toContain("part_d: USD 0.07");
    expect(container.textContent).toContain("Total cost: USD 0.11");
  });

  test("a refusal is the API's sentence", async () => {
    // What breaks if this is deleted: a refusal replaced by a console sentence that says less.
    const { container } = await featuresPage({
      [LIST]: () => json(page()),
      [WEIGH]: () => json({ message: "REFUSED-BY-THE-GATE", trace_id: "T-9" }, 404),
    });
    fireEvent.change(container.querySelector("#plan-to-weigh") as HTMLTextAreaElement, { target: { value: "{}" } });
    await act(async () => {
      fireEvent.click(button(container, "Weigh plan"));
    });
    await waitFor(() => {
      expect(container.textContent).toContain("REFUSED-BY-THE-GATE");
    });
  });
});

describe("the shapes", () => {
  test("every field the panel reads is a field the route declares", () => {
    // What breaks if this is deleted: a field renamed in `brain.orchestration_routes` that the panel
    // goes on reading, which renders as an empty sentence in production.
    expect(Object.keys(page()).sort()).toEqual(backendModelFields(ROUTES, "DecisionsPage").sort());
    expect(Object.keys(gate()).sort()).toEqual(backendModelFields(ROUTES, "GateView").sort());
    expect(Object.keys(weighed()).sort()).toEqual(backendModelFields(ROUTES, "PlanWeighedView").sort());
  });
});
