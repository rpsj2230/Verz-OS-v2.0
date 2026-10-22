/**
 * The peak load runs under the service levels: drawn from what the API sent, each lane beside the
 * objective it promises, a run smaller than the stated peak saying so, and an empty list for a
 * reader the API sent none.
 *
 * Task ids: M36.2.4.3
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, cleanup, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  AT_THE_PEAK,
  DID_NOT_HOLD,
  HELD,
  LOAD_RUNS_HEADING,
  NO_LOAD_RUNS,
  SMALLER_THAN_THE_PEAK,
} from "../src/pages/reports/LoadRuns";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { COMPANY_CONSOLE, NAVIGATION_ADDRESS } from "./support/navigation";
import { PAGES } from "./support/pageCases";
import { installRadixStubs } from "./support/radix";

beforeAll(() => {
  installRadixStubs();
});

const API = "/api/v1";
const RUNS = `${API}/report/service-levels/load-runs`;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", "x-trace-id": "trace-runs" } });
}

function run(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    run_id: "r1",
    started_at: "2026-10-01T09:00:00Z",
    commit: "abc1234",
    profile: "check",
    seconds_run: 1,
    planned: 80,
    sent: 78,
    not_sent: 2,
    most_in_flight: 9,
    at_stated_peak: false,
    held: true,
    interactive_shed: 0,
    lanes: [
      { lane: "fast", requests: 40, p95_ms: 12.4, success_rate: 1, shed: 0, objective_p95_ms: 500, objective_success_rate: 0.995 },
      { lane: "task", requests: 3, p95_ms: null, success_rate: null, shed: 0, objective_p95_ms: null, objective_success_rate: null },
    ],
    findings: ["the fast lane held"],
    ...over,
  };
}

async function mounted(runs: unknown[]) {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
  const base = PAGES["/service-levels"]?.answers ?? {};
  const idp = fakeIdentityProvider({
    api(url) {
      const parsed = new URL(url, "https://console.test");
      if (parsed.pathname === NAVIGATION_ADDRESS) {
        return json(COMPANY_CONSOLE);
      }
      if (parsed.pathname === RUNS) {
        return json({ runs });
      }
      return parsed.pathname in base ? json((base as Record<string, unknown>)[parsed.pathname]) : null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: ["/service-levels"] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => expect(container.querySelector("[data-slot='report-page']")).not.toBeNull(), { timeout: 10_000 });
  await waitFor(() => expect(container.textContent).toContain(LOAD_RUNS_HEADING), { timeout: 10_000 });
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 30));
  });
  return container.querySelector("[data-slot='report-page']") as Element;
}

describe("the peak load runs", () => {
  test("each lane is drawn beside what it promises, and a lane with no objective is drawn without one", async () => {
    // What breaks if this is deleted: a measured figure with no objective beside it, or an
    // objective drawn for a lane that has none.
    const page = await mounted([run()]);
    expect(page.textContent).toContain(HELD);
    expect(page.textContent).toContain("fast: p95 12 ms, promised 500 ms; success 100.0%, promised 99.5%");
    expect(page.textContent).toContain("task: p95 Not measured; success Not measured");
    expect(page.textContent).not.toContain("task: p95 Not measured, promised");
  });

  test("a run smaller than the stated peak says so and one that did not hold says that", async () => {
    // What breaks if this is deleted: a bounded run that held reads as the peak test.
    const small = await mounted([run()]);
    expect(small.textContent).toContain(SMALLER_THAN_THE_PEAK);
    expect(small.textContent).not.toContain(AT_THE_PEAK);
    const peak = await mounted([run({ at_stated_peak: true, held: false })]);
    expect(peak.textContent).toContain(AT_THE_PEAK);
    expect(peak.textContent).toContain(DID_NOT_HOLD);
    expect(peak.textContent).toContain("sent 78 of 80");
  });

  test("no run is an empty list with an act and a who, and nothing about why", async () => {
    // What breaks if this is deleted: a department reader's empty answer is drawn differently from
    // an install that has never been run, or with a reason.
    const page = await mounted([]);
    expect(page.textContent).toContain(NO_LOAD_RUNS);
    expect(page.textContent).toContain("A run is kept when an operator runs the peak load test");
    expect(page.textContent).not.toMatch(/because|withheld|permission/iu);
  });
});
