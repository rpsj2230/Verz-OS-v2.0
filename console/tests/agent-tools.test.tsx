/**
 * An agent's tools on its Profile: the ones it carries, each detachable, and the ones the reader may
 * attach, every press confirmed and offered only where the API said the reader may press.
 *
 * **Mounted through the application's own route table** and answered by a stand-in API that records
 * every request, as `agent-leash.test.tsx` mounts the leash block.
 *
 * Task ids: M39.8.6, M39.2.1.2, M39.1.1.3
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { NOTHING_CARRIED, NO_SOURCES, agentAttachmentsApiPath, readAttachments } from "../src/pages/agents/AgentTools";
import { viewAddress } from "../src/pages/agents/AgentDetailPage";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { apiDocument } from "./support/openapi";
import { installRadixStubs } from "./support/radix";

const CONSOLE_ORIGIN = "https://console.test";
const AGENT = "quote-helper";

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
      ceiling: { rows: "Every row", reads: [], reads_locked: false, tools: "It may call crm.read_client.", largest_effect: "Reads only", max_side_effect: "none" },
      tools: [{ name: "crm.read_client", description: "Read a client", within_ceiling: true }],
      leash: [],
    },
  };
}

function attachmentsWire(extra: Record<string, unknown> = {}): unknown {
  return {
    agent_id: AGENT,
    carried: [{ name: "crm.read_client", source: "crm", description: "Read a client" }],
    carried_connectors: ["hubspot"],
    tools: [{ name: "crm.read_deal", source: "crm", description: "Read a deal" }],
    connectors: ["freshdesk"],
    may_change_tools: true,
    may_change_connectors: true,
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
  const router = createMemoryRouter(routes, { initialEntries: [viewAddress(AGENT, "profile")] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(
    () => {
      if (!container.querySelector('[data-slot="agent-tools"]')) {
        throw new Error("the tools block has not arrived");
      }
    },
    { timeout: 10_000 },
  );
  return { container, idp };
}

function answers(attachments: unknown = attachmentsWire(), extra: Readonly<Record<string, Answer>> = {}): Record<string, Answer> {
  return {
    [`/api/v1/agents/${AGENT}/workspace`]: { body: workspaceWire() },
    [`/api/v1${agentAttachmentsApiPath(AGENT)}`]: { body: attachments },
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

describe("the tools block", () => {
  test("a carried tool is detached only through its confirmation, which says runs stop being handed it", async () => {
    // What breaks if this is deleted: M39.8.6's remove sent without asking.
    const { container, idp } = await consoleAt({ ...answers(), [`POST /api/v1${agentAttachmentsApiPath(AGENT)}`]: { body: { part: "tool", reference: "crm.read_client", attached: false, tools: ["crm.read_client"] } } });
    const row = container.querySelector('[data-slot="tools-carried"] li') as Element;
    await act(async () => {
      fireEvent.click([...row.querySelectorAll("button")].find((one) => one.textContent === "Detach") as Element);
    });
    expect(posts(idp)).toEqual([]);
    const dialog = await confirm("");
    expect(dialog.textContent).toContain("stop being handed it");
    await confirm("Detach");
    expect(JSON.parse(String(posts(idp)[0]?.init?.body))).toEqual({ part: "tool", reference: "crm.read_client", attached: false });
  });

  test("a tool the API offered is attached from its confirmation", async () => {
    // What breaks if this is deleted: M39.2.1.2's add sent without asking, or for a tool nobody offered.
    const { container, idp } = await consoleAt({ ...answers(), [`POST /api/v1${agentAttachmentsApiPath(AGENT)}`]: { body: { part: "tool", reference: "crm.read_deal", attached: true, tools: ["crm.read_deal"] } } });
    const form = [...container.querySelectorAll('[data-slot="agent-tools"] form')].find((one) => one.textContent?.includes("Attach a tool")) as HTMLFormElement;
    expect([...form.querySelectorAll("option")].map((one) => one.value)).toEqual(["crm.read_deal"]);
    await act(async () => {
      fireEvent.submit(form);
    });
    await confirm("Attach");
    expect(JSON.parse(String(posts(idp)[0]?.init?.body))).toEqual({ part: "tool", reference: "crm.read_deal", attached: true });
  });

  test("a connector is a source it reads: bound and unbound only through confirmations that say so", async () => {
    // What breaks if this is deleted: a connector bound or unbound without asking, or the dialog
    // describing a connector as a bundle of tools when what it changes is the sources a run reads.
    const pressedOn = `POST /api/v1${agentAttachmentsApiPath(AGENT)}`;
    const bind = await consoleAt({ ...answers(), [pressedOn]: { body: { part: "connector", reference: "freshdesk", attached: true, tools: [], connectors: ["hubspot", "freshdesk"] } } });
    const form = [...bind.container.querySelectorAll('[data-slot="agent-tools"] form')].find((one) => one.textContent?.includes("Let it read a connected source")) as HTMLFormElement;
    expect([...form.querySelectorAll("option")].map((one) => one.value)).toEqual(["freshdesk"]);
    await act(async () => {
      fireEvent.submit(form);
    });
    expect(posts(bind.idp)).toEqual([]);
    const dialog = await confirm("");
    expect(dialog.textContent).toContain("Let it read freshdesk?");
    expect(dialog.textContent).toContain("only what each person asking may read there too");
    await confirm("Attach");
    expect(JSON.parse(String(posts(bind.idp)[0]?.init?.body))).toEqual({ part: "connector", reference: "freshdesk", attached: true });
  });

  test("a bound connector is listed as a source it reads and unbound from its own row", async () => {
    // The sibling: the list is the agent's own connector list, and detaching asks first.
    const { container, idp } = await consoleAt({ ...answers(), [`POST /api/v1${agentAttachmentsApiPath(AGENT)}`]: { body: { part: "connector", reference: "hubspot", attached: false, tools: [], connectors: [] } } });
    const row = container.querySelector('[data-slot="connectors-carried"] li') as Element;
    expect(row.textContent).toContain("Reads hubspot");
    await act(async () => {
      fireEvent.click([...row.querySelectorAll("button")].find((one) => one.textContent === "Detach") as Element);
    });
    const dialog = await confirm("");
    expect(dialog.textContent).toContain("Stop it reading hubspot?");
    await confirm("Detach");
    expect(JSON.parse(String(posts(idp)[0]?.init?.body))).toEqual({ part: "connector", reference: "hubspot", attached: false });
  });

  test("a reader without the roles is offered no press, and an agent carrying nothing says so", async () => {
    // The siblings: the controls are the route's answer, and an empty list is one sentence.
    const { container } = await consoleAt(answers(attachmentsWire({ may_change_tools: false, may_change_connectors: false, carried: [], carried_connectors: [] })));
    expect(container.querySelector('[data-slot="agent-tools"] form')).toBeNull();
    expect(container.querySelector('[data-slot="agent-tools"]')?.textContent).toContain(NOTHING_CARRIED);
    expect(container.querySelector('[data-slot="agent-tools"]')?.textContent).toContain(NO_SOURCES);
    expect(container.querySelector('[data-slot="connectors-carried"] button')).toBeNull();
  });

  test("the route the block asks is declared, and a half-sent tool is left out", () => {
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    expect(paths).toContain("/api/v1/agents/{agent_id}/attachments");
    expect(readAttachments({ carried: [{ source: "crm" }, { name: "crm.read_client" }] })?.carried.map((one) => one.name)).toEqual(["crm.read_client"]);
  });
});
