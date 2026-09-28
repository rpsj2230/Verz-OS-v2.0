/**
 * An agent's pinned model on its profile. The provider register's terms and the add form moved to
 * the Models and routing module's own pages on 2026-09-28 and are held in
 * `tests/models-module.test.tsx`.
 *
 * Driven through the real route table with the page cases' stand-in answers, each overridden where
 * the pin is what is under test.
 *
 * Task ids: M5.7.3
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  agentSteps,
  CHOOSE_A_MODEL,
  MODEL_HEADING,
  PASSED_OVER,
  PIN_MODEL,
  pinChoices,
  PINNED_ROLE,
  STEPS_CAPTION,
} from "../src/pages/agentModelPinQuery";
import type { RungRow } from "../src/pages/matrixQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { PAGES } from "./support/pageCases";

beforeAll(async () => {
  await import("../src/pages/Agent");
}, 60_000);

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
}

async function mounted(path: string, answers: Record<string, unknown>): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url) {
      const pathname = new URL(url, "https://console.test").pathname;
      return pathname in answers ? json(answers[pathname]) : null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  return { container, idp };
}

function writes(idp: FakeIdp): { method: string; body: unknown }[] {
  return idp.calls
    .filter((call) => String(call.url).includes("/api/v1/") && (call.init?.method ?? "GET") !== "GET")
    .map((call) => ({
      method: call.init?.method ?? "GET",
      body: typeof call.init?.body === "string" ? (JSON.parse(call.init.body) as unknown) : null,
    }));
}

describe("an agent's pinned model", () => {
  test("the profile draws the order a question tries, and pins a model chosen from the matrix only from the confirmation", async () => {
    // What breaks if this is deleted: M5.7.3's pin has no way in from the console, is typed as a
    // slug and a model name nobody can check, or is sent from an unconfirmed press that moves
    // every question to the agent.
    const { container, idp } = await mounted("/agents/quote-helper/profile", {
      ...PAGES["/agents/:agentId/:tab"]?.answers,
      "/api/v1/agents/quote-helper/model-pin": {
        agent_id: "quote-helper",
        provider: "anthropic",
        model: "claude-sonnet-5",
      },
    });
    await waitFor(() => {
      if (!container.querySelector('form[aria-label="Pin a model for this agent"]')) {
        throw new Error("the profile has not opened");
      }
    });
    expect(container.textContent).toContain(MODEL_HEADING);
    expect(container.textContent).toContain("This agent answers at the Medium level on the failover matrix.");
    const order = [...container.querySelectorAll("table")].find((one) => one.querySelector("caption")?.textContent === STEPS_CAPTION);
    expect([...(order?.querySelectorAll("tbody tr") ?? [])].map((row) => row.textContent)).toEqual([
      "1Anthropic (Claude)claude-sonnet-5Medium level, step 1",
    ]);

    const form = container.querySelector('form[aria-label="Pin a model for this agent"]') as HTMLFormElement;
    const select = form.querySelector('select[name="model_pin"]') as HTMLSelectElement;
    expect([...select.options].map((one) => one.textContent)).toEqual([CHOOSE_A_MODEL, "Anthropic (Claude): claude-sonnet-5"]);
    fireEvent.submit(form);
    expect(container.textContent).toContain("Choose the model to pin.");
    expect(container.querySelector(".confirm")).toBeNull();

    fireEvent.change(select, { target: { value: "0" } });
    fireEvent.submit(form);
    expect(writes(idp)).toEqual([]);
    const confirm = [...container.querySelectorAll(".confirm button")].filter((one) => one.textContent === PIN_MODEL);
    fireEvent.click(confirm[0] as HTMLElement);
    await waitFor(() => {
      if (writes(idp).length === 0) {
        throw new Error("nothing sent");
      }
    });

    expect(writes(idp)).toEqual([{ method: "PUT", body: { provider: "anthropic", model: "claude-sonnet-5" } }]);
    await waitFor(() => {
      expect(container.textContent).toContain("Anthropic (Claude) claude-sonnet-5 is pinned: it is tried first");
    });
    const after = [...container.querySelectorAll("table")].find((one) => one.querySelector("caption")?.textContent === STEPS_CAPTION);
    expect([...(after?.querySelectorAll("tbody tr") ?? [])].map((row) => row.textContent)).toEqual([
      `1Anthropic (Claude)claude-sonnet-5${PINNED_ROLE}`,
    ]);
  });

  test("the pin is step 1, the level's steps in use follow by position without the pinned pair, and a pin nothing serves is said to be passed over", () => {
    // What breaks if this is deleted: the profile drawing an order the executor does not walk, with
    // the pinned model shown twice, a paused step shown as tried, or a pin no step serves drawn as
    // the model every question tries first.
    const step = (id: string, tier: string, position: number, provider: string, model: string, enabled = true) =>
      ({ id, tier, position, provider, model, enabled }) as RungRow;
    const matrix = [
      step("m2", "main", 2, "moonshot", "kimi-k3"),
      step("m0", "main", 0, "anthropic", "claude-sonnet-5"),
      step("m1", "main", 1, "anthropic", "claude-opus-5"),
      step("m3", "main", 3, "openai", "gpt-5", false),
      step("h0", "heavy", 0, "anthropic", "claude-opus-5"),
    ];

    const pinned = agentSteps({ tier: "main", provider: "anthropic", model: "claude-opus-5" }, matrix);
    expect(pinned.map((one) => [one.step, one.model, one.role, one.note])).toEqual([
      [1, "claude-opus-5", PINNED_ROLE, null],
      [2, "claude-sonnet-5", "Medium level, step 1", null],
      [3, "kimi-k3", "Medium level, step 2", null],
    ]);
    const unserved = agentSteps({ tier: "main", provider: "openai", model: "gpt-5" }, matrix);
    expect(unserved[0]?.note).toBe(PASSED_OVER);
    expect(agentSteps({ tier: "main", provider: null, model: null }, matrix).map((one) => one.model)).toEqual([
      "claude-sonnet-5",
      "claude-opus-5",
      "kimi-k3",
    ]);
    expect(pinChoices(matrix, ["small", "main", "heavy"]).map((one) => one.label)).toEqual([
      "Anthropic (Claude): claude-sonnet-5",
      "Anthropic (Claude): claude-opus-5",
      "Moonshot (Kimi): kimi-k3",
    ]);
  });
});
