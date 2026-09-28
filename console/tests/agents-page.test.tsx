/**
 * The Agents list on the shared page kit: that it draws what the API returned and nothing else,
 * names people rather than identifiers, reads its figures from the stats route without inventing
 * one, and draws every act that has no route as inert with its reason.
 *
 * **Reachable means through the application's own route table.** Every page test mounts `routes`
 * from `src/App.tsx` on a memory router, signed in through the real session modules and answered by
 * a stand-in API, so a test passes only if the address resolves.
 *
 * **"Nothing else" is compared as markup.** A body carrying counts beside the entries renders byte
 * for byte what the same entries render alone, and each refusal has a sibling proving the thing it
 * refuses to draw is drawn when it is sent.
 *
 * `readRoster`, which the Ask and Department pages still read the same route with, keeps its own
 * tests here, because the list page and those pages must agree about what an entry is.
 *
 * Task ids: M39.1.2.5, M27.8.6, M27.10.2
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { ROSTER_ADDRESS } from "../src/components/agentWorkspaceState";
import { NOT_RECORDED, UNAVAILABLE_MARK } from "../src/components/kit";
import { agentAddress, NO_AGENTS, ROSTER_HEADING } from "../src/pages/Agents";
import { readRoster } from "../src/pages/agentsQuery";
import { UNAVAILABLE } from "../src/pages/agents/agentActions";
import { ACT_DONE, MAY_NOT_CHANGE, TYPED_MISSING } from "../src/pages/agentLifecycleQuery";
import { DRAFTS_LINK, NOT_AVAILABLE, readAgentRows } from "../src/pages/agents/AgentsPage";
import { DRAFTS_ADDRESS, NEW_AGENT_ADDRESS } from "../src/pages/agents/agentDraftsQuery";
import { NEW_AGENT_HEADING } from "../src/pages/agents/NewAgentPage";
import { agentStatsApiPath } from "../src/pages/agents/agentStats";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { COMPANY_CONSOLE, NAVIGATION_ADDRESS, departmentConsole } from "./support/navigation";
import { asPythonName, backendDeepLinkPrefix, backendHiddenCountNames, membersOf } from "./support/agentWorkspace";
import { apiDocument, declaredProperty, declaredPropertyNames, declaredResponseSchema } from "./support/openapi";
import { backendPublicMessages } from "./support/python";
import { installRadixStubs } from "./support/radix";
import { parseConsoleSource } from "./support/typescript";

const CONSOLE_ORIGIN = "https://console.test";
const ROSTER_API = "/api/v1/agents";
const ROSTER_ROUTE = "/api/v1/agents";

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/Agent");
}, 60_000);

interface Answer {
  readonly status?: number;
  readonly body: unknown;
  readonly traceId?: string;
}

interface Mounted {
  readonly container: HTMLElement;
  readonly idp: FakeIdp;
  readonly router: ReturnType<typeof createMemoryRouter>;
}

async function consoleAt(path: string, answers: Readonly<Record<string, Answer>>): Promise<Mounted> {
  const idp = fakeIdentityProvider({
    api(url) {
      const answer = answers[new URL(url, CONSOLE_ORIGIN).pathname];
      if (answer === undefined) {
        return null;
      }
      return new Response(JSON.stringify(answer.body), {
        status: answer.status ?? 200,
        headers: { "content-type": "application/json", ...(answer.traceId ? { "x-trace-id": answer.traceId } : {}) },
      });
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  await settled(container);
  return { container, idp, router };
}

async function settled(container: HTMLElement): Promise<void> {
  await waitFor(() => {
    if (!container.querySelector("h1")) {
      throw new Error("the page has not arrived");
    }
  });
  await waitFor(() => {
    if (container.querySelector('[data-slot="loading-state"]')) {
      throw new Error("the page is still asking");
    }
  });
}

function entry(agentId: string, displayName: string): Record<string, unknown> {
  return { agent_id: agentId, display_name: displayName, owner_id: `p_${agentId}` };
}

function listPage(container: HTMLElement): HTMLElement {
  const found = container.querySelector<HTMLElement>('[data-slot="list-page"]');
  if (!found) {
    throw new Error("No list page was rendered.");
  }
  return found;
}

function links(container: HTMLElement): [string, string][] {
  return [...listPage(container).querySelectorAll('[data-slot="entity-table"] tbody a')].map((link) => [
    link.textContent ?? "",
    link.getAttribute("href") ?? "",
  ]);
}

function textOf(element: Element): string {
  return element.textContent ?? "";
}

/**
 * The list's markup, with the ids React makes per mount replaced, so two mounts of the same answer
 * compare equal and a difference is a difference in what is drawn.
 */
async function listMarkup(body: unknown, extra: Readonly<Record<string, Answer>> = {}): Promise<string> {
  const { container } = await consoleAt(ROSTER_ADDRESS, { [ROSTER_API]: { body }, ...extra });
  return listPage(container).innerHTML.replace(/«[^»]*»|:r[0-9a-z]+:/g, "ID");
}

// ------------------------------------------------------------------------ what is drawn

describe("the list", () => {
  test("it draws the agents the API returned, in the order it returned them, as links to their pages", async () => {
    // What breaks if this is deleted: every refusal below is satisfied by a page that draws nothing.
    // The order is the API's, so the console cannot re-sort a list it did not filter.
    const { container } = await consoleAt(ROSTER_ADDRESS, {
      [ROSTER_API]: { body: { items: [entry("rota_helper", "Rota Helper"), entry("quote_helper", "Quote Helper")] } },
    });

    expect(container.querySelector("h1")?.textContent).toBe(ROSTER_HEADING);
    expect(links(container)).toEqual([
      ["Rota Helper", "/agents/rota_helper"],
      ["Quote Helper", "/agents/quote_helper"],
    ]);
  });

  test("a count beside the entries reaches nothing on the page", async () => {
    // What breaks if this is deleted: "3 of 47 agents" arriving because a route sent a field and a
    // renderer was generous. The body carrying counts must render byte for byte what the bare entries
    // render.
    const bare = { items: [entry("quote_helper", "Quote Helper")] };
    const leaky = {
      items: [{ ...entry("quote_helper", "Quote Helper"), hidden_count: 4700 }],
      total: 4700,
      hidden: 4700,
      of_total: "4700",
    };
    const markup = await listMarkup(leaky);
    expect(markup).toBe(await listMarkup(bare));
    expect(markup).not.toMatch(/4700/);
    expect(markup).toContain("Quote Helper");
  });

  test("the steward is a name and never an id, and the status and leash are drawn only when sent", async () => {
    // What breaks if this is deleted: the old roster's principal ids back in the Owner column, or a
    // status column saying "unknown" to a reader the API sent no state, which says something was
    // withheld. The bare row is the sibling: the same columns, nothing in the cells.
    const full = {
      items: [
        {
          ...entry("quote_helper", "Quote Helper"),
          owner_id: "p_0447",
          owner_name: "Wei Ling Tan",
          department: "web",
          state: "disabled",
          leash_up_to: "assisted",
        },
      ],
    };
    const drawn = await listMarkup(full);
    const holder = document.createElement("div");
    holder.innerHTML = drawn;
    expect(textOf(holder)).toContain("Wei Ling Tan");
    expect(textOf(holder)).toContain("Disabled");
    expect(textOf(holder)).toContain("Assisted");
    expect(drawn).not.toContain("p_0447");
    expect(drawn).not.toContain("quote_helper<");

    const bare = document.createElement("div");
    bare.innerHTML = await listMarkup({ items: [{ ...entry("quote_helper", "Quote Helper"), owner_id: "p_0447" }] });
    expect(textOf(bare)).not.toMatch(/p_0447|unknown|withheld|Disabled|Enabled|Assisted|Shadow/i);
  });

  test("each row's figures are the stats route's, and a row whose figures cannot be read says so and draws no number", async () => {
    // What breaks if this is deleted: a runs column of zeros for agents whose figures nobody sent,
    // or a list taken down because one agent's figures failed.
    const { container } = await consoleAt(ROSTER_ADDRESS, {
      [ROSTER_API]: { body: { items: [entry("quote_helper", "Quote Helper"), entry("rota_helper", "Rota Helper")] } },
      [`/api/v1${agentStatsApiPath("quote_helper")}`]: { body: { periods: [{ range: "30d", runs: 1284 }], last_active: "2019-03-04T09:42:00Z" } },
      [`/api/v1${agentStatsApiPath("rota_helper")}`]: { status: 404, body: { message: "Nothing here." } },
    });
    await waitFor(() => {
      expect(textOf(listPage(container))).toContain("1,284");
    });
    const rows = [...listPage(container).querySelectorAll("tbody tr")];
    expect(textOf(rows[0] as Element)).toContain("1,284");
    expect(textOf(rows[1] as Element)).toContain(NOT_AVAILABLE);
    expect(textOf(rows[1] as Element)).not.toMatch(/\d/);

    const partial = await consoleAt(ROSTER_ADDRESS, {
      [ROSTER_API]: { body: { items: [entry("quote_helper", "Quote Helper")] } },
      [`/api/v1${agentStatsApiPath("quote_helper")}`]: { body: { periods: [{ range: "30d", runs: null }] } },
    });
    await waitFor(() => {
      expect(textOf(listPage(partial.container))).toContain(NOT_RECORDED);
    });
  });

  test("an empty list is one state, whatever else the body says, and it has no number in it", async () => {
    // What breaks if this is deleted: an empty list that says why it is empty, or counts what it hid.
    // A company with no agents and a reader whose audience covers none are one screen.
    const empty = await listMarkup({ items: [] });
    expect(empty).toBe(await listMarkup({ items: [], total: 12, hidden: 12 }));
    expect(empty).toContain(NO_AGENTS);
    const holder = document.createElement("div");
    holder.innerHTML = empty;
    expect(textOf(holder)).not.toMatch(/\d/);
    expect(await listMarkup({ items: [entry("quote_helper", "Quote Helper")] })).not.toContain(NO_AGENTS);
  });

  test("a refusal is the API's own sentence and its reference, with no list drawn", async () => {
    // What breaks if this is deleted: a page that explains a refusal in words of its own, or draws an
    // empty list over one, which reads as "you may see no agents" when nothing said so.
    const sentence = backendPublicMessages()["ABSENT"];
    expect(sentence).toBeTruthy();
    const { container } = await consoleAt(ROSTER_ADDRESS, {
      [ROSTER_API]: { status: 404, body: { message: sentence }, traceId: "trace-roster" },
    });
    expect(container.querySelector(".notice__body")?.textContent).toBe(sentence);
    expect(container.querySelector(".notice__trace code")?.textContent).toBe("trace-roster");
    expect(container.querySelector('[data-slot="entity-table"]')).toBeNull();
    expect(container.textContent).not.toContain(NO_AGENTS);
  });

  test("the list asks the roster once and each drawn agent's figures once, and no agent's workspace", async () => {
    // What breaks if this is deleted: a list that fetches each agent's workspace to decorate its rows,
    // which is a second path to facts the roster already sends, or figures asked twice per row.
    const { idp } = await consoleAt(ROSTER_ADDRESS, {
      [ROSTER_API]: { body: { items: [entry("quote_helper", "Quote Helper")] } },
      [`/api/v1${agentStatsApiPath("quote_helper")}`]: { body: { periods: [{ range: "30d", runs: 3 }] } },
    });
    await waitFor(() => {
      expect(idp.urls.some((url) => url.includes("/stats"))).toBe(true);
    });
    const asked = idp.urls.map((url) => new URL(url, CONSOLE_ORIGIN)).filter((url) => url.pathname.startsWith("/api/v1/"));
    const paths = asked.map((url) => url.pathname).filter((path) => path !== NAVIGATION_ADDRESS && path !== "/api/v1/me");
    expect(paths.sort()).toEqual([ROSTER_API, `/api/v1${agentStatsApiPath("quote_helper")}`].sort());
  });

  test("New agent opens the guided start, and Drafts the drafts list", async () => {
    // What breaks if this is deleted: a New agent control that opens nothing, which is fake
    // functionality now that a draft can be started, or one that leads somewhere the route table does
    // not resolve. Pressed through the real route table, it lands on the page that starts a draft.
    const { container, router } = await consoleAt(ROSTER_ADDRESS, {
      [ROSTER_API]: { body: { items: [{ ...entry("quote_helper", "Quote Helper"), state: "enabled" }] } },
      "/api/v1/agent-templates": { body: { items: [], next_cursor: null, truncated: false } },
    });
    expect([...container.querySelectorAll(`[${UNAVAILABLE_MARK}]`)].some((one) => one.textContent?.includes("New agent"))).toBe(false);
    const drafts = [...container.querySelectorAll<HTMLAnchorElement>("a")].find((one) => one.getAttribute("href") === DRAFTS_ADDRESS);
    expect(drafts?.textContent).toBe(DRAFTS_LINK);
    const create = [...container.querySelectorAll<HTMLAnchorElement>("a")].find((one) => one.getAttribute("href") === NEW_AGENT_ADDRESS);
    expect(create?.textContent).toContain("New agent");

    fireEvent.click(create as HTMLAnchorElement);
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(NEW_AGENT_ADDRESS);
      expect(container.querySelector("h1")?.textContent).toBe(NEW_AGENT_HEADING);
    });
  });
});

// ------------------------------------------------------------------------ the lifecycle acts

const LIFECYCLE_API = "/api/v1/agents/quote_helper/lifecycle";
const DIGEST = "a".repeat(64);

function lifecycle(overrides: Readonly<Record<string, unknown>> = {}): Record<string, unknown> {
  return {
    agent_id: "quote_helper",
    display_name: "Quote Helper",
    state: "enabled",
    owner_id: "p_quote_helper",
    effective_hash: DIGEST,
    may_change: true,
    may_duplicate: true,
    duplicate_unavailable: null,
    ...overrides,
  };
}

function rosterWith(state: string): Answer {
  return { body: { items: [{ ...entry("quote_helper", "Quote Helper"), state }] } };
}

/** Opens the row's menu from the keyboard and chooses one item, as a keyboard user would. */
async function chooseOnRow(label: string): Promise<void> {
  const trigger = screen.getByRole("button", { name: "Actions for Quote Helper" });
  trigger.focus();
  await act(async () => {
    fireEvent.keyDown(trigger, { key: "Enter" });
  });
  const menu = await screen.findByRole("menu");
  const item = within(menu).getByRole("menuitem", { name: label });
  item.focus();
  await act(async () => {
    fireEvent.keyDown(item, { key: "Enter" });
  });
}

function posts(idp: FakeIdp): { readonly path: string; readonly body: unknown }[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST" && new URL(call.url, CONSOLE_ORIGIN).pathname.startsWith("/api/v1/"))
    .map((call) => ({ path: new URL(call.url, CONSOLE_ORIGIN).pathname, body: JSON.parse(String(call.init?.body ?? "null")) }));
}

describe("the lifecycle acts", () => {
  test("switching an agent off asks the lifecycle route, confirms by name and sends the state it showed", async () => {
    // What breaks if this is deleted: a Switch off that sends without asking, or sends a state the
    // page never showed, so the route's stale-page check compares against a guess. The positive case
    // of the row menu: the write goes out once, from the confirmation, and the list is asked again.
    const { idp } = await consoleAt(ROSTER_ADDRESS, {
      [ROSTER_API]: rosterWith("enabled"),
      [LIFECYCLE_API]: { body: lifecycle() },
      "/api/v1/agents/quote_helper/disable": { body: lifecycle({ state: "disabled" }) },
    });
    const rosterAsked = () => idp.urls.filter((url) => new URL(url, CONSOLE_ORIGIN).pathname === ROSTER_API).length;
    const before = rosterAsked();
    await chooseOnRow("Switch off");

    const dialog = await screen.findByRole("alertdialog", { name: "Switch off Quote Helper?" });
    expect(posts(idp)).toEqual([]);
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: "Switch off" }));
    });
    await screen.findByText(ACT_DONE.disable);
    expect(posts(idp)).toEqual([{ path: "/api/v1/agents/quote_helper/disable", body: { expected_state: "enabled" } }]);
    await waitFor(() => expect(rosterAsked()).toBeGreaterThan(before));
  });

  test("a refusal is the API's own sentence, and nothing is said to have happened", async () => {
    // What breaks if this is deleted: a stale page's 409 drawn as a generic failure, or as done.
    const sentence = "This agent changed after you opened it, so nothing was changed. Look again and choose.";
    await consoleAt(ROSTER_ADDRESS, {
      [ROSTER_API]: rosterWith("disabled"),
      [LIFECYCLE_API]: { body: lifecycle({ state: "disabled" }) },
      "/api/v1/agents/quote_helper/enable": { status: 409, body: { outcome: "moved", sentence } },
    });
    await chooseOnRow("Switch on");
    const dialog = await screen.findByRole("alertdialog", { name: "Switch on Quote Helper?" });
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: "Switch on" }));
    });
    await screen.findByText(sentence);
    expect(screen.queryByText(ACT_DONE.enable)).toBeNull();
  });

  test("a reader the API says may not act is told so, and no confirmation opens", async () => {
    // What breaks if this is deleted: a confirmation offered to somebody whose press the route will
    // refuse, which reads as a broken button after they agreed to it.
    const { idp } = await consoleAt(ROSTER_ADDRESS, {
      [ROSTER_API]: rosterWith("enabled"),
      [LIFECYCLE_API]: { body: lifecycle({ may_change: false }) },
    });
    await chooseOnRow("Archive");
    await screen.findByText(MAY_NOT_CHANGE);
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(posts(idp)).toEqual([]);
  });

  test("a copy with no name sends nothing and says what to fill in, and a named one sends the digest shown", async () => {
    // What breaks if this is deleted: a blank duplicate sent for the API to refuse after the person
    // agreed to it, or a copy sent without the configuration digest the route checks.
    const { idp } = await consoleAt(ROSTER_ADDRESS, {
      [ROSTER_API]: rosterWith("enabled"),
      [LIFECYCLE_API]: { body: lifecycle() },
      "/api/v1/agents/quote_helper/duplicate": {
        status: 201,
        body: { agent: lifecycle({ agent_id: "quote_helper_copy_a1b2c3", state: "disabled" }), leash: [] },
      },
    });
    await chooseOnRow("Duplicate");
    const dialog = await screen.findByRole("alertdialog", { name: "Duplicate Quote Helper?" });
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: "Duplicate" }));
    });
    await screen.findByText(TYPED_MISSING.duplicate ?? "");
    expect(posts(idp)).toEqual([]);

    fireEvent.change(within(dialog).getByLabelText("Name for the copy"), { target: { value: "Quote Helper copy" } });
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: "Duplicate" }));
    });
    await screen.findByText(ACT_DONE.duplicate);
    expect(posts(idp)).toEqual([
      { path: "/api/v1/agents/quote_helper/duplicate", body: { display_name: "Quote Helper copy", expected_hash: DIGEST } },
    ]);
    expect(screen.getByRole("link", { name: "Open the copy" }).getAttribute("href")).toBe("/agents/quote_helper_copy_a1b2c3");
  });
});

// ------------------------------------------------------------------ what an entry becomes

describe("what an entry becomes", () => {
  test("an entry that does not say which agent it is is not drawn, and an agent is drawn once", () => {
    // What breaks if this is deleted: a link with no address, a name with no agent, or two links for
    // one agent whose keys collide. Held for both readers of the route, the list's and `readRoster`.
    const body = {
      items: [
        entry("quote_helper", "Quote Helper"),
        entry("quote_helper", "A Second Quote Helper"),
        entry("", "No Id"),
        { display_name: "Missing Id" },
        { agent_id: "missing_name" },
        { agent_id: 7, display_name: "Numbered" },
        "quote_helper",
        null,
      ],
    };
    expect(readAgentRows(body).map((row) => row.agentId)).toEqual(["quote_helper"]);
    expect(readRoster(body)?.entries.map((one) => one.agentId)).toEqual(["quote_helper"]);
  });

  test("a field sent as null, empty or the wrong type is the same row as a field not sent", () => {
    // What breaks if this is deleted: a cell reading "null" or a blank pill, which says a value exists
    // and was withheld.
    const bare = readAgentRows({ items: [entry("quote_helper", "Quote Helper")] });
    for (const noise of [null, "", "   ", 7, ["enabled"]]) {
      expect(
        readAgentRows({
          items: [{ ...entry("quote_helper", "Quote Helper"), owner_name: noise, state: noise, leash_up_to: noise, department: noise }],
        }),
      ).toEqual(bare);
    }
    expect(readAgentRows({ items: [{ ...entry("quote_helper", "Quote Helper"), owner_name: "Wei Ling Tan", state: "enabled" }] })).toEqual([
      { agentId: "quote_helper", displayName: "Quote Helper", ownerName: "Wei Ling Tan", state: "enabled" },
    ]);
  });

  test("the answers the pages hold have no field for what was left out", () => {
    // What breaks if this is deleted: a `hiddenCount` added to make a heading friendlier. The
    // forbidden names are `brain.ops.jobs`' own list, read rather than copied.
    const forbidden = new Set(backendHiddenCountNames());
    const roster = membersOf(parseConsoleSource("src/pages/agentsQuery.ts"), "RosterAnswer");
    const row = membersOf(parseConsoleSource("src/pages/agents/AgentsPage.tsx"), "AgentRow");
    expect(roster).toEqual(["entries", "truncated"]);
    expect(row).toEqual(["agentId", "displayName", "department", "ownerName", "state", "leashUpTo", "ceiling"]);
    expect([...roster, ...row].filter((member) => forbidden.has(asPythonName(member)))).toEqual([]);
  });

  test("every name the list reads is a name the route declares, and an entry declares no more", () => {
    // What breaks if this is deleted: a reader and the route drifting apart, or a route that started
    // sending a field nobody decided to disclose. The set is exact, so a new field is a red test.
    const roster = declaredResponseSchema(ROSTER_ROUTE, "get");
    expect(declaredPropertyNames(roster)).toEqual(expect.arrayContaining(["items", "truncated"]));
    expect(declaredPropertyNames(declaredProperty(roster, "items"))).toEqual([
      "agent_id",
      "ceiling",
      "department",
      "display_name",
      "leash_up_to",
      "owner_id",
      "owner_name",
      "state",
    ]);
  });

  test("an agent's address on the list is the address the Python side spells", () => {
    // What breaks if this is deleted: a link wrong by one character, which lands on the page's
    // refusal and reads as an agent the reader may not open.
    expect(agentAddress("quote_helper")).toBe(`${backendDeepLinkPrefix()}quote_helper`);
    expect(agentAddress("a/b")).toBe(`${backendDeepLinkPrefix()}a%2Fb`);
  });

  test("no act the pages call coming soon has a route in the API document", () => {
    // What breaks if this is deleted: a sentence saying "coming soon" about an act that has arrived,
    // so a person is told they cannot do what they can. When a lifecycle route lands, this fails
    // until its control is made live and its sentence removed.
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    for (const [act, { retiredBy }] of Object.entries(UNAVAILABLE)) {
      expect(paths.filter((path) => retiredBy.test(path)), act).toEqual([]);
    }
    // The positive sibling: the pattern shape does match the paths it is written for.
    expect(UNAVAILABLE.leash.retiredBy.test("/api/v1/agents/{agent_id}/leash")).toBe(true);
    expect(UNAVAILABLE.level.retiredBy.test("/api/v1/agents/{agent_id}/audience")).toBe(true);
  });
});

// ----------------------------------------------------------------- the way in and the way back

describe("the way in and the way back", () => {
  const answers: Record<string, Answer> = {
    [ROSTER_API]: { body: { items: [entry("quote_helper", "Quote Helper")] } },
    [`${ROSTER_API}/quote_helper/workspace`]: {
      body: {
        agent: entry("quote_helper", "Quote Helper"),
        tabs: [{ tab: "settings", label: "Settings", purpose: "The agent's own decisions." }],
        composition: [],
      },
    },
  };

  test("a name on the list opens the agent, and the agent's trail leads back to the list", async () => {
    // What breaks if this is deleted: a list whose links do not reach the page they name, or an agent
    // page with no way back but the browser's own button. Driven through the real route table.
    const { container } = await consoleAt(ROSTER_ADDRESS, answers);
    const name = listPage(container).querySelector<HTMLAnchorElement>("tbody a");
    fireEvent.click(name as HTMLAnchorElement);
    await waitFor(() => {
      expect(container.querySelector('[data-slot="detail-header"] h1')?.textContent).toBe("Quote Helper");
    });
    const back = [...container.querySelectorAll<HTMLAnchorElement>('nav[aria-label="Breadcrumb"] a')].find((one) => one.getAttribute("href") === ROSTER_ADDRESS);
    expect(back?.textContent).toBe(ROSTER_HEADING);
    fireEvent.click(back as HTMLAnchorElement);
    await waitFor(() => {
      expect(container.querySelector("h1")?.textContent).toBe(ROSTER_HEADING);
    });
  });

  test("the list is in the navigation, for everybody, at the address the way back uses", async () => {
    // What breaks if this is deleted: a list reachable only from inside an agent, which is a page
    // nobody finds without first knowing an agent's slug. "For everybody" is both consoles the API
    // gives: the company's menu and a department's.
    for (const given of [COMPANY_CONSOLE, departmentConsole()]) {
      const { container } = await consoleAt("/", { ...answers, [NAVIGATION_ADDRESS]: { body: given } });
      await waitFor(() => {
        if (container.querySelector('nav [role="status"]')) {
          throw new Error("the menu has not been answered yet");
        }
      });
      const nav = [...container.querySelectorAll("nav a")].map((link) => [link.textContent ?? "", link.getAttribute("href") ?? ""]);
      const found = nav.find(([, href]) => href === ROSTER_ADDRESS);
      expect(found).toBeDefined();
      expect(found?.[0]).toContain(ROSTER_HEADING);
      container.remove();
    }
  });
});
