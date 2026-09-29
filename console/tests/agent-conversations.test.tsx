/**
 * An agent's Conversations section: the reader's own threads it answered in, with who took part,
 * when, the first question and how the run ended, a failed one saying so and nothing more.
 *
 * **Mounted through the application's own route table** and answered by a stand-in API that
 * records every request, as `agent-tools.test.tsx` mounts the tools block.
 *
 * Task ids: M39.8.9
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  NO_CONVERSATIONS,
  STATE_NOT_RECORDED,
  STATE_WORDS,
  agentConversationsApiPath,
  readConversations,
  relativeWhen,
} from "../src/pages/agents/AgentConversations";
import { CONVERSATIONS_TAB, viewAddress, viewFor } from "../src/pages/agents/AgentDetailPage";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { apiDocument } from "./support/openapi";
import { backendEnumMembers } from "./support/python";
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
    tabs: [{ tab: "conversations", label: "conversations", purpose: "x" }],
    composition: [],
    skills: [],
    connectors: { shown: [], overflow: 0 },
    channels: [],
    headline: { basis: "own", range: "30d", spend_minor: 0, runs: 0, recorded: false },
  };
}

function conversationsWire(items: readonly unknown[]): unknown {
  return { agent_id: AGENT, items };
}

async function sectionOf(conversations: unknown): Promise<HTMLElement> {
  const idp = fakeIdentityProvider({
    api(url) {
      const pathname = new URL(url, CONSOLE_ORIGIN).pathname;
      const body =
        pathname === `/api/v1/agents/${AGENT}/workspace`
          ? workspaceWire()
          : pathname === `/api/v1${agentConversationsApiPath(AGENT)}`
            ? conversations
            : undefined;
      return body === undefined ? null : new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [viewAddress(AGENT, CONVERSATIONS_TAB)] });
  const { container } = render(<RouterProvider router={router} />);
  return waitFor(
    () => {
      const found = container.querySelector<HTMLElement>('[data-slot="agent-conversations"]');
      if (found === null) {
        throw new Error("the conversations section has not arrived");
      }
      return found;
    },
    { timeout: 10_000 },
  );
}

describe("the conversations section", () => {
  test("each of the reader's threads shows who took part, its first question and how the run ended, a failed one saying so", async () => {
    // What breaks if this is deleted: M39.8.9's row, or a failed run drawn as if it answered.
    const section = await sectionOf(
      conversationsWire([
        {
          thread_id: "t1",
          title: "what changed this week",
          last_at: "2019-03-06T09:00:00Z",
          last_channel: "lark",
          agents: [{ agent_id: AGENT, display_name: "Quote Helper" }],
          state: "failed",
        },
        {
          thread_id: "t2",
          title: "the Acme quote",
          last_at: "2019-03-05T09:00:00Z",
          last_channel: "console",
          agents: [{ agent_id: AGENT, display_name: "Quote Helper" }, { agent_id: "desk", display_name: "Sales desk" }],
          state: null,
        },
      ]),
    );
    const rows = [...section.querySelectorAll('[data-slot="conversations-listed"] li')];
    expect(rows.map((one) => one.getAttribute("data-state"))).toEqual(["failed", "unrecorded"]);
    expect(rows[0]?.textContent).toContain("what changed this week");
    expect(rows[0]?.textContent).toContain("You, Quote Helper");
    expect(rows[0]?.textContent).toContain("in Lark");
    expect(rows[0]?.textContent).toContain(STATE_WORDS["failed"]);
    expect(rows[1]?.textContent).toContain("You, Quote Helper, Sales desk");
    expect(rows[1]?.textContent).toContain(STATE_NOT_RECORDED);
  });

  test("a reader who has not asked the agent anything is told so, with nothing counted", async () => {
    // The sibling: an empty list is the reader's own history, said in words and never as a number.
    const section = await sectionOf(conversationsWire([]));
    expect(section.textContent).toContain(NO_CONVERSATIONS);
    expect(section.querySelector('[data-slot="conversations-listed"]')).toBeNull();
  });

  test("the section opens only where the workspace lists it, and its route and words match the API", () => {
    expect(viewFor(CONVERSATIONS_TAB, [CONVERSATIONS_TAB])).toBe(CONVERSATIONS_TAB);
    expect(viewFor(CONVERSATIONS_TAB, [])).toBe("dashboard");
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    expect(paths).toContain("/api/v1/agents/{agent_id}/conversations");
    expect(Object.keys(STATE_WORDS).sort()).toEqual(Object.values(backendEnumMembers("src/brain/tables/chat.py", "RunState")).sort());
    expect(readConversations({ items: [{ title: "no id" }, { thread_id: "t", last_at: "2019-03-06T09:00:00Z" }] })?.map((one) => one.threadId)).toEqual(["t"]);
    const now = new Date("2019-03-06T12:00:00Z");
    expect(relativeWhen("2019-03-06T09:00:00Z", now)).toBe("3 hours ago");
    expect(relativeWhen("2019-03-04T12:00:00Z", now)).toBe("2 days ago");
  });
});
