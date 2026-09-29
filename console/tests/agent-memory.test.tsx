/**
 * One agent's Memory section: reachable from its Sections menu at its own address, drawing what it
 * remembers as text, stated apart from inferred, what it keeps about the reader, every change with
 * its diff, and how it learns, with the corrections and deletes the API offered, each confirmed.
 *
 * **Mounted through the application's own route table** and answered by a stand-in API that records
 * every request, as `agent-page.test.tsx` mounts it.
 *
 * Task ids: M39.4.1.1, M39.4.1.2, M39.4.1.3, M39.4.1.4, M39.4.1.5, M39.4.2.1, M39.4.2.2, M39.4.2.4
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { ABOUT_YOU_HEADING, CORRECTION_FORMAT, CORRECTION_NEEDED, NOTHING_REMEMBERED } from "../src/pages/agents/AgentMemory";
import { agentMemoryApiPath, memoryDeletionApiPath, memoryEditApiPath, readAgentMemory } from "../src/pages/agents/agentMemoryQuery";
import { MEMORY_TAB, viewAddress } from "../src/pages/agents/AgentDetailPage";
import { UNDO_API_PATH } from "../src/pages/learningQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { apiDocument } from "./support/openapi";
import { installRadixStubs } from "./support/radix";

const CONSOLE_ORIGIN = "https://console.test";
const AGENT = "quote-helper";
const ADDRESS = viewAddress(AGENT, MEMORY_TAB);

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/Agent");
}, 60_000);

function workspaceWire(): unknown {
  return {
    agent: { agent_id: AGENT, display_name: "Quote Helper", owner_id: "p_steward", created_at: "2019-03-01T09:00:00Z" },
    tabs: ["memory", "settings"].map((tab) => ({ tab, label: tab, purpose: "x" })),
    composition: [],
    skills: [],
    connectors: { shown: [], overflow: 0 },
    channels: [],
    headline: { basis: "own", range: "30d", spend_minor: 0, runs: 0, recorded: false },
  };
}

function item(memoryId: string, statement: string, extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    memory_id: memoryId,
    statement,
    confidence: 0.9,
    formed_at: "2019-03-04T09:00:00Z",
    provenance: "curated",
    about_you: false,
    changeable: true,
    ...extra,
  };
}

function memoryWire(extra: Record<string, unknown> = {}): unknown {
  return {
    agent_id: AGENT,
    curated: [item("m1", "Invoices go to the accounts inbox")],
    extracted: [item("m2", "Prefers short answers", { provenance: "extracted", confidence: 0.6, changeable: false })],
    about_you: [item("m3", "You work on Fridays", { about_you: true })],
    history: [
      {
        memory_id: "m1",
        replaced_id: "m0",
        at: "2019-03-05T09:00:00Z",
        diff: ["-Invoices go to the finance inbox", "+Invoices go to the accounts inbox"],
        trigger: "rejected",
        correction: "superseded",
      },
    ],
    active_tiers: [0, 1, 2],
    tier_one: [{ memory_id: "m1", change: "preference", control_writes: "superseded", learned_at: "2019-03-05T09:00:00Z", in_effect: true, undo_offered: true }],
    tier_two: [{ memory_id: "m4", change: "procedure", evidence: ["reasked"], promote_ready: false, learned_at: "2019-03-05T09:00:00Z" }],
    tier_three: [{ memory_id: "m5", department: "sales", back_to: `agent:${AGENT}/learning` }],
    ...extra,
  };
}

interface Answer {
  readonly status?: number;
  readonly body: unknown;
}

async function consoleAt(path: string, answers: Readonly<Record<string, Answer>>): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      const method = init?.method ?? "GET";
      const pathname = new URL(url, CONSOLE_ORIGIN).pathname;
      const answer = answers[`${method} ${pathname}`] ?? (method === "GET" ? answers[pathname] : undefined);
      return answer === undefined
        ? null
        : new Response(JSON.stringify(answer.body), { status: answer.status ?? 200, headers: { "content-type": "application/json" } });
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector('[data-slot="agent-memory"]')) {
      throw new Error("the Memory section has not arrived");
    }
  });
  return { container, idp };
}

function answers(memory: unknown = memoryWire(), extra: Readonly<Record<string, Answer>> = {}): Record<string, Answer> {
  return {
    [`/api/v1/agents/${AGENT}/workspace`]: { body: workspaceWire() },
    [`/api/v1${agentMemoryApiPath(AGENT)}`]: { body: memory },
    ...extra,
  };
}

function posts(idp: FakeIdp): FakeIdp["calls"] {
  return idp.calls.filter((one) => one.init?.method === "POST" && one.url.includes("/api/v1/"));
}

async function confirm(label: string): Promise<void> {
  const dialog = await waitFor(() => {
    const found = document.querySelector('[role="alertdialog"]');
    if (found === null) {
      throw new Error("no confirmation opened");
    }
    return found;
  });
  await act(async () => {
    fireEvent.click([...dialog.querySelectorAll("button")].find((one) => one.textContent === label) as Element);
  });
}

describe("the Memory section", () => {
  test("it draws what is remembered as text, stated apart from inferred, apart from what it keeps about you", async () => {
    // What breaks if this is deleted: M39.4.1.1's text, M39.4.1.2's split and M39.4.1.5's separation
    // reaching the page merged, or not at all.
    const { container } = await consoleAt(ADDRESS, answers());
    expect(container.querySelector('[data-slot="memory-curated"]')?.textContent).toContain("Invoices go to the accounts inbox");
    expect(container.querySelector('[data-slot="memory-extracted"]')?.textContent).toContain("Prefers short answers");
    const aboutYou = container.querySelector('[data-slot="memory-about-you"]')?.textContent ?? "";
    expect(aboutYou).toContain("You work on Fridays");
    expect(aboutYou).not.toContain("Invoices");
    expect(container.textContent).toContain(ABOUT_YOU_HEADING);
  });

  test("every change is drawn with its diff and what caused it", async () => {
    // What breaks if this is deleted: M39.4.1.3's history reduced to a date.
    const { container } = await consoleAt(ADDRESS, answers());
    const history = container.querySelector('[data-slot="memory-history"]')?.textContent ?? "";
    expect(history).toContain("Replaced an earlier memory");
    expect(history).toContain("because it was rejected");
    expect(history).toContain("-Invoices go to the finance inbox");
    expect(history).toContain("+Invoices go to the accounts inbox");
  });

  test("a correction says its format, refuses a blank, and is sent only from its confirmation", async () => {
    // What breaks if this is deleted: M39.4.1.4's correction sent blank or without asking.
    const { container, idp } = await consoleAt(ADDRESS, { ...answers(), [`POST /api/v1${memoryEditApiPath(AGENT, "m1")}`]: { body: { memory_id: "m1", took_effect: true, told: "x" } } });
    const row = container.querySelector('[data-slot="memory-curated"] [data-slot="memory-item"]') as Element;
    await act(async () => {
      fireEvent.click([...row.querySelectorAll("button")].find((one) => one.textContent === "Correct") as Element);
    });
    expect(row.textContent).toContain(CORRECTION_FORMAT);
    const form = row.querySelector("form") as HTMLFormElement;
    await act(async () => {
      fireEvent.change(form.querySelector("textarea") as Element, { target: { value: "  " } });
      fireEvent.submit(form);
    });
    expect(form.querySelector('[role="alert"]')?.textContent).toBe(CORRECTION_NEEDED);
    await act(async () => {
      fireEvent.change(form.querySelector("textarea") as Element, { target: { value: "Invoices go to the billing inbox" } });
      fireEvent.submit(form);
    });
    expect(posts(idp)).toEqual([]);
    await confirm("Save correction");
    const [sent] = posts(idp);
    expect(sent?.url).toContain(memoryEditApiPath(AGENT, "m1"));
    expect(JSON.parse(String(sent?.init?.body))).toEqual({ statement: "Invoices go to the billing inbox" });
  });

  test("a delete is offered only where the API said so and is sent from its confirmation", async () => {
    // What breaks if this is deleted: a delete on a memory the reader may not change, or one sent
    // without asking.
    const { container, idp } = await consoleAt(ADDRESS, { ...answers(), [`POST /api/v1${memoryDeletionApiPath(AGENT, "m3")}`]: { body: { memory_id: "m3", took_effect: true, told: "x" } } });
    const inferred = container.querySelector('[data-slot="memory-extracted"] [data-slot="memory-item"]') as Element;
    expect([...inferred.querySelectorAll("button")].map((one) => one.textContent)).toEqual([]);
    const mine = container.querySelector('[data-slot="memory-about-you"] [data-slot="memory-item"]') as Element;
    await act(async () => {
      fireEvent.click([...mine.querySelectorAll("button")].find((one) => one.textContent === "Delete") as Element);
    });
    await confirm("Delete");
    expect(posts(idp)[0]?.url).toContain(memoryDeletionApiPath(AGENT, "m3"));
  });

  test("the tiers say which are active, offer the undo where the API did, and send a gated change to its department", async () => {
    // What breaks if this is deleted: M39.4.2.1's active tiers, M39.4.2.2's one-click undo and
    // M39.4.2.4's routing never drawn.
    const { container, idp } = await consoleAt(ADDRESS, { ...answers(), [`POST /api/v1${UNDO_API_PATH}`]: { body: { memory_id: "m1", took_effect: true, correction: "superseded", at: null, told: "x" } } });
    const tiers = [...container.querySelectorAll('[data-slot="learning-tiers"] li')].map((one) => one.textContent ?? "");
    expect(tiers.map((one) => one.endsWith("Active"))).toEqual([true, true, true, false]);
    expect(container.querySelector('[data-slot="tier-three"]')?.textContent).toContain("In the sales department's review");
    const undo = [...(container.querySelector('[data-slot="tier-one"]')?.querySelectorAll("button") ?? [])].find((one) => one.textContent === "Undo") as Element;
    await act(async () => {
      fireEvent.click(undo);
    });
    await confirm("Undo");
    const [sent] = posts(idp);
    expect(sent?.url).toContain(UNDO_API_PATH);
    expect(JSON.parse(String(sent?.init?.body))).toEqual({ memory_id: "m1" });
  });

  test("an agent that remembers nothing says so, and a reader not sent tier three is shown none", async () => {
    // The siblings: empty lists read as one sentence, and null tier three draws nothing.
    const empty = memoryWire({ curated: [], extracted: [], about_you: [], history: [], tier_one: [], tier_two: [], tier_three: null });
    const { container } = await consoleAt(ADDRESS, answers(empty));
    expect(container.querySelector('[data-slot="memory-curated"]')?.textContent).toContain(NOTHING_REMEMBERED);
    expect(container.querySelector('[data-slot="tier-three"]')).toBeNull();
  });

  test("the routes the section asks are declared, and a half-sent memory is left out", () => {
    // What breaks if this is deleted: a path spelled differently from the route, or a blank row.
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    expect(paths).toEqual(
      expect.arrayContaining([
        "/api/v1/agents/{agent_id}/memory",
        "/api/v1/agents/{agent_id}/memory/{memory_id}/deletion",
        "/api/v1/agents/{agent_id}/memory/{memory_id}/edit",
      ]),
    );
    const read = readAgentMemory({ curated: [{ memory_id: "m1" }, item("m2", "kept")], tier_three: null });
    expect(read?.curated.map((one) => one.memoryId)).toEqual(["m2"]);
    expect(read?.tierThree).toBeUndefined();
  });
});
