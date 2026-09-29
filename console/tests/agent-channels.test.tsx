/**
 * Where an agent answers, on its Profile: the web page and the chats it could be carried on, each
 * switched on or off only through its confirmation, the switch offered only where the API said the
 * reader may switch, and an agent switched on nowhere said so in the owner's words.
 *
 * **Mounted through the application's own route table** and answered by a stand-in API that records
 * every request, as `agent-tools.test.tsx` mounts the tools block.
 *
 * Task ids: M39.2.4.1, M39.2.4.2, M39.2.4.3, M39.2.4.4
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { CHANNEL_WORDS, agentChannelsApiPath, readChannels } from "../src/pages/agents/AgentChannels";
import { viewAddress } from "../src/pages/agents/AgentDetailPage";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { apiDocument } from "./support/openapi";
import { backendEnumMembers } from "./support/python";
import { installRadixStubs } from "./support/radix";
import { extractOne, readRepoFile } from "./support/repo";

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
      tools: [],
      leash: [],
    },
  };
}

function channelsWire(extra: Record<string, unknown> = {}): unknown {
  return {
    agent_id: AGENT,
    channels: [
      { channel: "console", on: true, profile: null, group_installable: false },
      { channel: "lark", on: false, profile: "card", group_installable: false },
    ],
    reachable: true,
    unreachable: null,
    may_switch: true,
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
      if (!container.querySelector('[data-slot="channels-listed"]')) {
        throw new Error("the channels block has not arrived");
      }
    },
    { timeout: 10_000 },
  );
  return { container, idp };
}

function answers(channels: unknown = channelsWire(), extra: Readonly<Record<string, Answer>> = {}): Record<string, Answer> {
  return {
    [`/api/v1/agents/${AGENT}/workspace`]: { body: workspaceWire() },
    [`/api/v1${agentChannelsApiPath(AGENT)}`]: { body: channels },
    ...extra,
  };
}

function posts(idp: FakeIdp): FakeIdp["calls"] {
  return idp.calls.filter((one) => one.init?.method === "POST" && one.url.includes("/channels"));
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

function row(container: HTMLElement, channel: string): Element {
  return container.querySelector(`[data-slot="channels-listed"] li[data-channel="${channel}"]`) as Element;
}

describe("the channels block", () => {
  test("the web page is switched off only through its confirmation, which says questions stop reaching it", async () => {
    // What breaks if this is deleted: M39.2.4.1's switch sent without asking.
    const { container, idp } = await consoleAt(answers());
    expect(row(container, "console").textContent).toContain("Web page");
    expect(row(container, "console").textContent).toContain("Switched on");
    await act(async () => {
      fireEvent.click([...row(container, "console").querySelectorAll("button")].find((one) => one.textContent === "Switch off") as Element);
    });
    expect(posts(idp)).toEqual([]);
    const dialog = await confirm("");
    expect(dialog.textContent).toContain("stops answering there");
    await confirm("Switch off");
    expect(JSON.parse(String(posts(idp)[0]?.init?.body))).toEqual({ channel: "console", on: false });
  });

  test("a chat the API offered is switched on from its confirmation, drawn with how it lays an answer out", async () => {
    // What breaks if this is deleted: a chat switched on without asking, or its derived profile lost.
    const { container, idp } = await consoleAt(answers());
    expect(row(container, "lark").textContent).toContain("Lark as cards");
    await act(async () => {
      fireEvent.click([...row(container, "lark").querySelectorAll("button")].find((one) => one.textContent === "Switch on") as Element);
    });
    await confirm("Switch on");
    expect(JSON.parse(String(posts(idp)[0]?.init?.body))).toEqual({ channel: "lark", on: true });
  });

  test("an agent switched on nowhere says so in the API's words, and a reader without the role is offered no switch", async () => {
    // The siblings: the sentence is the route's, and the controls are the route's answer.
    const unreachable = extractOne(readRepoFile("src/brain/agents/channel_switches.py"), /^NOT_REACHABLE: Final = "([^"]+)"$/m, "NOT_REACHABLE");
    const { container } = await consoleAt(
      answers(
        channelsWire({
          channels: [{ channel: "console", on: false, profile: null, group_installable: false }],
          reachable: false,
          unreachable,
          may_switch: false,
        }),
      ),
    );
    const block = container.querySelector('[data-slot="agent-channels"]') as Element;
    expect(block.textContent).toContain("Not reachable: no channel is switched on");
    expect(block.querySelectorAll("button")).toHaveLength(0);
  });

  test("the route the block asks is declared, every channel the gate names has words, and a half-sent row is left out", () => {
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    expect(paths).toContain("/api/v1/agents/{agent_id}/channels");
    expect(Object.keys(CHANNEL_WORDS).sort()).toEqual(Object.values(backendEnumMembers("src/brain/gate/context.py", "Channel")).sort());
    expect(readChannels({ channels: [{ on: true }, { channel: "console", on: true }] })?.channels.map((one) => one.channel)).toEqual(["console"]);
  });
});
