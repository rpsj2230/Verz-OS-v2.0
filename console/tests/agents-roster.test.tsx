/**
 * The agent roster: that it draws what the API returned and nothing else, and that the
 * workspace's way back lands on it.
 *
 * **Reachable means through the application's own route table.** Every page test here mounts
 * `routes` from `src/App.tsx` on a memory router, signed in through the real session modules
 * and answered by a stand-in API, so a test passes only if the address resolves.
 *
 * **"Nothing else" is compared as markup.** A body carrying counts, states and owners beside
 * the entries renders byte for byte what the same entries render alone, and each refusal has a
 * sibling proving the thing it refuses to draw is drawn when it is sent.
 *
 * **The keyboard loop is driven end to end.** Escape on the strip moves focus to the way back,
 * following it lands on this page, and an agent's name on this page leads back into its
 * workspace. That is M39.1.2.5, which could not close while the way back reached the console's
 * not-found page.
 *
 * Task ids: M39.1.2.5
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { BACK_TO_ROSTER } from "../src/components/AgentWorkspace";
import { ROSTER_ADDRESS } from "../src/components/agentWorkspaceState";
import {
  agentAddress,
  MORE_AGENTS,
  NO_AGENTS,
  ROSTER_HEADING,
} from "../src/pages/Agents";
import { readRoster } from "../src/pages/agentsQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { COMPANY_CONSOLE, NAVIGATION_ADDRESS, departmentConsole } from "./support/navigation";
import { asPythonName, backendDeepLinkPrefix, backendHiddenCountNames, membersOf } from "./support/agentWorkspace";
import { declaredProperty, declaredPropertyNames, declaredResponseSchema } from "./support/openapi";
import { backendPublicMessages } from "./support/python";
import { parseConsoleSource } from "./support/typescript";

const CONSOLE_ORIGIN = "https://console.test";
const ROSTER_API = "/api/v1/agents";
const ROSTER_ROUTE = "/api/v1/agents";

/** The workspace page is split; transform it once before anything is timed. */
beforeAll(async () => {
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
}

/** The whole console at one address, with the stand-in API answering by path and nothing else. */
async function consoleAt(path: string, answers: Readonly<Record<string, Answer>>): Promise<Mounted> {
  const idp = fakeIdentityProvider({
    api(url) {
      const answer = answers[new URL(url, CONSOLE_ORIGIN).pathname];
      if (answer === undefined) {
        return null;
      }
      return new Response(JSON.stringify(answer.body), {
        status: answer.status ?? 200,
        headers: {
          "content-type": "application/json",
          ...(answer.traceId ? { "x-trace-id": answer.traceId } : {}),
        },
      });
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  await settled(container);
  return { container, idp };
}

async function settled(container: HTMLElement): Promise<void> {
  await waitFor(() => {
    if (!container.querySelector("h1")) {
      throw new Error("the page has not arrived");
    }
  });
  await waitFor(() => {
    if (container.querySelector('p.note[role="status"]')) {
      throw new Error("the page is still asking");
    }
  });
}

function entry(agentId: string, displayName: string): Record<string, unknown> {
  return { agent_id: agentId, display_name: displayName };
}

function page(container: HTMLElement): HTMLElement {
  const found = container.querySelector<HTMLElement>("article.page");
  if (!found) {
    throw new Error("No page was rendered.");
  }
  return found;
}

function links(container: HTMLElement): [string, string][] {
  return [...page(container).querySelectorAll("table.roster a")].map((link) => [
    link.textContent ?? "",
    link.getAttribute("href") ?? "",
  ]);
}

/** What a person reads in some markup: its text, with the tags gone. */
function textOf(markup: string): string {
  const holder = document.createElement("div");
  holder.innerHTML = markup;
  return holder.textContent ?? "";
}

async function rosterMarkup(body: unknown): Promise<string> {
  const { container } = await consoleAt(ROSTER_ADDRESS, { [ROSTER_API]: { body } });
  return page(container).innerHTML;
}

// ------------------------------------------------------------------------ what is drawn

describe("the roster", () => {
  test("the roster draws the agents the API returned, in the order it returned them, as links", async () => {
    // What breaks if this is deleted: every refusal below is satisfied by a page that draws
    // nothing. The order is the API's, so the console cannot re-sort a list it did not filter.
    const { container } = await consoleAt(ROSTER_ADDRESS, {
      [ROSTER_API]: { body: { items: [entry("rota_helper", "Rota Helper"), entry("quote_helper", "Quote Helper")] } },
    });

    expect(container.querySelector("h1")?.textContent).toBe(ROSTER_HEADING);
    expect(links(container)).toEqual([
      ["Rota Helper", "/agents/rota_helper"],
      ["Quote Helper", "/agents/quote_helper"],
    ]);
  });

  test("a count or a lifecycle word beside an entry reaches nothing on the page", async () => {
    // What breaks if this is deleted: "3 of 47 agents", or an agent greyed out as disabled,
    // arriving because a route sent a field and a renderer was generous. The body carrying
    // both must render byte for byte what the bare entries render.
    //
    // The steward is deliberately not in this list any more and is the test below. It was
    // refused here while the roster was a list of names; `docs/screens.html` SCREEN 4 is a
    // table with an Owner column, the route sends it to a reader whose audience already
    // covers the agent, and that reader is told the same fact by the agent's own page. What
    // stays refused is a count and a state, because those are facts about agents the reader
    // was not shown and about a decision nobody made on this page.
    const bare = { items: [entry("quote_helper", "Quote Helper")] };
    const leaky = {
      items: [{ ...entry("quote_helper", "Quote Helper"), state: "disabled", hidden_count: 4700 }],
      total: 4700,
      hidden: 4700,
      of_total: "4700",
    };

    expect(readRoster(leaky)).toEqual({
      entries: [{ agentId: "quote_helper", displayName: "Quote Helper" }],
      truncated: false,
    });
    const markup = await rosterMarkup(leaky);
    expect(markup).toBe(await rosterMarkup(bare));
    expect(markup).not.toMatch(/4700|disabled/);
    expect(markup).toContain("Quote Helper");
  });

  test("the department, the steward and the ceiling are drawn when they are sent and absent when they are not", async () => {
    // What breaks if this is deleted: SCREEN 4's three columns silently missing, which is how
    // this roster started, or a column drawn with a word in it for a reader who was not sent
    // the field. The bare body is the sibling: the same page, the same columns, nothing in
    // the cells, and no sentence saying anything was withheld.
    const full = {
      items: [
        {
          ...entry("quote_helper", "Quote Helper"),
          department: "web",
          owner_id: "the-steward",
          ceiling: { clauses: [{ field: "department", op: "eq", value: "web" }] },
        },
      ],
    };

    expect(readRoster(full)?.entries).toEqual([
      {
        agentId: "quote_helper",
        displayName: "Quote Helper",
        department: "web",
        ownerId: "the-steward",
        ceiling: ["department eq web"],
      },
    ]);

    const drawn = await rosterMarkup(full);
    expect(drawn).toContain("the-steward");
    expect(drawn).toContain("department eq web");

    const bare = await rosterMarkup({ items: [entry("quote_helper", "Quote Helper")] });
    expect(bare).not.toMatch(/the-steward|unknown|withheld|not shown/i);
    expect(readRoster({ items: [{ ...entry("quote_helper", "Quote Helper"), ceiling: {} }] })
      ?.entries[0]).toEqual({ agentId: "quote_helper", displayName: "Quote Helper" });
  });

  test("the answer the page holds has no field for what was left out", () => {
    // What breaks if this is deleted: a `hiddenCount` added to the answer to make a heading
    // friendlier. The forbidden names are `brain.ops.jobs`' own list, read rather than copied.
    const forbidden = new Set(backendHiddenCountNames());
    const members = membersOf(parseConsoleSource("src/pages/agentsQuery.ts"), "RosterAnswer");

    expect(members).toEqual(["entries", "truncated"]);
    expect(members.filter((member) => forbidden.has(asPythonName(member)))).toEqual([]);
  });

  test("an entry that does not say which agent it is is not drawn, and an agent is drawn once", () => {
    // What breaks if this is deleted: a link with no address, a name with no agent, or two
    // links for one agent whose keys collide. The sibling entry is carried.
    const answer = readRoster({
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
    });

    expect(answer?.entries).toEqual([{ agentId: "quote_helper", displayName: "Quote Helper" }]);
  });

  test("an empty roster is one sentence, whatever else the body says, and it has no number in it", async () => {
    // What breaks if this is deleted: an empty list that says why it is empty, or counts what
    // it hid. A company with no agents and a reader whose audience covers none are one screen.
    const empty = await rosterMarkup({ items: [] });

    expect(empty).toBe(await rosterMarkup({ items: [], total: 12, hidden: 12 }));
    expect(empty).toContain(NO_AGENTS);
    // The text, not the markup: `<h1>` is a digit in a tag name and says nothing to a reader.
    expect(textOf(empty)).not.toMatch(/\d/);
    expect(await rosterMarkup({ items: [entry("quote_helper", "Quote Helper")] })).not.toContain(NO_AGENTS);
  });

  test("a body that is not a roster draws no list and composes no sentence about it", async () => {
    // What breaks if this is deleted: a body from a different API drawn as an empty roster,
    // which is a claim that this reader may see no agents made on no evidence.
    for (const unreadable of [null, [], {}, { items: "quote_helper" }]) {
      expect(readRoster(unreadable)).toBeNull();
    }
    expect(readRoster({ items: [] })).toEqual({ entries: [], truncated: false });

    const markup = await rosterMarkup({});
    expect(markup).not.toContain(NO_AGENTS);
    expect(markup).not.toContain("roster");
  });

  test("a truncated roster says there is more, without a figure, and only when the API says exactly that", async () => {
    // What breaks if this is deleted: "and 12 more", or a truncation claim read out of a
    // string or a number, which is a fact about hidden rows asserted on a malformed body.
    const truncated = await rosterMarkup({ items: [entry("quote_helper", "Quote Helper")], truncated: true });
    expect(truncated).toContain(MORE_AGENTS);
    expect(textOf(truncated)).not.toMatch(/\d/);
    expect(await rosterMarkup({ items: [entry("quote_helper", "Quote Helper")] })).not.toContain(MORE_AGENTS);

    for (const notTrue of [false, "true", 1, undefined]) {
      expect(readRoster({ items: [], truncated: notTrue })?.truncated).toBe(false);
    }
  });

  test("a refusal is the API's own sentence and its reference, with no roster drawn", async () => {
    // What breaks if this is deleted: a page that explains a refusal in words of its own, or
    // draws an empty list over one, which reads as "you may see no agents" when nothing said so.
    const sentence = backendPublicMessages()["ABSENT"];
    expect(sentence).toBeTruthy();

    const { container } = await consoleAt(ROSTER_ADDRESS, {
      [ROSTER_API]: { status: 404, body: { message: sentence }, traceId: "trace-roster" },
    });

    expect(container.querySelector(".notice__body")?.textContent).toBe(sentence);
    expect(container.querySelector(".notice__trace code")?.textContent).toBe("trace-roster");
    expect(container.querySelector("ul.roster")).toBeNull();
    expect(container.textContent).not.toContain(NO_AGENTS);
  });

  test("the roster asks the roster's address once and asks about no agent", async () => {
    // What breaks if this is deleted: a roster that fetches each agent's workspace to decorate
    // its entries, which is one request per agent and a second path to the same facts.
    const { idp } = await consoleAt(ROSTER_ADDRESS, {
      [ROSTER_API]: { body: { items: [entry("quote_helper", "Quote Helper")] } },
    });
    const asked = idp.urls
      .map((url) => new URL(url, CONSOLE_ORIGIN))
      .filter((url) => url.pathname.startsWith(ROSTER_API));

    expect(asked.map((url) => `${url.pathname}${url.search}`)).toEqual([ROSTER_API]);
  });

  test("every name the roster reads is a name the route declares, and an entry declares no more", () => {
    // What breaks if this is deleted: a reader and the route drifting apart, or a route that
    // started sending an entry's lifecycle state, which is a disclosure decision taken by a
    // serialiser. The entry's set is exact, so a sixth field is a red test rather than a
    // column that appeared.
    //
    // Five rather than two since 2026-09-16, and the three that arrived are the columns
    // `docs/screens.html` SCREEN 4 tabulates: the department, the steward and the ceiling.
    // The first two are what the agent's own page already tells the same reader, and the
    // ceiling is sent only to a reader holding the Agents screen's read, which
    // `tests/unit/test_agent_routes.py` holds against a narrower one.
    const roster = declaredResponseSchema(ROSTER_ROUTE, "get");

    expect(declaredPropertyNames(roster)).toEqual(expect.arrayContaining(["items", "truncated"]));
    expect(declaredPropertyNames(declaredProperty(roster, "items"))).toEqual([
      "agent_id",
      "ceiling",
      "department",
      "display_name",
      "owner_id",
    ]);
  });

  test("an agent's address on the roster is the address the Python side spells", () => {
    // What breaks if this is deleted: a link wrong by one character, which lands on the
    // workspace's refusal and reads as an agent the reader may not open.
    expect(agentAddress("quote_helper")).toBe(`${backendDeepLinkPrefix()}quote_helper`);
    expect(agentAddress("a/b")).toBe(`${backendDeepLinkPrefix()}a%2Fb`);
  });
});

// ------------------------------------------------------------------- the way back (M39.1.2.5)

describe("the way back from a workspace", () => {
  const answers: Record<string, Answer> = {
    [ROSTER_API]: { body: { items: [entry("quote_helper", "Quote Helper")] } },
    [`${ROSTER_API}/quote_helper/workspace`]: {
      body: {
        agent: entry("quote_helper", "Quote Helper"),
        tabs: [
          { tab: "settings", label: "Settings", purpose: "The agent's own decisions." },
          { tab: "memory", label: "Memory", purpose: "What it has been told to remember." },
        ],
        composition: [],
      },
    },
  };

  test("escape on the strip and then the way back lands on the roster, and a name leads back in", async () => {
    // What breaks if this is deleted: the keyboard route out of a workspace ending on the
    // not-found page, which is what it did until this page existed, or a roster whose links
    // do not reach the workspace they name. Driven through the real route table both ways.
    const { container } = await consoleAt("/agents/quote_helper", answers);
    const firstTab = container.querySelector<HTMLButtonElement>('[role="tab"]');
    if (!firstTab) {
      throw new Error("The workspace drew no tab strip.");
    }
    firstTab.focus();

    fireEvent.keyDown(firstTab, { key: "Escape" });
    const back = document.activeElement as HTMLAnchorElement;
    expect(back.textContent).toBe(BACK_TO_ROSTER);

    fireEvent.click(back);
    await waitFor(() => {
      expect(container.querySelector("h1")?.textContent).toBe(ROSTER_HEADING);
    });
    await settled(container);
    expect(links(container)).toEqual([["Quote Helper", "/agents/quote_helper"]]);

    const name = page(container).querySelector<HTMLAnchorElement>("table.roster a");
    if (!name) {
      throw new Error("The roster drew no link.");
    }
    fireEvent.click(name);
    await waitFor(() => {
      expect(container.querySelector(".agent-header h2")?.textContent).toBe("Quote Helper");
    });
  });

  test("the roster is in the navigation, for everybody, at the address the way back uses", async () => {
    // What breaks if this is deleted: a roster reachable only from inside a workspace, which
    // is a page nobody finds without first knowing an agent's slug. "For everybody" is both
    // consoles the API gives: the company's menu and a department's.
    for (const given of [COMPANY_CONSOLE, departmentConsole()]) {
      const { container } = await consoleAt("/", {
        ...answers,
        [NAVIGATION_ADDRESS]: { body: given },
      });
      await waitFor(() => {
        if (container.querySelector('nav [role="status"]')) {
          throw new Error("the menu has not been answered yet");
        }
      });
      const nav = [...container.querySelectorAll("nav a")].map((link) => [
        link.textContent ?? "",
        link.getAttribute("href") ?? "",
      ]);

      // The address rather than the label, and then the label separately: the menu says what
      // `docs/screens.html` calls this section, which is "Agents and leashes", and
      // `brain.ops.console_design.navigation_gaps` is what holds the two together. What this
      // test is for is that the section is there at all and lands where the way back does.
      const entry = nav.find(([, href]) => href === ROSTER_ADDRESS);
      expect(entry).toBeDefined();
      expect(entry?.[0]).toContain(ROSTER_HEADING);
      container.remove();
    }
  });
});
