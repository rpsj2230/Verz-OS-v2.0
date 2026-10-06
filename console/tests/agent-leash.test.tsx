/**
 * An agent's leash block on its Profile: the change form offered only to a holder of the leash role,
 * every change confirmed before it is sent, the history with its evidence and the breaker's metric,
 * supervision and its review, and the actions waiting for a verdict.
 *
 * **Mounted through the application's own route table** and answered by a stand-in API that records
 * every request, as `agent-memory.test.tsx` mounts the Memory section.
 *
 * Task ids: M39.3.2.1, M39.3.2.2, M39.3.2.3, M39.3.2.4, M39.3.2.5, M39.8.2
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { NO_MOVES } from "../src/pages/agents/AgentLeash";
import { agentLeashApiPath, leashMoveApiPath, readAgentLeash, supervisionApiPath } from "../src/pages/agents/agentLeashQuery";
import { viewAddress } from "../src/pages/agents/AgentDetailPage";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { apiDocument } from "./support/openapi";
import { installRadixStubs } from "./support/radix";

const CONSOLE_ORIGIN = "https://console.test";
const AGENT = "quote-helper";
const ADDRESS = viewAddress(AGENT, "profile");
const DIGEST = "d".repeat(64);

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/Agent");
}, 60_000);

function workspaceWire(): unknown {
  return {
    agent: { agent_id: AGENT, display_name: "Quote Helper", owner_id: "p_steward", created_at: "2019-03-01T09:00:00Z" },
    tabs: [{ tab: "settings", label: "settings", purpose: "x" }],
    composition: [],
    skills: [],
    connectors: { shown: [], overflow: 0 },
    channels: [],
    headline: { basis: "own", range: "30d", spend_minor: 0, runs: 0, recorded: false },
    profile: {
      tier: "main",
      tools: [{ name: "quote.send", description: "Send a quote", acts: true }],
      leash: [{ target: "quote.send", rung: "assisted", configured: true, acts: true }],
    },
  };
}

function leashWire(extra: Record<string, unknown> = {}): unknown {
  return {
    agent_id: AGENT,
    entries: [{ target: "quote.send", scope: { clauses: [] }, where: "", rung: "assisted", proposed: "autonomous" }],
    history: [
      {
        target: "quote.send",
        where: "",
        kind: "raised",
        was: "shadow",
        became: "assisted",
        at: "2019-03-04T09:00:00Z",
        approver: "Ada Admin",
        second_approver: "",
        clean_runs: 10,
        agreement_rate: 1,
        metric: "",
        measured: null,
        threshold: null,
      },
      {
        target: "invoice.pay",
        where: "",
        kind: "tripped",
        was: "assisted",
        became: "shadow",
        at: "2019-03-05T09:00:00Z",
        approver: "",
        second_approver: "",
        clean_runs: null,
        agreement_rate: null,
        metric: "share of its actions a person accepted unchanged",
        measured: 0.5,
        threshold: 0.9,
      },
    ],
    supervision: {
      pinned_at: "2019-02-01T09:00:00Z",
      review_due_at: "2019-03-03T09:00:00Z",
      outcome: "pinned",
      understood: null,
      reviewed: null,
      simulated: null,
      held: true,
      due: true,
    },
    awaiting: [{ action_digest: DIGEST, target: "quote.send", route: "simulate", at: "2019-03-06T09:00:00Z" }],
    may_move: true,
    may_judge: true,
    ...extra,
  };
}

interface Answer {
  readonly status?: number;
  readonly body: unknown;
}

async function consoleAt(answers: Readonly<Record<string, Answer>>): Promise<{ container: HTMLElement; idp: FakeIdp }> {
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
  const router = createMemoryRouter(routes, { initialEntries: [ADDRESS] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(
    () => {
      if (!container.querySelector('[data-slot="agent-leash"]')) {
        throw new Error("the leash block has not arrived");
      }
    },
    { timeout: 10_000 },
  );
  return { container, idp };
}

function answers(leash: unknown = leashWire(), extra: Readonly<Record<string, Answer>> = {}): Record<string, Answer> {
  return {
    [`/api/v1/agents/${AGENT}/workspace`]: { body: workspaceWire() },
    [`/api/v1${agentLeashApiPath(AGENT)}`]: { body: leash },
    ...extra,
  };
}

function posts(idp: FakeIdp): FakeIdp["calls"] {
  return idp.calls.filter((one) => one.init?.method === "POST" && one.url.includes("/api/v1/"));
}

async function confirm(label: string): Promise<Element> {
  const dialog = await waitFor(() => {
    const found = document.querySelector('[role="alertdialog"]');
    if (found === null) {
      throw new Error("no confirmation opened");
    }
    return found;
  });
  if (label !== "") {
    await act(async () => {
      fireEvent.click([...dialog.querySelectorAll("button")].find((one) => one.textContent === label) as Element);
    });
  }
  return dialog;
}

describe("the leash block", () => {
  test("a rung is changed from the form only through its confirmation, which says a rise is judged", async () => {
    // What breaks if this is deleted: M39.3.2.2's rise sent without asking, or the dialog not saying
    // that a rise is judged on the agent's record and a money action needs a second person.
    const { container, idp } = await consoleAt({
      ...answers(),
      [`POST /api/v1${leashMoveApiPath(AGENT)}`]: { body: { target: "quote.send", kind: "proposed", was: "assisted", became: "autonomous" } },
    });
    const form = container.querySelector('[data-slot="leash-change"]') as HTMLFormElement;
    const [, rung] = [...form.querySelectorAll("select")];
    await act(async () => {
      fireEvent.change(rung as Element, { target: { value: "autonomous" } });
      fireEvent.submit(form);
    });
    expect(posts(idp)).toEqual([]);
    const dialog = await confirm("");
    expect(dialog.textContent).toContain("needs a second person");
    await confirm("Change");
    const [sent] = posts(idp);
    expect(sent?.url).toContain(leashMoveApiPath(AGENT));
    expect(JSON.parse(String(sent?.init?.body))).toEqual({ target: "quote.send", scope: { clauses: [] }, to: "autonomous" });
  });

  test("the history shows each move with its evidence, and a trip with its metric", async () => {
    // What breaks if this is deleted: M39.3.2.5's history reduced to dates, or M39.3.2.3's breaker
    // shown without the figure that tripped it.
    const { container } = await consoleAt(answers());
    const history = container.querySelector('[data-slot="leash-history"]')?.textContent ?? "";
    expect(history).toContain("10 actions in a row accepted unchanged, 100% overall; approved by Ada Admin");
    expect(history).toContain("share of its actions a person accepted unchanged was 50%, below 90%");
    expect(container.querySelector('[data-slot="leash-proposal"]')?.textContent).toContain("waiting for a second person");
  });

  test("a takeover demotion shows in the history and in the setting it holds lower, naming nobody", async () => {
    // What breaks if this is deleted: the lower rung that binds hidden behind a raise that reads as
    // having taken effect, or the takeover demotion missing from the history beside the moves.
    const demotion = {
      target: "quote.send",
      where: "",
      kind: "taken_over",
      was: "assisted",
      became: "shadow",
      at: "2019-03-05T12:00:00Z",
      approver: "",
      second_approver: "",
      clean_runs: null,
      agreement_rate: null,
      metric: "",
      measured: null,
      threshold: 3,
      takeovers: 4,
    };
    const base = leashWire() as { history: unknown[] };
    const { container } = await consoleAt(
      answers(
        leashWire({
          entries: [{ target: "quote.send", scope: { clauses: [] }, where: "", rung: "assisted", lowered_to: "shadow" }],
          history: [...base.history, demotion],
        }),
      ),
    );
    const history = container.querySelector('[data-slot="leash-history"]')?.textContent ?? "";
    expect(history).toContain("Held a step lower because people kept doing its work themselves: quote.send from Assisted to Shadow");
    expect(history).toContain("People did its work themselves 4 times in the last week. It comes back up once fewer than 3 of those are inside the week.");
    expect(history).toContain("approved by Ada Admin");
    const form = container.querySelector('[data-slot="leash-change"]') as HTMLFormElement;
    expect(form.textContent).toContain("quote.send (Assisted, held at Shadow for now)");
  });

  test("supervision is shown with its review, and a due review is pressed through its confirmation", async () => {
    // What breaks if this is deleted: M39.8.2's pin invisible, or a review sent without asking.
    const { container, idp } = await consoleAt({
      ...answers(),
      [`POST /api/v1${supervisionApiPath(AGENT, "review")}`]: { body: { outcome: "extended", review_due_at: "2019-04-05T09:00:00Z" } },
    });
    const block = container.querySelector('[data-slot="leash-supervision"]') as Element;
    expect(block.textContent).toContain("only practises until a review finds it ready");
    await act(async () => {
      fireEvent.click([...block.querySelectorAll("button")].find((one) => one.textContent === "Review it now") as Element);
    });
    expect(posts(idp)).toEqual([]);
    await confirm("Review");
    expect(posts(idp)[0]?.url).toContain(supervisionApiPath(AGENT, "review"));
  });

  test("a verdict is recorded from its confirmation, which says it can put a setting back", async () => {
    // What breaks if this is deleted: a verdict sent without asking, or the dialog hiding that a
    // verdict below the bar trips the rung.
    const { container, idp } = await consoleAt({
      ...answers(),
      [`POST /api/v1${supervisionApiPath(AGENT, "verdicts")}`]: { body: { action_digest: DIGEST, tripped: [] } },
    });
    const row = container.querySelector('[data-slot="leash-awaiting"]') as Element;
    await act(async () => {
      fireEvent.change(row.querySelector("select") as Element, { target: { value: "rejected" } });
      fireEvent.submit(row.querySelector("form") as Element);
    });
    const dialog = await confirm("");
    expect(dialog.textContent).toContain("back to Shadow");
    await confirm("Record");
    expect(JSON.parse(String(posts(idp)[0]?.init?.body))).toEqual({ action_digest: DIGEST, verdict: "rejected" });
  });

  test("a reader without the leash role is offered no change, and an agent never moved says so", async () => {
    // The siblings: the controls are the route's answer, not the page's guess, and an empty history
    // is one sentence.
    const { container } = await consoleAt(answers(leashWire({ may_move: false, may_judge: false, history: [], awaiting: [], supervision: null })));
    expect(container.querySelector('[data-slot="leash-change"]')).toBeNull();
    expect(container.querySelector('[data-slot="leash-awaiting"]')).toBeNull();
    expect(container.textContent).toContain(NO_MOVES);
  });

  test("the routes the block asks are declared, and a half-sent move is left out", () => {
    // What breaks if this is deleted: a path spelled differently from the route, or a blank row.
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    expect(paths).toEqual(
      expect.arrayContaining([
        "/api/v1/agents/{agent_id}/leash",
        "/api/v1/agents/{agent_id}/leash/moves",
        "/api/v1/agents/{agent_id}/supervision/pin",
        "/api/v1/agents/{agent_id}/supervision/review",
        "/api/v1/agents/{agent_id}/supervision/verdicts",
      ]),
    );
    const read = readAgentLeash({ history: [{ target: "x" }], supervision: null });
    expect(read?.history).toEqual([]);
    const plain = readAgentLeash({ entries: [{ target: "x", scope: { clauses: [] }, rung: "assisted", lowered_to: null }] });
    expect(plain?.entries[0]?.loweredTo).toBeUndefined();
    expect(read?.supervision).toBeUndefined();
  });
});
