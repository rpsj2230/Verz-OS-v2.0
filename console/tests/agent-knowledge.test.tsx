/**
 * One agent's Knowledge section: reachable from its Sections menu at its own address, listing the
 * documents the agent draws on with who added them, when and whether they are verified or due, a
 * longer list asked for page by page, and an empty state that says what the section is for.
 *
 * **Mounted through the application's own route table** and answered by a stand-in API that
 * records every request, as `agent-artifacts.test.tsx` mounts the Artifacts section.
 *
 * Task ids: M39.9.1.1, M39.9.1.6
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { EMPTY_TITLE, NOTHING_YOURS_TO_SEE, SHOW_MORE } from "../src/pages/agents/AgentKnowledge";
import { agentKnowledgeApiPath, readAgentKnowledge } from "../src/pages/agents/agentKnowledgeQuery";
import { KNOWLEDGE_TAB, viewAddress } from "../src/pages/agents/AgentDetailPage";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { installRadixStubs } from "./support/radix";

const CONSOLE_ORIGIN = "https://console.test";
const AGENT = "quote-helper";
const ADDRESS = viewAddress(AGENT, KNOWLEDGE_TAB);

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/Agent");
}, 60_000);

function workspaceWire(): unknown {
  return {
    agent: { agent_id: AGENT, display_name: "Quote Helper", owner_id: "p_steward", created_at: "2019-03-01T09:00:00Z" },
    tabs: ["knowledge", "settings"].map((tab) => ({ tab, label: tab, purpose: "x" })),
    composition: [],
    skills: [],
    connectors: { shown: [], overflow: 0 },
    channels: [],
    headline: { basis: "own", range: "30d", spend_minor: 0, runs: 0, recorded: false },
  };
}

function item(itemId: string, extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    item_id: itemId,
    title: `Title of ${itemId}`,
    kind: "sop",
    kind_label: "SOP",
    place: "web",
    level: "department",
    added_by: "p_steward",
    added_by_name: "Sam Steward",
    added_at: "2019-03-04T09:00:00Z",
    verification: "verified",
    verified_by_name: "Vera Verifier",
    verified_at: "2019-03-05T09:00:00Z",
    review_by: "2999-01-01T00:00:00Z",
    due: false,
    reached: true,
    ...extra,
  };
}

function knowledgeWire(extra: Record<string, unknown> = {}): unknown {
  return {
    agent_id: AGENT,
    items: [item("one"), item("two", { verification: "due", due: true, verified_by_name: null })],
    rule: [{ field: "department", op: "eq", value: "web" }],
    can_add: true,
    more: false,
    at_least: false,
    unread: "",
    kept_rule: "An item shown here is one of the company's documents, read at your own reach.",
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
      const where = new URL(url, CONSOLE_ORIGIN);
      const answer = answers[`${method} ${where.pathname}${where.search}`] ?? answers[`${method} ${where.pathname}`] ?? (method === "GET" ? answers[where.pathname] : undefined);
      if (answer === undefined) {
        return null;
      }
      return new Response(JSON.stringify(answer.body), { status: answer.status ?? 200, headers: { "content-type": "application/json" } });
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [ADDRESS] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(
    () => {
      if (!container.querySelector('[data-slot="agent-knowledge"] [data-slot="knowledge-list"], [data-slot="agent-knowledge"] [data-slot="knowledge-empty"], [data-slot="agent-knowledge"] [data-slot="note"]')) {
        throw new Error("the Knowledge section has not arrived");
      }
    },
    { timeout: 10_000 },
  );
  return { container, idp };
}

function answers(knowledge: unknown = knowledgeWire(), extra: Readonly<Record<string, Answer>> = {}): Record<string, Answer> {
  return {
    [`/api/v1/agents/${AGENT}/workspace`]: { body: workspaceWire() },
    [`GET /api/v1${agentKnowledgeApiPath(AGENT, 0)}`]: { body: knowledge },
    ...extra,
  };
}

function rows(container: HTMLElement): Element[] {
  return [...container.querySelectorAll('[data-slot="knowledge-item"]')];
}

describe("the Knowledge section", () => {
  test("it lists each document with its kind, where it sits, who added it, its badge and the rule it is the answer to", async () => {
    // What breaks if this is deleted: M39.9.1.1's list reaching the page without who added a
    // document, when, or whether it is verified or due for review.
    const { container } = await consoleAt(answers());
    const first = rows(container)[0]?.textContent ?? "";
    expect(first).toContain("Title of one");
    expect(first).toContain("SOP");
    expect(first).toContain("in web");
    expect(first).toContain("added by Sam Steward");
    expect(first).toContain("Verified by Vera Verifier");
    expect(rows(container)[1]?.textContent).toContain("Due for review");
    expect(rows(container)[0]?.querySelector("a")?.getAttribute("href")).toBe("/library/one");
    expect(container.querySelector('[data-slot="knowledge-rule"]')?.textContent).toContain("department");
    expect(container.textContent).toContain("one of the company's documents");
  });

  test("an empty list says what the section is for and offers both ways to add to a reader who may add", async () => {
    // What breaks if this is deleted: M39.9.1.1's empty state, the words that tell a person this is
    // where context for the agent is added.
    const { container } = await consoleAt(answers(knowledgeWire({ items: [] })));
    expect(container.querySelector('[data-slot="knowledge-empty"]')?.textContent).toContain(EMPTY_TITLE);
    const links = [...container.querySelectorAll('[data-slot="knowledge-empty"] a')].map((one) => one.textContent);
    expect(links).toEqual(["Add a file", "Add a web page by its link"]);
  });

  test("an empty list for a reader who may not add offers nothing to add and claims nothing about what exists", async () => {
    // What breaks if this is deleted: M39.9.1.6's sibling, an add offered to a reader the API said
    // may not, or an empty list that says how many documents are out of sight.
    const { container } = await consoleAt(answers(knowledgeWire({ items: [], can_add: false })));
    expect(container.textContent).toContain(NOTHING_YOURS_TO_SEE);
    expect(container.querySelectorAll('[data-slot="knowledge-empty"]').length).toBe(0);
    expect(container.textContent).not.toMatch(/\bof \d+\b|hidden|more than you/i);
  });

  test("a longer list is the next page asked for, appended, and never a count", async () => {
    // What breaks if this is deleted: the list stuck at its first page, or a page that is full
    // drawn with a total beside it.
    const next = agentKnowledgeApiPath(AGENT, 2);
    const { container, idp } = await consoleAt(
      answers(knowledgeWire({ more: true }), { [`GET /api/v1${next}`]: { body: knowledgeWire({ items: [item("three")], more: false }) } }),
    );
    expect(rows(container).length).toBe(2);
    const button = [...container.querySelectorAll("button")].find((one) => one.textContent === SHOW_MORE) as Element;
    await act(async () => {
      fireEvent.click(button);
    });
    await waitFor(() => {
      expect(rows(container).length).toBe(3);
    });
    expect(idp.calls.some((one) => one.url.endsWith(next))).toBe(true);
    expect([...container.querySelectorAll("button")].some((one) => one.textContent === SHOW_MORE)).toBe(false);
  });

  test("the strip offers Knowledge and the section answers a sentence when the API could not say", async () => {
    // What breaks if this is deleted: a reader of an agent whose rule is not about where documents
    // sit being shown an empty add prompt instead of the API's own sentence.
    const { container } = await consoleAt(answers(knowledgeWire({ items: [], unread: "This agent's rule is not about where documents sit." })));
    expect(container.textContent).toContain("not about where documents sit");
    expect(container.querySelectorAll('[data-slot="knowledge-empty"]').length).toBe(0);
  });

  test("a body that is not an object reads as no section, and an item with no title is left out", () => {
    // What breaks if this is deleted: a malformed answer drawn as a blank row.
    expect(readAgentKnowledge("nope")).toBeNull();
    const read = readAgentKnowledge({ items: [{ item_id: "x" }, item("y")], rule: [{ field: "department" }] });
    expect(read?.items.map((one) => one.itemId)).toEqual(["y"]);
    expect(read?.rule).toEqual([]);
  });
});
