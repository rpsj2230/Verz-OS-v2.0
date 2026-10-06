/**
 * One agent's Artifacts section: reachable from its Sections menu at its own address, drawing what
 * the agent produced with who it was for, what fed it and how long it is kept, filtered by asking
 * the API again, with the file offered where the API said so and the supersession and archive each
 * confirmed.
 *
 * **Mounted through the application's own route table** and answered by a stand-in API that records
 * every request, as `agent-memory.test.tsx` mounts the Memory section.
 *
 * Task ids: M39.5.2.1, M39.5.2.2, M39.5.2.3, M39.5.2.4, M39.5.2.5, M39.5.1.5
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, test, vi } from "vitest";
import { CANNOT_SAVE_FILE, NOTHING_MATCHES, NOTHING_PRODUCED } from "../src/pages/agents/AgentArtifacts";
import {
  agentArtifactsApiPath,
  artifactArchiveApiPath,
  artifactFileApiPath,
  artifactSupersedeApiPath,
  readAgentArtifacts,
} from "../src/pages/agents/agentArtifactsQuery";
import { ARTIFACTS_TAB, viewAddress } from "../src/pages/agents/AgentDetailPage";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { apiDocument } from "./support/openapi";
import { installRadixStubs } from "./support/radix";

const CONSOLE_ORIGIN = "https://console.test";
const AGENT = "quote-helper";
const ADDRESS = viewAddress(AGENT, ARTIFACTS_TAB);
const OLD = "a".repeat(32);
const NEW = "b".repeat(32);
const THEIRS = "c".repeat(32);

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/Agent");
}, 60_000);

// jsdom has no object addresses, so a test that saves a file gives `URL` the two it needs and this
// puts back what was there, whatever the test did.
const ADDRESSES = { create: URL.createObjectURL, revoke: URL.revokeObjectURL };

afterEach(() => {
  URL.createObjectURL = ADDRESSES.create;
  URL.revokeObjectURL = ADDRESSES.revoke;
});

function workspaceWire(): unknown {
  return {
    agent: { agent_id: AGENT, display_name: "Quote Helper", owner_id: "p_steward", created_at: "2019-03-01T09:00:00Z" },
    tabs: ["artifacts", "settings"].map((tab) => ({ tab, label: tab, purpose: "x" })),
    composition: [],
    skills: [],
    connectors: { shown: [], overflow: 0 },
    channels: [],
    headline: { basis: "own", range: "30d", spend_minor: 0, runs: 0, recorded: false },
  };
}

function item(artifactId: string, extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    artifact_id: artifactId,
    kind: "report",
    produced_for: "p_asker",
    produced_for_name: "Ada Asker",
    produced_at: "2019-03-04T09:00:00Z",
    state: "current",
    superseded_by: "",
    run_id: "run-1",
    agent_version: "3",
    kept_as: "payload",
    kept_until: "2019-04-03T09:00:00Z",
    kept_because: "kept 30 days from when it was produced",
    bytes_stored: 2048,
    client_id: "",
    provenance: { sources: ["price_list"], knowledge_items: [{ item_id: "k1", title: "Rate card" }] },
    downloadable: true,
    changeable: true,
    ...extra,
  };
}

function artifactsWire(extra: Record<string, unknown> = {}): unknown {
  return {
    agent_id: AGENT,
    artifacts: [
      item(NEW, { produced_at: "2019-03-05T09:00:00Z" }),
      item(OLD),
      item(THEIRS, { produced_for: "p_other", produced_for_name: "Otto Other", downloadable: false, changeable: false, state: "archived" }),
    ],
    summary: { basis: "everyone", count: 3, bytes_stored: 6144, oldest_at: "2019-03-04T09:00:00Z", expires_soonest_at: "2019-04-03T09:00:00Z" },
    kinds: ["document", "deck", "report", "export", "image"],
    people: [
      { principal_id: "p_asker", name: "Ada Asker" },
      { principal_id: "p_other", name: "Otto Other" },
    ],
    kept_rule: "An artifact is kept no longer than the shortest-lived thing it was built from.",
    unread: "",
    ...extra,
  };
}

interface Answer {
  readonly status?: number;
  readonly body: unknown;
  readonly type?: string;
}

async function consoleAt(answers: Readonly<Record<string, Answer>>): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      const method = init?.method ?? "GET";
      const where = new URL(url, CONSOLE_ORIGIN);
      const answer =
        answers[`${method} ${where.pathname}${where.search}`] ??
        answers[`${method} ${where.pathname}`] ??
        (method === "GET" ? answers[where.pathname] : undefined);
      if (answer === undefined) {
        return null;
      }
      const type = answer.type ?? "application/json";
      const body = type === "application/json" ? JSON.stringify(answer.body) : String(answer.body);
      return new Response(body, { status: answer.status ?? 200, headers: { "content-type": type } });
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [ADDRESS] });
  const { container } = render(<RouterProvider router={router} />);
  // Ten seconds rather than one: the whole suite mounts the console in parallel, and the first
  // render of the route table is where a loaded machine spends its time.
  await waitFor(
    () => {
      if (!container.querySelector('[data-slot="artifact-list"], [data-slot="agent-artifacts"] [data-slot="note"]')) {
        throw new Error("the Artifacts section has not arrived");
      }
    },
    { timeout: 10_000 },
  );
  return { container, idp };
}

function answers(artifacts: unknown = artifactsWire(), extra: Readonly<Record<string, Answer>> = {}): Record<string, Answer> {
  return {
    [`/api/v1/agents/${AGENT}/workspace`]: { body: workspaceWire() },
    [`/api/v1${agentArtifactsApiPath(AGENT)}`]: { body: artifacts },
    ...extra,
  };
}

function posts(idp: FakeIdp): FakeIdp["calls"] {
  return idp.calls.filter((one) => one.init?.method === "POST" && one.url.includes("/api/v1/"));
}

function rowOf(container: HTMLElement, index: number): Element {
  return container.querySelectorAll('[data-slot="artifact-item"]')[index] as Element;
}

function buttonsOf(row: Element): string[] {
  return [...row.querySelectorAll("button")].map((one) => one.textContent ?? "");
}

async function press(row: Element, label: string): Promise<void> {
  await act(async () => {
    fireEvent.click([...row.querySelectorAll("button")].find((one) => one.textContent === label) as Element);
  });
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

describe("the Artifacts section", () => {
  test("it lists what was produced with who it was for, what fed it, how long it is kept, and the figures", async () => {
    // What breaks if this is deleted: M39.5.2.1's list, M39.5.2.3's provenance and M39.5.2.5's
    // figures reaching the page without who, what or until when.
    const { container } = await consoleAt(answers());
    const first = rowOf(container, 0).textContent ?? "";
    expect(first).toContain("Report");
    expect(first).toContain("for Ada Asker");
    expect(first).toContain("kept 30 days from when it was produced");
    expect(rowOf(container, 0).querySelector('[data-slot="artifact-provenance"]')?.textContent).toContain("price_list");
    expect(rowOf(container, 0).querySelector('[data-slot="artifact-provenance"]')?.textContent).toContain("Rate card");
    expect(rowOf(container, 2).textContent).toContain("Archived");
    expect(container.textContent).toContain("6.0 KB");
    expect(container.textContent).toContain("An artifact is kept no longer than the shortest-lived thing");
  });

  test("a filter asks the API again with the type, the person and the days, and never narrows in the page", async () => {
    // What breaks if this is deleted: M39.5.2.2's filters applied to a list the browser already
    // holds, which is the unfiltered list handed over first.
    const narrowed = agentArtifactsApiPath(AGENT, { kind: "deck", producedFor: "p_other", from: "2019-03-01", to: "2019-03-31" });
    const { container, idp } = await consoleAt({ ...answers(), [`GET /api/v1${narrowed}`]: { body: artifactsWire({ artifacts: [] }) } });
    const control = (index: number) => container.querySelectorAll('[data-slot="artifact-filters"] select, [data-slot="artifact-filters"] input')[index] as Element;
    for (const [index, value] of [
      [0, "deck"],
      [1, "p_other"],
      [2, "2019-03-01"],
      [3, "2019-03-31"],
    ] as const) {
      await act(async () => {
        fireEvent.change(control(index), { target: { value } });
      });
    }
    await waitFor(() => {
      expect(container.textContent).toContain(NOTHING_MATCHES);
    });
    expect(idp.calls.some((one) => one.url.endsWith(narrowed))).toBe(true);
    expect(narrowed).toContain("kind=deck");
    expect(narrowed).toContain("produced_for=p_other");
    expect(narrowed).toContain("since=2019-03-01T00%3A00%3A00Z");
  });

  test("the file is offered only where the API said so, is fetched again when pressed, and is saved", async () => {
    // What breaks if this is deleted: M39.5.1.5's download offered on a file the reader may not
    // fetch, or saved from a page copy instead of asked for at the moment it is pressed.
    const made = vi.fn(() => "blob:artifact");
    URL.createObjectURL = made;
    URL.revokeObjectURL = vi.fn();
    const { container, idp } = await consoleAt({
      ...answers(),
      [`GET /api/v1${artifactFileApiPath(AGENT, NEW)}`]: { body: "name,sell_price\ndesign,900\n", type: "text/csv" },
    });
    expect(buttonsOf(rowOf(container, 2))).not.toContain("Download");
    await press(rowOf(container, 0), "Download");
    await waitFor(
      () => {
        expect(made).toHaveBeenCalledTimes(1);
      },
      { timeout: 5_000 },
    );
    expect(idp.calls.some((one) => one.url.endsWith(artifactFileApiPath(AGENT, NEW)))).toBe(true);
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });

  test("a refused download says the API's own sentence, and a browser that cannot save says so", async () => {
    // The sibling: a download the API refuses at the moment it is pressed is not saved.
    const { container } = await consoleAt({
      ...answers(),
      [`GET /api/v1${artifactFileApiPath(AGENT, NEW)}`]: { status: 404, body: { message: "I could not find that." } },
      [`GET /api/v1${artifactFileApiPath(AGENT, OLD)}`]: { body: "x", type: "text/csv" },
    });
    await press(rowOf(container, 0), "Download");
    await waitFor(() => {
      expect(container.querySelector('[role="alert"]')?.textContent).toBe("I could not find that.");
    });
    // A browser with no way to make a file from memory, as `saveFile` asks.
    (URL as { createObjectURL?: unknown }).createObjectURL = undefined;
    await press(rowOf(container, 1), "Download");
    await waitFor(() => {
      expect(container.querySelector('[role="alert"]')?.textContent).toBe(CANNOT_SAVE_FILE);
    });
  });

  test("an archive is offered only where the API said so and is sent from its confirmation", async () => {
    // What breaks if this is deleted: M39.5.2.4's archive on somebody else's artifact, or sent
    // without asking.
    const { container, idp } = await consoleAt({
      ...answers(),
      [`POST /api/v1${artifactArchiveApiPath(AGENT, OLD)}`]: { body: { artifact_id: OLD, state: "archived", superseded_by: "" } },
    });
    expect(buttonsOf(rowOf(container, 2))).toEqual([]);
    await press(rowOf(container, 1), "Archive");
    expect(posts(idp)).toEqual([]);
    const dialog = await confirm("");
    expect(dialog.textContent).toContain("Nothing is deleted");
    await confirm("Archive");
    expect(posts(idp)[0]?.url).toContain(artifactArchiveApiPath(AGENT, OLD));
  });

  test("a replacement names the newer version chosen in its confirmation", async () => {
    // What breaks if this is deleted: M39.5.2.4's supersession sent with no successor, or with
    // one the reader did not choose.
    const { container, idp } = await consoleAt({
      ...answers(),
      [`POST /api/v1${artifactSupersedeApiPath(AGENT, OLD)}`]: { body: { artifact_id: OLD, state: "superseded", superseded_by: NEW } },
    });
    await press(rowOf(container, 1), "Replace with a newer one");
    const dialog = await confirm("");
    expect((dialog.querySelector("select") as HTMLSelectElement).value).toBe(NEW);
    await confirm("Replace");
    const [sent] = posts(idp);
    expect(sent?.url).toContain(artifactSupersedeApiPath(AGENT, OLD));
    expect(JSON.parse(String(sent?.init?.body))).toEqual({ by: NEW });
  });

  test("nothing listed says so without claiming what anybody else may see, and an unread store says why", async () => {
    // The siblings: an empty list is one sentence about the reader, and a process with no record is
    // the API's sentence with no filters and no figures.
    const empty = await consoleAt(answers(artifactsWire({ artifacts: [], people: [], summary: { basis: "own", count: 0, bytes_stored: 0 } })));
    expect(empty.container.textContent).toContain(NOTHING_PRODUCED);
    empty.container.remove();
    const unread = await consoleAt(answers(artifactsWire({ artifacts: [], summary: null, unread: "This process has no database attached." })));
    expect(unread.container.textContent).toContain("This process has no database attached.");
    expect(unread.container.querySelector('[data-slot="artifact-filters"]')).toBeNull();
  });

  test("the routes the section asks are declared, and a half-sent artifact is left out", () => {
    // What breaks if this is deleted: a path spelled differently from the route, or a blank row.
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    expect(paths).toEqual(
      expect.arrayContaining([
        "/api/v1/agents/{agent_id}/artifacts",
        "/api/v1/agents/{agent_id}/artifacts/{artifact_id}/download",
        "/api/v1/agents/{agent_id}/artifacts/{artifact_id}/archive",
        "/api/v1/agents/{agent_id}/artifacts/{artifact_id}/supersede",
      ]),
    );
    const read = readAgentArtifacts({ artifacts: [{ artifact_id: OLD }, item(NEW)], summary: null });
    expect(read?.artifacts.map((one) => one.artifactId)).toEqual([NEW]);
    expect(read?.summary).toBeUndefined();
  });
});
