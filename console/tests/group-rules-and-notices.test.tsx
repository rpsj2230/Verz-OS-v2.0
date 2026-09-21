/**
 * The Roles screen's directory group mapping, and the break-glass notices on the Elevation screen.
 *
 * The mapping (M1.1.5): the rules and the roles the sync wrote are drawn as the API answered them,
 * the form and the retirement are offered only when the API said `editable`, a retirement is asked
 * behind a confirmation, and the form sends the named keys and nothing else. The notices (M1.2.5):
 * each standing Super Admin sees the sessions they were told about, and a reader told nothing is
 * told so in a sentence.
 *
 * Task ids: M1.1.5, M1.2.5
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import {
  GROUP_RULES_API_PATH,
  GROUP_RULE_RETIREMENT_API_PATH,
  submittedGroupRule,
} from "../src/pages/governQuery";
import { BREAK_GLASS_NOTICES_API_PATH } from "../src/pages/governPeopleQuery";
import {
  GROUP_RULES_LIST_LABEL,
  NO_GROUP_RULES,
  RETIRE_RULE,
  SYNCED_LIST_LABEL,
} from "../src/pages/GroupRules";
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

describe("the directory group mapping on the roles screen", () => {
  test("it draws each rule and each role the sync wrote, with when the sync last confirmed it", async () => {
    // What breaks if this is deleted: the mapping and the synced roles are answered and never
    // shown, so an administrator cannot see which group makes somebody a Super Admin.
    const { container } = await consoleAt("/roles", {
      "/govern/roles": { roles: [] },
      [GROUP_RULES_API_PATH]: RULES,
    });
    await waitFor(() => {
      expect(container.querySelector(`[aria-label="${GROUP_RULES_LIST_LABEL}"]`)).not.toBeNull();
    });
    const synced = container.querySelector(`[aria-label="${SYNCED_LIST_LABEL}"]`);
    expect(synced?.textContent).toContain("u_member");
    expect(synced?.textContent).toContain("2019-03-05");
    expect(container.textContent).toContain("Retire /brain/auditor as auditor");
  });

  test("a reader who may not map is offered neither the form nor a retirement", async () => {
    // What breaks if this is deleted: a reader is offered controls every press of which is refused.
    const { container } = await consoleAt("/roles", {
      "/govern/roles": { roles: [] },
      [GROUP_RULES_API_PATH]: { ...RULES, editable: false },
    });
    await waitFor(() => {
      expect(container.querySelector(`[aria-label="${GROUP_RULES_LIST_LABEL}"]`)).not.toBeNull();
    });
    expect(container.querySelector('[aria-label="Map a directory group to a role"]')).toBeNull();
    expect(container.textContent).not.toContain("Retire /brain/auditor");
  });

  test("a retirement is asked behind a confirmation and then sent with the rule's id", async () => {
    // What breaks if this is deleted: one press removes a role from a whole directory group.
    const { container, idp } = await consoleAt("/roles", {
      "/govern/roles": { roles: [] },
      [GROUP_RULES_API_PATH]: RULES,
    });
    await waitFor(() => {
      expect(container.textContent).toContain("Retire /brain/auditor as auditor");
    });
    const button = [...container.querySelectorAll("button")].find(
      (one) => one.textContent === "Retire /brain/auditor as auditor",
    );
    fireEvent.click(button as HTMLButtonElement);
    expect(writes(idp)).toEqual([]);
    const confirm = [...container.querySelectorAll("button")].find((one) => one.textContent === RETIRE_RULE);
    fireEvent.click(confirm as HTMLButtonElement);
    await waitFor(() => {
      expect(writes(idp).map((one) => one.url)).toEqual([
        expect.stringContaining(GROUP_RULE_RETIREMENT_API_PATH),
      ]);
    });
    expect(writes(idp)[0]?.body).toEqual({ rule_id: "r-1" });
  });

  test("the form sends the group, the role and the reason, and a blank is said before sending", async () => {
    // What breaks if this is deleted: the mapping is served and unreachable, or a blank group is
    // sent for the API to refuse in words that do not name the field.
    const { container, idp } = await consoleAt("/roles", {
      "/govern/roles": { roles: [] },
      [GROUP_RULES_API_PATH]: { ...RULES, rules: [] },
    });
    await waitFor(() => {
      expect(container.textContent).toContain(NO_GROUP_RULES);
    });
    const form = container.querySelector('[aria-label="Map a directory group to a role"]') as HTMLFormElement;
    fireEvent.submit(form);
    expect(container.textContent).toContain("Fill in");
    expect(writes(idp)).toEqual([]);
    const set = (name: string, value: string) => {
      fireEvent.change(form.querySelector(`[name="${name}"]`) as HTMLElement, { target: { value } });
    };
    set("idp_group", " /brain/auditor ");
    set("role", "auditor");
    set("reason", "the directory says so");
    fireEvent.submit(form);
    await waitFor(() => {
      expect(writes(idp)).toHaveLength(1);
    });
    expect(writes(idp)[0]?.body).toEqual({
      idp_group: "/brain/auditor",
      role: "auditor",
      reason: "the directory says so",
    });
    expect(submittedGroupRule({ idp_group: "g", role: "approver", reason: "r", scope_slug: "web_all", pack: "x" })).toEqual({
      idp_group: "g",
      role: "approver",
      reason: "r",
      scope_slug: "web_all",
    });
  });
});

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
