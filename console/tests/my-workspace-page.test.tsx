/**
 * My workspace: the four figures, the four cards and the two sentences, for the person asking.
 *
 * Mounted directly on a memory router at its own address, for the reason
 * `tests/sessions-page.test.tsx` gives. The failures worth testing look like the page working: a
 * budget the API could not read drawn as a budget of nothing, a share spent rounded down into
 * headroom the person does not have, and a request that names somebody.
 *
 * Task ids: M27.7.28
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  AGENTS_CAPTION,
  ITEMS_CAPTION,
  NO_CEILING,
  READING_WORKSPACE,
} from "../src/pages/MyWorkspace";
import { spentOf, type Workspace } from "../src/pages/myWorkspaceQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { declaredParameterNames } from "./support/openapi";

const OPERATION = "/api/v1/me/workspace";
const CONSOLE_ORIGIN = "https://console.test";

beforeAll(async () => {
  await import("../src/pages/MyWorkspace");
}, 60_000);

function workspace(overrides: Partial<Workspace> = {}): Workspace {
  return {
    principal_id: "u_member",
    display_name: "Wei Ling Tan",
    asked: { since: "2019-03-01T00:00:00Z", questions: 143, corrections: "CORRECTIONS-SENTENCE" },
    agents: [
      { agent_id: "support_ticket", provision: "provided", channels: ["lark", "web"], uses: 61 },
      { agent_id: "renewal_chaser", provision: "personal", channels: [], uses: 9 },
    ],
    agents_used_since: "2019-02-05T00:00:00Z",
    budget: [
      { period: "month", ceiling_minor: 4000, spent_minor: 1799, headroom_minor: 2201, alerts_crossed: [] },
    ],
    budget_unread: "",
    knowledge: [{ item_id: "renewal_script", level: "department", department: "maintenance" }],
    knowledge_truncated: false,
    knowledge_not_shown: "NOT-SHOWN-SENTENCE",
    learned: [
      {
        memory_id: "m_1",
        statement: "Hours before dates",
        stated: false,
        confidence: 0.8,
        formed_at: "2019-02-28T00:00:00Z",
      },
    ],
    learned_undo: "UNDO-SENTENCE",
    can_ask_about: "You can see: client, member.",
    accounts: "ACCOUNTS-SENTENCE",
    staleness: null,
    ...overrides,
  };
}

async function mount(body: unknown): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url) {
      return new URL(url, CONSOLE_ORIGIN).pathname === OPERATION
        ? new Response(JSON.stringify(body), {
            status: 200,
            headers: { "content-type": "application/json" },
          })
        : null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { MyWorkspace } = await import("../src/pages/MyWorkspace");
  const router = createMemoryRouter([{ path: "/me", element: <MyWorkspace /> }], {
    initialEntries: ["/me"],
  });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (container.textContent?.includes(READING_WORKSPACE) || !container.querySelector("h2")) {
      throw new Error("still reading");
    }
  });
  return { container, idp };
}

function valueBeside(container: HTMLElement, label: string): string | null {
  for (const row of container.querySelectorAll(".fields__row")) {
    if (row.querySelector("dt")?.textContent === label) {
      return row.querySelector("dd")?.textContent ?? "";
    }
  }
  return null;
}

describe("what the workspace asks for", () => {
  test("the request names nobody, because the route declares nothing that could", async () => {
    // What breaks if this is deleted: a person parameter is added to the page's request for an
    // administrator's convenience, and a personal page becomes a directory.
    expect(declaredParameterNames(OPERATION, "get", "query")).toEqual([]);
    const { idp } = await mount(workspace());
    const asked = idp.urls.filter((url) => new URL(url, CONSOLE_ORIGIN).pathname === OPERATION);
    expect(asked.length).toBeGreaterThan(0);
    expect(asked.every((url) => new URL(url, CONSOLE_ORIGIN).search === "")).toBe(true);
  });
});

describe("what the workspace shows", () => {
  test("the design's four figures and four cards, from what the API sent", async () => {
    // What breaks if this is deleted: a card drops off, or a figure is drawn from something other
    // than the person's own rows, and SCREEN 12 stops being the page it was built to.
    const { container } = await mount(workspace());

    expect(valueBeside(container, "Questions this month")).toContain("143");
    expect(valueBeside(container, "Questions this month")).toContain("CORRECTIONS-SENTENCE");
    expect(valueBeside(container, "Agents I can call")).toContain("2");
    expect(valueBeside(container, "Agents I can call")).toContain("1 of them your own");
    expect(valueBeside(container, "My budget")).toBe("17.99 of 40.00, 45%");
    expect(container.querySelector(`table[aria-label="${AGENTS_CAPTION}"]`)?.textContent).toContain(
      "lark, web",
    );
    expect(container.querySelector(`table[aria-label="${ITEMS_CAPTION}"]`)?.textContent).toContain(
      "maintenance",
    );
    for (const sentence of [
      "Hours before dates",
      "UNDO-SENTENCE",
      "NOT-SHOWN-SENTENCE",
      "ACCOUNTS-SENTENCE",
      "You can see: client, member.",
    ]) {
      expect(container.textContent).toContain(sentence);
    }
  });

  test("a budget the API could not read says why and is never drawn as no budget", async () => {
    // What breaks if this is deleted: the unread budget draws "No budget of your own is set", which
    // tells somebody with a ceiling and a busy month that nothing limits them.
    const { container } = await mount(workspace({ budget: null, budget_unread: "TOO-MANY-RUNS" }));

    expect(valueBeside(container, "My budget")).toBe("TOO-MANY-RUNS");
    expect(container.textContent).not.toContain(NO_CEILING);
  });

  test("the share spent is rounded up, so it never shows more headroom than there is", () => {
    // What breaks if this is deleted: 44.98 per cent spent is drawn as 44, which is headroom
    // rounded in the reassuring direction on the page somebody checks before spending.
    expect(
      spentOf({ period: "month", ceiling_minor: 4000, spent_minor: 1799, headroom_minor: 2201, alerts_crossed: [] }),
    ).toBe("17.99 of 40.00, 45%");
  });
});
