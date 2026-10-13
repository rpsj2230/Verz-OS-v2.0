/**
 * One agent's Knowledge section: reachable from its Sections menu at its own address, listing the
 * documents the agent draws on with who added them, when and whether they are verified or due, a
 * longer list asked for page by page, and an empty state that says what the section is for.
 *
 * **Mounted through the application's own route table** and answered by a stand-in API that
 * records every request, as `agent-artifacts.test.tsx` mounts the Artifacts section.
 *
 * Task ids: M39.2.3.5, M39.9.1.5, M39.9.1.1, M39.9.1.2, M39.9.1.3, M39.9.1.4, M39.9.1.6
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { DOES_NOT_MATCH, EMPTY_TITLE, NOTHING_YOURS_TO_SEE, SHOW_MORE, WIDEN_THROUGH_A_DRAFT } from "../src/pages/agents/AgentKnowledge";
import {
  agentKnowledgeApiPath,
  agentKnowledgeLinkApiPath,
  agentKnowledgeRefetchApiPath,
  agentKnowledgeRetireApiPath,
  agentKnowledgeUploadApiPath,
  readAgentKnowledge,
  readKnowledgeAdded,
} from "../src/pages/agents/agentKnowledgeQuery";
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
    skills: [{ name: "ssl-renewal-runbook", digest: "a".repeat(64) }],
    connectors: { shown: [{ source: "ledger", presence: "attached" }, { source: "pricing", presence: "requested" }], overflow: 2 },
    channels: [],
    headline: { basis: "own", range: "30d", spend_minor: 0, runs: 0, recorded: false },
  };
}

const OPTIONS = {
  kinds: [{ value: "sop", label: "SOP" }],
  departments: ["web"],
  personal: false,
  types: [{ media_type: "text/markdown", extensions: [".md", ".markdown"], max_bytes: 5 * 1024 * 1024 }],
  found_by: "text search",
  checked_by: "structural check",
  offered_as_tables: [".csv", ".xlsx"],
};

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
    add_into: "web",
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
    "GET /api/v1/knowledge/uploads/options": { body: OPTIONS },
    ...extra,
  };
}

function addedWire(extra: Record<string, unknown> = {}): unknown {
  return {
    item_id: "fresh",
    title: "Handover",
    kind: "sop",
    level: "department",
    department: "web",
    passages: 1,
    found_by: "text search",
    route: "link",
    reached: true,
    said: "Added. This agent draws on it now.",
    blocking: [],
    can_widen: false,
    ...extra,
  };
}

function posts(idp: FakeIdp): { url: string; init: RequestInit }[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST" && call.url.includes("/api/v1/"))
    .map((call) => ({ url: call.url, init: call.init as RequestInit }));
}

function change(container: HTMLElement, name: string, value: string): void {
  const field = container.querySelector(`[name="${name}"]`);
  if (field === null) {
    throw new Error(`no ${name} field`);
  }
  fireEvent.change(field, { target: { value } });
}

async function openWay(container: HTMLElement, label: string): Promise<void> {
  const button = await waitFor(() => {
    const found = [...container.querySelectorAll("button")].find((one) => one.textContent === label);
    if (found === undefined) {
      throw new Error(`no ${label} button`);
    }
    return found;
  });
  await act(async () => {
    fireEvent.click(button);
  });
}

function rows(container: HTMLElement): Element[] {
  return [...container.querySelectorAll('[data-slot="knowledge-item"]')];
}

describe("adding from the Knowledge section", () => {
  test("a web page is sent to the agent's own address with the rule's department already chosen, and the answer says the agent draws on it", async () => {
    // What breaks if this is deleted: M39.9.1.3's link added from the agent's page, or told nothing
    // about whether the agent will use it.
    const { container, idp } = await consoleAt(
      answers(knowledgeWire(), { [`POST /api/v1${agentKnowledgeLinkApiPath(AGENT)}`]: { status: 201, body: addedWire() } }),
    );
    await openWay(container, "Add a web page by its link");
    expect((container.querySelector('[name="department"]') as HTMLSelectElement).value).toBe("web");
    change(container, "url", "https://example.test/pricing");
    change(container, "kind", "sop");
    await act(async () => {
      fireEvent.submit(container.querySelector("form") as HTMLFormElement);
    });
    await waitFor(() => {
      expect(container.querySelector('[data-slot="knowledge-added"]')?.textContent).toContain("This agent draws on it now.");
    });
    const [sent] = posts(idp);
    expect(sent?.url.endsWith(agentKnowledgeLinkApiPath(AGENT))).toBe(true);
    expect(JSON.parse(String(sent?.init.body))).toMatchObject({ url: "https://example.test/pricing", department: "web", level: "department" });
    expect(container.querySelector('[data-slot="knowledge-blocking"]')).toBeNull();
  });

  test("a file is sent raw to the agent's own address, and an item outside the rule says why and offers the draft", async () => {
    // What breaks if this is deleted: M39.9.1.2's upload from the agent's page and M39.9.1.4's one
    // next step: an unreached item reported as drawn on, or widened for every agent silently.
    const target = agentKnowledgeUploadApiPath(AGENT, "sop", "department", "web");
    const blocked = addedWire({
      route: "upload",
      reached: false,
      said: "Added to the company's documents, but this agent does not draw on it.",
      blocking: [{ field: "department", op: "eq", value: "finance" }],
      can_widen: true,
    });
    const { container, idp } = await consoleAt(answers(knowledgeWire(), { [`POST /api/v1${target}`]: { status: 201, body: blocked } }));
    await openWay(container, "Add a file");
    const file = new File(["# Notes"], "Notes.md", { type: "" });
    fireEvent.change(container.querySelector('input[type="file"]') as HTMLInputElement, { target: { files: [file] } });
    change(container, "kind", "sop");
    await act(async () => {
      fireEvent.submit(container.querySelector("form") as HTMLFormElement);
    });
    await waitFor(() => {
      expect(container.querySelector('[data-slot="knowledge-blocking"]')?.textContent).toContain(DOES_NOT_MATCH);
    });
    expect(container.querySelector('[data-slot="knowledge-blocking"]')?.textContent).toContain("finance");
    const [sent] = posts(idp);
    expect(sent?.url.endsWith(target)).toBe(true);
    expect(sent?.init.body).toBe(file);
    const widen = [...container.querySelectorAll("button")].find((one) => one.textContent === WIDEN_THROUGH_A_DRAFT);
    expect(widen).toBeDefined();
    // Pressing it opens the confirmation for a draft of this agent and changes nothing yet.
    await act(async () => {
      fireEvent.click(widen as Element);
    });
    await waitFor(() => {
      expect(document.querySelector('[role="alertdialog"]')).not.toBeNull();
    });
    expect(posts(idp).some((one) => one.url.includes(`/agents/${AGENT}/drafts`))).toBe(false);
  });

  test("the door's refusal is drawn in its own words and nothing is added", async () => {
    // What breaks if this is deleted: a refused address (a private one, say) shown as a generic
    // failure, or as success.
    const refusal = {
      message: "that address is refused by the address check",
      problems: [{ field: "url", code: "not_added", message: "that address is refused by the address check" }],
    };
    const { container } = await consoleAt(
      answers(knowledgeWire(), { [`POST /api/v1${agentKnowledgeLinkApiPath(AGENT)}`]: { status: 422, body: refusal } }),
    );
    await openWay(container, "Add a web page by its link");
    change(container, "url", "https://169.254.169.254/");
    change(container, "kind", "sop");
    await act(async () => {
      fireEvent.submit(container.querySelector("form") as HTMLFormElement);
    });
    await waitFor(() => {
      expect(container.textContent).toContain("refused by the address check");
    });
    expect(container.querySelector('[data-slot="knowledge-added"]')).toBeNull();
  });

  test("a reader the API says may not add is offered no way to add", async () => {
    // What breaks if this is deleted: an add offered to a reader the door will refuse.
    const { container } = await consoleAt(answers(knowledgeWire({ can_add: false })));
    expect([...container.querySelectorAll("button")].some((one) => one.textContent === "Add a file")).toBe(false);
  });

  test("an answer with no sentence is not an addition", () => {
    // What breaks if this is deleted: a malformed answer drawn as a blank confirmation.
    expect(readKnowledgeAdded({ item_id: "x" })).toBeNull();
    expect(readKnowledgeAdded(addedWire())?.reached).toBe(true);
  });
});

describe("the other sources", () => {
  test("each connected source and skill is named by kind and links to the page that owns it", async () => {
    // What breaks if this is deleted: M39.9.1.7's one place for the agent's whole context, or a
    // source listed with no way to the page that manages it.
    const { container } = await consoleAt(answers());
    const rowsOf = [...container.querySelectorAll('[data-slot="knowledge-other-sources"] li')];
    const said = rowsOf.map((one) => one.textContent);
    expect(said[0]).toContain("Connected source");
    expect(said[0]).toContain("ledger");
    expect(said[1]).toContain("requested");
    expect(said.some((one) => one?.includes("2 more connected sources"))).toBe(true);
    expect(said.some((one) => one?.includes("Skill") && one.includes("ssl-renewal-runbook"))).toBe(true);
    const hrefs = [...container.querySelectorAll('[data-slot="knowledge-other-sources"] a')].map((one) => one.getAttribute("href"));
    expect(hrefs).toContain("/connectors/ledger");
    expect(hrefs).toContain("/skills/ssl-renewal-runbook");
  });
});

describe("the figures beside each document", () => {
  test("a document the agent drew on says how often, one it never touched says so, and the basis is stated once", async () => {
    // What breaks if this is deleted: M39.2.3.5's per-item figures reaching the page without saying
    // whose activity they are, or an untouched document with nothing to prune it by.
    const { container } = await consoleAt(
      answers(
        knowledgeWire({
          items: [item("one", { uses: 4 }), item("two", { uses: 0 }), item("three", { uses: 1 })],
          use_figures: { window_days: 30, basis: "answers by everybody who asked this agent" },
        }),
      ),
    );
    const said = rows(container).map((one) => one.querySelector('[data-slot="knowledge-uses"]')?.textContent);
    expect(said).toEqual(["Cited in 4 answers in the last 30 days", "Not cited in the last 30 days", "Cited in 1 answer in the last 30 days"]);
    expect(container.textContent).toContain("count answers by everybody who asked this agent");
  });

  test("while nothing is counted no document carries a figure, which is not the same as nought", async () => {
    // What breaks if this is deleted: an install that never switched counting on drawing every
    // document as one the agent never touched.
    const { container } = await consoleAt(answers());
    expect(container.querySelectorAll('[data-slot="knowledge-uses"]').length).toBe(0);
    expect(container.textContent).not.toContain("Not cited");
  });
});

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
    await waitFor(() => {
      const ways = [...container.querySelectorAll('[data-slot="knowledge-empty"] button')].map((one) => one.textContent);
      expect(ways).toEqual(["Add a file", "Add a web page by its link"]);
    });
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

function dialogButton(label: string): HTMLButtonElement {
  const found = [...document.querySelectorAll('[role="alertdialog"] button')].find((one) => one.textContent === label);
  if (found === undefined) {
    throw new Error(`no ${label} button in the confirmation`);
  }
  return found as HTMLButtonElement;
}

async function press(container: HTMLElement, label: string): Promise<void> {
  const button = await waitFor(() => {
    const found = [...container.querySelectorAll('[data-slot="knowledge-item"] button')].find((one) => one.textContent === label);
    if (found === undefined) {
      throw new Error(`no ${label} button on a row`);
    }
    return found;
  });
  await act(async () => {
    fireEvent.click(button);
  });
}

describe("how a document arrived, and what may be done to it", () => {
  test("a file, a link and a document that recorded nothing are each said as recorded, and no act is drawn where the API offered none", async () => {
    // What breaks if this is deleted: M39.9.1.1's way of arriving drawn as a guess for an old
    // document, or a Retire button drawn for a reader the API did not offer it to.
    const wire = knowledgeWire({
      items: [
        item("file", { arrived_as: "file" }),
        item("link", { arrived_as: "link", can_retire: true, can_refetch: true }),
        item("old"),
      ],
    });
    const { container, idp } = await consoleAt(answers(wire));
    const said = rows(container).map((one) => one.querySelector('[data-slot="knowledge-arrival"]')?.textContent);
    expect(said).toEqual(["added as a file", "added from a link", "how it was added is not recorded"]);
    const acts = rows(container).map((one) => one.querySelector('[data-slot="knowledge-acts"]') !== null);
    expect(acts).toEqual([false, true, false]);
    expect(posts(idp)).toEqual([]);
  });

  test("retiring asks first, sends the agent's own address once confirmed and draws the list again without it", async () => {
    // What breaks if this is deleted: M39.9.1.5's retire acting without a confirmation, or leaving a
    // retired document on the list the agent draws from.
    const retire = `POST /api/v1${agentKnowledgeRetireApiPath(AGENT, "two")}`;
    const table = answers(knowledgeWire({ items: [item("one"), item("two", { can_retire: true })] }), {
      [retire]: { body: { item_id: "two", title: "Title of two", said: "Retired." } },
    });
    const { container, idp } = await consoleAt(table);
    await press(container, "Retire");
    await waitFor(() => {
      expect(document.querySelector('[role="alertdialog"]')?.textContent).toContain("No agent answers from it");
    });
    expect(posts(idp)).toEqual([]);
    table[`GET /api/v1${agentKnowledgeApiPath(AGENT, 0)}`] = { body: knowledgeWire({ items: [item("one")] }) };
    await act(async () => {
      fireEvent.click(dialogButton("Retire"));
    });
    await waitFor(() => {
      expect(rows(container)).toHaveLength(1);
    });
    expect(posts(idp).map((one) => one.url.replace(/^.*\/api\/v1/, ""))).toEqual([agentKnowledgeRetireApiPath(AGENT, "two")]);
    expect(rows(container)[0]?.textContent).toContain("Title of one");
  });

  test("a retire the API refuses is shown in its words and the document stays listed", async () => {
    // What breaks if this is deleted: a refused retire drawn as done, so the person believes a
    // document no longer answers.
    const retire = `POST /api/v1${agentKnowledgeRetireApiPath(AGENT, "two")}`;
    const refusal = { message: "I could not find that.", problems: [] };
    const { container } = await consoleAt(
      answers(knowledgeWire({ items: [item("two", { can_retire: true })] }), { [retire]: { status: 404, body: refusal } }),
    );
    await press(container, "Retire");
    await waitFor(() => {
      expect(document.querySelector('[role="alertdialog"]')).not.toBeNull();
    });
    await act(async () => {
      fireEvent.click(dialogButton("Retire"));
    });
    await waitFor(() => {
      expect(container.textContent).toContain("I could not find that.");
    });
    expect(rows(container)).toHaveLength(1);
  });

  test("fetching a link again happens only when a person presses it, asks for a review date and confirms, and sends no address", async () => {
    // What breaks if this is deleted: M39.9.1.5's refetch fetched on load, or without confirming
    // that it replaces the version answers use, or sent an address a caller could point elsewhere.
    const refetch = `POST /api/v1${agentKnowledgeRefetchApiPath(AGENT, "link")}`;
    const table = answers(knowledgeWire({ items: [item("link", { arrived_as: "link", can_refetch: true })] }), {
      [refetch]: { status: 201, body: { item_id: "newer", supersedes: "link", title: "Title", level: "department", department: "web", passages: 1, found_by: "text search" } },
    });
    const { container, idp } = await consoleAt(table);
    expect(posts(idp)).toEqual([]);
    await press(container, "Fetch the page again");
    await waitFor(() => {
      expect(container.querySelector('[data-slot="knowledge-fetch-again"] form')).not.toBeNull();
    });
    expect(posts(idp)).toEqual([]);
    change(container, "review_by", "2999-01-01");
    await act(async () => {
      fireEvent.submit(container.querySelector('[data-slot="knowledge-fetch-again"] form') as HTMLFormElement);
    });
    await waitFor(() => {
      expect(document.querySelector('[role="alertdialog"]')?.textContent).toContain("from the address it was added from");
    });
    expect(posts(idp)).toEqual([]);
    await act(async () => {
      fireEvent.click(dialogButton("Fetch the page again"));
    });
    await waitFor(() => {
      expect(posts(idp)).toHaveLength(1);
    });
    const [sent] = posts(idp);
    expect(sent?.url.endsWith(agentKnowledgeRefetchApiPath(AGENT, "link"))).toBe(true);
    expect(Object.keys(JSON.parse(String(sent?.init.body)))).toEqual(["review_by"]);
  });
});
