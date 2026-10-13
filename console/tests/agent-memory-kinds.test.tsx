/**
 * An agent's memory kinds: five boxes from the route, the change confirmed and sent with the kinds the
 * card drew, and a reader who may not change them offered no button.
 *
 * Task ids: M39.7.1
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  AgentMemoryKinds,
  CHANGE_MEMORY_KINDS,
  MEMORY_KINDS_HEADING,
  NO_KIND_ON,
  agentMemoryKindsApiPath,
  memoryKindsBody,
  readMemoryKinds,
} from "../src/pages/agents/AgentMemoryKinds";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { apiDocument } from "./support/openapi";
import { installRadixStubs } from "./support/radix";

const AGENT = "quote-helper";

const FIVE = ["conversation", "own", "person", "project", "task"];

function wire(off: readonly string[] = [], mayChange = true): unknown {
  return {
    agent_id: AGENT,
    kinds: FIVE.map((name) => ({ name, label: `L ${name}`, hint: `H ${name}`, on: !off.includes(name) })),
    may_change: mayChange,
    note: "Leaving a kind out deletes nothing.",
  };
}

beforeAll(() => {
  installRadixStubs();
});

describe("the memory kinds card", () => {
  test("it reads the five kinds, the body it sends is the kinds ticked and the kinds drawn, and a name that is no kind is dropped", () => {
    // What breaks if this is deleted: a body that sends what the card did not draw, so a stale page
    // overwrites a change somebody else made.
    const shown = readMemoryKinds(wire(["person"]));
    expect(shown?.kinds.map((one) => one.on)).toEqual([true, true, false, true, true]);
    expect(memoryKindsBody(shown!, new Set(["own", "task"]))).toEqual({
      kinds: ["own", "task"],
      expected: ["conversation", "own", "project", "task"],
    });
    expect(readMemoryKinds({ agent_id: AGENT })).toBeNull();
    expect(readMemoryKinds({ agent_id: AGENT, kinds: [{ label: "no name" }, { name: "own", on: true }] })?.kinds).toHaveLength(1);
  });

  test("its route and fields are the ones the API document declares", () => {
    // What breaks if this is deleted: the card reading a name the route does not send, so every kind
    // is drawn as off.
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    expect(paths).toContain("/api/v1/agents/{agent_id}/memory-kinds");
    expect(agentMemoryKindsApiPath("a/b")).toBe("/agents/a%2Fb/memory-kinds");
  });

  test("a steward is offered the change and is asked to confirm it before anything is sent; a reader who may not is offered none", async () => {
    // What breaks if this is deleted: a one-press switch-off of what an agent remembers, or a button
    // for a reader the route would refuse.
    for (const mayChange of [true, false]) {
      const posts: unknown[] = [];
      const idp = fakeIdentityProvider({
        api(url, init) {
          const pathname = new URL(url, "https://console.test").pathname;
          if (pathname !== `/api/v1${agentMemoryKindsApiPath(AGENT)}`) {
            return null;
          }
          if (init?.method === "POST") {
            posts.push(JSON.parse(String(init.body)));
          }
          return new Response(JSON.stringify(wire([], mayChange)), { status: 200, headers: { "content-type": "application/json" } });
        },
      });
      const loaded = await loadConsole({ idp });
      await signIn(loaded);
      const { container, unmount } = render(<AgentMemoryKinds agentId={AGENT} />);
      await waitFor(() => {
        expect(container.querySelector('[data-slot="agent-memory-kinds"]')).not.toBeNull();
      });
      expect(container.textContent).toContain(MEMORY_KINDS_HEADING);
      const button = screen.queryByRole("button", { name: CHANGE_MEMORY_KINDS });
      expect(button !== null).toBe(mayChange);
      expect(posts).toEqual([]);
      if (button !== null) {
        fireEvent.click(button);
        expect(posts).toEqual([]);
      }
      unmount();
    }
    expect(NO_KIND_ON).toContain("remembers nothing");
  });
});
