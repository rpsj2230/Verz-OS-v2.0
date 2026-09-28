/**
 * The break-glass notices on the Elevation screen (M1.2.5): each standing Super Admin sees the
 * sessions they were told about, and a reader told nothing is told so in a sentence. The Roles
 * screen's directory group mapping moved to the page kit and is held by
 * `tests/people-access-pages.test.tsx`.
 *
 * Task ids: M1.2.5
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { BREAK_GLASS_NOTICES_API_PATH } from "../src/pages/governPeopleQuery";
import { NOTHING_TOLD, TOLD_LIST_LABEL } from "../src/pages/Elevation";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";

type Answers = Readonly<Record<string, unknown>>;

const RULES = {
  rules: [
    {
      id: "r-1",
      idp_group: "/brain/auditor",
      role: "auditor",
      scope: null,
      created_by: "u_admin",
      created_at: "2019-03-04T09:00:00Z",
    },
  ],
  synced: [
    {
      principal_id: "u_member",
      role: "auditor",
      source_group: "/brain/auditor",
      first_seen_at: "2019-03-04T09:00:00Z",
      last_seen_at: "2019-03-05T09:00:00Z",
    },
  ],
  editable: true,
};

async function consoleAt(path: string, answers: Answers): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      const method = init?.method ?? "GET";
      if (method === "POST") {
        return new Response(JSON.stringify({ id: "r-2", change: "mapped", at: "2019-03-04T09:00:00Z" }), {
          status: 201,
          headers: { "content-type": "application/json" },
        });
      }
      const found = Object.keys(answers)
        .sort((a, b) => b.length - a.length)
        .find((key) => new URL(url, "http://console").pathname === `/api/v1${key}`);
      if (found === undefined) {
        return null;
      }
      return new Response(JSON.stringify(answers[found]), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (container.querySelector("h1") === null) {
      throw new Error("the page has no heading yet");
    }
  });
  return { container, idp };
}

function writes(idp: FakeIdp): { url: string; body: unknown }[] {
  return idp.calls
    .filter((call) => (call.init?.method ?? "GET") === "POST")
    .filter((call) => call.url.includes("/api/v1/govern/"))
    .map((call) => ({ url: call.url, body: JSON.parse(String(call.init?.body ?? "null")) }));
}

describe("the break-glass notices on the elevation screen", () => {
  const ELEVATION = {
    prompt: "Ask for more",
    holds_nothing_standing: false,
    may_authorise: false,
    reasons: ["lockout"],
    longest_hours: 4,
    items: [],
    next_cursor: null,
    truncated: false,
  };

  test("a standing super admin sees who took emergency access, who allowed it and until when", async () => {
    // What breaks if this is deleted: the notices are written and nobody ever reads one, which is
    // a session nobody was told about.
    const { container } = await consoleAt("/elevation", {
      "/govern/elevation": ELEVATION,
      [BREAK_GLASS_NOTICES_API_PATH]: {
        items: [
          {
            session_id: "s-1",
            principal_id: "u_partner",
            authorised_by: "u_approver",
            reason: "incident_response",
            lapses_at: "2019-03-04T13:00:00Z",
            told_at: "2019-03-04T09:00:00Z",
          },
        ],
      },
    });
    await waitFor(() => {
      expect(container.querySelector(`[aria-label="${TOLD_LIST_LABEL}"]`)).not.toBeNull();
    });
    const told = container.querySelector(`[aria-label="${TOLD_LIST_LABEL}"]`)?.textContent ?? "";
    expect(told).toContain("u_partner");
    expect(told).toContain("u_approver");
    expect(told).toContain("incident response");
  });

  test("a reader told nothing is told so in a sentence", async () => {
    // What breaks if this is deleted: an empty answer renders as a blank section.
    const { container } = await consoleAt("/elevation", {
      "/govern/elevation": ELEVATION,
      [BREAK_GLASS_NOTICES_API_PATH]: { items: [] },
    });
    await waitFor(() => {
      expect(container.textContent).toContain(NOTHING_TOLD);
    });
  });
});
