/**
 * A person's own Google account on their personal agent, and an auditor's oversight of personal
 * agents: the card is drawn only for the owner, both presses are confirmed before anything is sent,
 * a refusal says so in the API's words, and oversight names an agent and counts nothing.
 *
 * Task ids: M39.10.3, M39.10.4
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeAll, describe, expect, test } from "vitest";
import {
  AgentOversight,
  OVERSIGHT_API_PATH,
  OVERSIGHT_HEADING,
  readOverseen,
} from "../src/pages/agents/AgentOversight";
import {
  AgentOwnWorkspace,
  ATTACH_LABEL,
  CANNOT_ATTACH_YET,
  DETACH_LABEL,
  NOT_CONNECTED_WORDS,
  OWN_WORKSPACE_HEADING,
  agentOwnWorkspaceApiPath,
  ownWorkspaceBody,
  readOwnWorkspace,
} from "../src/pages/agents/AgentOwnWorkspace";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { apiDocument } from "./support/openapi";
import { installRadixStubs } from "./support/radix";

const AGENT = "my-helper";

function wire(over: Record<string, unknown> = {}): unknown {
  return { agent_id: AGENT, attached: false, may_attach: true, account_connected: false, note: "n", ...over };
}

beforeAll(() => {
  installRadixStubs();
});

const JSON_HEADERS = { "content-type": "application/json" };

describe("the own account card", () => {
  test("it reads the facts out of the body, sends only what the person chose, and refuses a body that is not one", () => {
    // What breaks if this is deleted: a body that sends more than the choice, or a card drawn from
    // a body the API did not send, which would draw a button that does nothing.
    expect(readOwnWorkspace(wire({ attached: true, may_attach: false, account_connected: true }))).toEqual({
      agentId: AGENT,
      attached: true,
      mayAttach: false,
      accountConnected: true,
    });
    expect(readOwnWorkspace(wire({ account_connected: null }))?.accountConnected).toBeNull();
    expect(readOwnWorkspace({ agent_id: AGENT })).toBeNull();
    expect(ownWorkspaceBody(true)).toEqual({ attached: true });
    expect(ownWorkspaceBody(false)).toEqual({ attached: false });
  });

  test("its route and the oversight route are the ones the API document declares", () => {
    // What breaks if this is deleted: a page asking an address the API does not serve, drawn as
    // nothing for everybody because a refused read is a hidden card.
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    expect(paths).toContain("/api/v1/agents/{agent_id}/own-workspace");
    expect(paths).toContain(`/api/v1${OVERSIGHT_API_PATH}`);
    expect(agentOwnWorkspaceApiPath("a/b")).toBe("/agents/a%2Fb/own-workspace");
  });

  test("attaching asks first and sends nothing until it is confirmed, then sends the choice and reads again", async () => {
    // What breaks if this is deleted: a one-press attach of a person's own mail to an agent, or a
    // confirmation that sends something other than what it says.
    const posts: unknown[] = [];
    let attached = false;
    const idp = fakeIdentityProvider({
      api(url, init) {
        const pathname = new URL(url, "https://console.test").pathname;
        if (pathname !== `/api/v1${agentOwnWorkspaceApiPath(AGENT)}`) {
          return null;
        }
        if (init?.method === "POST") {
          posts.push(JSON.parse(String(init.body)));
          attached = true;
        }
        return new Response(JSON.stringify(wire({ attached, may_attach: !attached })), { status: 200, headers: JSON_HEADERS });
      },
    });
    const loaded = await loadConsole({ idp });
    await signIn(loaded);
    const { container } = render(
      <MemoryRouter>
        <AgentOwnWorkspace agentId={AGENT} name="Mine" />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(container.querySelector('[data-slot="agent-own-workspace"]')).not.toBeNull();
    });
    expect(container.textContent).toContain(OWN_WORKSPACE_HEADING);
    expect(container.textContent).toContain(NOT_CONNECTED_WORDS);

    fireEvent.click(screen.getByRole("button", { name: ATTACH_LABEL }));
    expect(posts).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "Attach" }));

    await waitFor(() => {
      expect(posts).toEqual([{ attached: true }]);
      expect(screen.queryByRole("button", { name: DETACH_LABEL })).not.toBeNull();
    });
  });

  test("taking it off is confirmed too, and a refusal is the API's own sentence under a heading that says nothing changed", async () => {
    // What breaks if this is deleted: a detach with no question asked, or a refusal swallowed so the
    // person thinks their account was attached.
    const posts: unknown[] = [];
    const idp = fakeIdentityProvider({
      api(url, init) {
        const pathname = new URL(url, "https://console.test").pathname;
        if (pathname !== `/api/v1${agentOwnWorkspaceApiPath(AGENT)}`) {
          return null;
        }
        if (init?.method === "POST") {
          posts.push(JSON.parse(String(init.body)));
          return new Response(JSON.stringify({ message: "This agent changed after you opened it, so nothing was changed." }), {
            status: 409,
            headers: JSON_HEADERS,
          });
        }
        return new Response(JSON.stringify(wire({ attached: true, may_attach: false, account_connected: true })), {
          status: 200,
          headers: JSON_HEADERS,
        });
      },
    });
    const loaded = await loadConsole({ idp });
    await signIn(loaded);
    const { container } = render(
      <MemoryRouter>
        <AgentOwnWorkspace agentId={AGENT} name="Mine" />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: DETACH_LABEL })).not.toBeNull();
    });

    fireEvent.click(screen.getByRole("button", { name: DETACH_LABEL }));
    expect(posts).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "Take off" }));

    await waitFor(() => {
      expect(container.textContent).toContain("Nothing was changed");
      expect(container.textContent).toContain("so nothing was changed");
    });
    expect(posts).toEqual([{ attached: false }]);
  });

  test("a person who may not attach is offered no button and told what to ask, and a refused read draws nothing", async () => {
    // What breaks if this is deleted: a button for a person the route would refuse, or a heading
    // drawn for a reader who is told nothing about this agent.
    let status = 200;
    const idp = fakeIdentityProvider({
      api(url) {
        const pathname = new URL(url, "https://console.test").pathname;
        if (pathname !== `/api/v1${agentOwnWorkspaceApiPath(AGENT)}`) {
          return null;
        }
        return new Response(JSON.stringify(status === 200 ? wire({ may_attach: false, account_connected: null }) : { message: "no" }), {
          status,
          headers: JSON_HEADERS,
        });
      },
    });
    const loaded = await loadConsole({ idp });
    await signIn(loaded);
    const first = render(
      <MemoryRouter>
        <AgentOwnWorkspace agentId={AGENT} name="Mine" />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(first.container.textContent).toContain(CANNOT_ATTACH_YET);
    });
    expect(screen.queryByRole("button", { name: ATTACH_LABEL })).toBeNull();
    first.unmount();

    status = 404;
    const second = render(
      <MemoryRouter>
        <AgentOwnWorkspace agentId={AGENT} name="Mine" />
      </MemoryRouter>,
    );
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(second.container.textContent).toBe("");
  });
});

describe("oversight of personal agents", () => {
  test("it reads each agent once with its id and name, falls back to the owner's id for a name, and drops what is not an agent", () => {
    // What breaks if this is deleted: a row drawn for an entry with no id, which would be a door to
    // nothing, or the same agent twice.
    const rows = readOverseen({
      items: [
        { agent_id: "a", display_name: "A", owner_id: "u_a", owner_name: "Amy", state: "enabled" },
        { agent_id: "a", display_name: "A again", owner_id: "u_a", state: "enabled" },
        { agent_id: "b", display_name: "B", owner_id: "u_b", state: "disabled" },
        { display_name: "no id" },
      ],
    });
    expect(rows.map((one) => [one.agentId, one.ownerName, one.state])).toEqual([
      ["a", "Amy", "enabled"],
      ["b", "u_b", "disabled"],
    ]);
    expect(readOverseen({ nothing: true })).toEqual([]);
  });

  test("it draws names and owners with no link and no number, and nothing at all when it was told of none", async () => {
    // What breaks if this is deleted: a link into an agent the reader may not open, a count of the
    // agents they were told of, or a heading over an empty list that says which readers hold the
    // capability.
    let items: unknown[] = [
      { agent_id: "amy-helper", display_name: "Amy helper", owner_id: "u_amy", owner_name: "Amy", state: "enabled" },
    ];
    const idp = fakeIdentityProvider({
      api(url) {
        if (new URL(url, "https://console.test").pathname !== `/api/v1${OVERSIGHT_API_PATH}`) {
          return null;
        }
        return new Response(JSON.stringify({ items, truncated: false }), { status: 200, headers: JSON_HEADERS });
      },
    });
    const loaded = await loadConsole({ idp });
    await signIn(loaded);
    const first = render(<AgentOversight />);
    await waitFor(() => {
      expect(first.container.textContent).toContain(OVERSIGHT_HEADING);
    });
    expect(first.container.textContent).toContain("Amy helper");
    expect(first.container.querySelectorAll("a")).toHaveLength(0);
    expect(first.container.textContent).not.toMatch(/[0-9]/);
    first.unmount();

    items = [];
    const second = render(<AgentOversight />);
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(second.container.textContent).toBe("");
  });
});
