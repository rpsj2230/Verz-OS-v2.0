/**
 * The requests split between agents, on the Features page: each run kept in words, with why the
 * specialists were not run together, what each did and what it cost, and that a run is kept as how it
 * went and never what it was about. The shapes are read from `brain.coordination_routes` itself.
 *
 * Task ids: M18.6.2
 */

import { waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { FEATURES_API_PATH, FEATURES_PATH } from "../src/pages/featuresQuery";
import { childWords, COORDINATED_RUNS_API_PATH, modeWords, whyWords } from "../src/pages/agents/agentSpecialistsQuery";
import { NO_COORDINATED_RUNS, WHAT_IS_KEPT } from "../src/pages/install/CoordinatedRunsPanel";
import { json, mountPage, type Answer } from "./support/pageHarness";
import { backendModelFields } from "./support/python";
import { installRadixStubs } from "./support/radix";

beforeAll(() => {
  installRadixStubs();
});

const FEATURES = `GET /api/v1${FEATURES_API_PATH}`;
const LIST = `GET /api/v1${COORDINATED_RUNS_API_PATH}`;
const ROUTES = "src/brain/coordination_routes.py";

function kept(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    run_id: "coordinated-1",
    coordinator_id: "quote-helper",
    started_at: "2019-03-04T09:00:00Z",
    asked_by: "u_asker",
    mode: "sequential",
    why: ["gate_declined", "no_room"],
    children: [
      { subtask_id: "price", callee_id: "pricing", depth: 1, reach_hash: "a".repeat(32), status: "delivered", cost_minor: 1200, seconds: 2.5 },
      { subtask_id: "terms", callee_id: "legal", depth: 1, reach_hash: "b".repeat(32), status: "timed_out", cost_minor: 0, seconds: 30 },
    ],
    complete: false,
    total_minor: 1200,
    currency: "SGD",
    ...overrides,
  };
}

function page(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return { runs: [kept()], switched_on: true, ...overrides };
}

async function features(answers: Record<string, Answer>) {
  return mountPage(
    FEATURES_PATH,
    async () => {
      const { Features } = await import("../src/pages/Features");
      return <Features />;
    },
    { [FEATURES]: () => json({ features: [], components_are_chosen_by_the_profile: true, plugins_have_no_loader: true }), ...answers },
  );
}

describe("what the panel draws", () => {
  test("a run kept in words: who asked, why not together, each specialist, and the estimate", async () => {
    // What breaks if this is deleted: a run drawn as a row of codes, a reason for running one after
    // another missing, or a cost with no currency beside it.
    const { container } = await features({ [LIST]: () => json(page()) });
    const text = container.textContent ?? "";
    expect(text).toContain(modeWords("sequential"));
    expect(text).toContain("quote-helper, asked by u_asker");
    expect(text).toContain(whyWords("gate_declined"));
    expect(text).toContain(whyWords("no_room"));
    expect(text).toContain(`price: pricing, ${childWords("delivered")}`);
    expect(text).toContain(`terms: legal, ${childWords("timed_out")}`);
    expect(text).toContain("SGD");
    expect(text).toContain(WHAT_IS_KEPT);
  });

  test("with none kept it says how one is made, and while the switch is off it says so in the server's words", async () => {
    // What breaks if this is deleted: an empty panel with no way forward, or a switch that is off and
    // unmentioned.
    const none = await features({ [LIST]: () => json(page({ runs: [], switched_on: false })) });
    expect(none.container.textContent).toContain(NO_COORDINATED_RUNS);
    expect(none.container.textContent).toContain("Profile");
    await waitFor(() => {
      expect(none.container.textContent).toContain("handing a request between agents is switched off on this install");
    });
  });
});

describe("the shapes", () => {
  test("every field the panel reads is a field the route declares", () => {
    // What breaks if this is deleted: a field renamed in `brain.coordination_routes` that the panel goes
    // on reading, which draws as an empty sentence in production.
    expect(Object.keys(page()).sort()).toEqual(backendModelFields(ROUTES, "CoordinationKeptRunsPage").sort());
    expect(Object.keys(kept()).sort()).toEqual(backendModelFields(ROUTES, "CoordinationKeptRunView").sort());
  });
});
