/**
 * One agent's page on the shared kit: where it is reachable, what each of its three views draws and
 * asks for, and how an answer is read.
 *
 * **Reachable means through the application's own route table.** The page is mounted at the address
 * `brain.console.workspace.deep_link` spells, on a memory router over `routes` from `src/App.tsx`,
 * signed in through the real session modules and answered by a stand-in API. A test that rendered
 * the page component directly would pass with the route deleted.
 *
 * **Withheld and absent are compared as markup.** Each refusal renders the variants a route could
 * plausibly send for "not told" and asserts they are one screen, and each has a sibling proving the
 * field reaches the screen when it is sent.
 *
 * **The design of record is SCREEN 14**: one header and its figures, then Dashboard, Profile and
 * About, each at its own address. It replaced a tab strip beside a two-way pane on 2026-09-28, and
 * the properties the old page's tests held are restated here over the new one: an address opens
 * what it names or the first view, a probe for a tab lands where no tab does, a view change asks
 * nothing again, and another agent never inherits the last one's state.
 *
 * Task ids: M39.1.2.1, M39.1.2.4, M39.1.2.5, M39.1.1.5, M27.10.2, M27.15.32
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { CompositionDiff } from "../src/components/CompositionDiff";
import { NOT_RECORDED, UNAVAILABLE_MARK } from "../src/components/kit";
import { FIGURES_FAILED } from "../src/components/kit/KpiStrip";
import { readAgentWorkspace, type AgentWorkspaceAnswer } from "../src/pages/agentQuery";
import { UNAVAILABLE } from "../src/pages/agents/agentActions";
import { leashRowId, readHeaderFacts, readProfile } from "../src/pages/agents/agentDetailQuery";
import { COMPUTER_HEADING, takenOverWords } from "../src/pages/agents/AgentProfile";
import { ANSWERS_NOWHERE, CHANGE_CHANNELS, CHANNELS_DONE, CHANNELS_QUESTION, SAVE_CHANNELS } from "../src/pages/agents/AgentChannels";
import {
  CHOOSE_A_CHAT,
  GROUP_CHATS,
  INSTALL_HERE,
  INSTALL_QUESTION,
  NO_GROUPS,
  PAUSED,
  REMOVE_QUESTION,
  THE_BOT_LEFT,
} from "../src/pages/agents/AgentGroups";
import { WHERE_IT_ANSWERS } from "../src/pages/agents/ChannelChoices";
import { rungWords } from "../src/pages/agents/agentActions";
import { VIEWS_LABEL, viewAddress } from "../src/pages/agents/AgentDetailPage";
import { agentStatsApiPath } from "../src/pages/agents/agentStats";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import {
  asPythonName,
  backendDeepLinkPrefix,
  backendFieldSource,
  backendHiddenCountNames,
  backendPartOfPath,
  backendTabOrder,
  membersOf,
} from "./support/agentWorkspace";
import {
  apiDocument,
  declaredProperty,
  declaredPropertyNames,
  declaredRequestBodySchema,
  declaredResponseSchema,
} from "./support/openapi";
import { backendEnumMembers, backendModelFields, backendPublicMessages } from "./support/python";
import { installRadixStubs } from "./support/radix";
import { readRepoFile } from "./support/repo";
import { parseConsoleSource, staticImportGraph } from "./support/typescript";

const WORKSPACE_MODULE = "src/brain/console/workspace.py";
const MODEL_MODULE = "src/brain/agents/model.py";
const TEMPLATE_MODULE = "src/brain/agents/template.py";
const CONSOLE_ORIGIN = "https://console.test";
const WORKSPACE_ROUTE = "/api/v1/agents/{agent_id}/workspace";

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/Agent");
}, 60_000);

// ------------------------------------------------------------------------------- fixtures

function capitalised(word: string): string {
  return `${word.slice(0, 1).toLocaleUpperCase("en-GB")}${word.slice(1)}`;
}

/** The part a manifest path supplies, in the spelling `brain.console.workspace` serialises. */
function partOf(path: string): string {
  const member = backendPartOfPath()[path];
  const value = member === undefined ? undefined : backendEnumMembers(WORKSPACE_MODULE, "Part")[member];
  if (value === undefined) {
    throw new Error(`PART_OF_PATH does not map ${path} to a Part value; the fixture is stale.`);
  }
  return value;
}

const SET_HERE = backendFieldSource("INSTANCE");
const FROM_TEMPLATE = backendFieldSource("TEMPLATE");

/** One agent on the wire, with every fact the header can show. */
function agentWire(agentId = "quote-helper", displayName = "Quote Helper"): Record<string, unknown> {
  return {
    agent_id: agentId,
    display_name: displayName,
    summary: "Drafts a first answer to a pricing question.",
    owner_id: "p_steward_one",
    owner_name: "Steward One",
    template_id: "pricing-desk",
    template_version: 4,
    created_at: "2019-03-01T09:00:00Z",
    created_by: "p_builder",
    state: "disabled",
    leash_up_to: "assisted",
  };
}

/** A whole strip on the wire, in `TABS` order and spelled with the `Tab` enum's values. */
function stripWire(): Record<string, unknown>[] {
  const values = backendEnumMembers(WORKSPACE_MODULE, "Tab");
  return backendTabOrder().map((member) => {
    const tab = values[member];
    if (tab === undefined) {
      throw new Error(`TABS names Tab.${member}, which the Tab enum does not declare.`);
    }
    return { tab, label: capitalised(tab), purpose: `What the ${tab} tab is for.` };
  });
}

function compositionWire(): Record<string, unknown>[] {
  return [
    {
      part: partOf("persona"),
      path: "persona",
      template: '"Answer briefly."',
      instance: '"Answer briefly and name the price list."',
      source: SET_HERE,
      set_by: "steward-one",
    },
    {
      part: partOf("skills"),
      path: "skills",
      template: '["quote-draft"]',
      instance: '["quote-draft"]',
      source: SET_HERE,
      set_by: "steward-one",
    },
    {
      part: partOf("tier"),
      path: "tier",
      template: '"standard"',
      instance: '"standard"',
      source: FROM_TEMPLATE,
    },
  ];
}

function assemblyWire(): Record<string, unknown> {
  return {
    divergent: ["persona"],
    skills: [{ name: "ssl-renewal-runbook", digest: "a".repeat(64) }],
    connectors: { shown: [{ source: "ledger", presence: "attached" }], overflow: 0 },
    channels: [{ channel: "lark", profile: "card" }],
    headline: { basis: "own", range: "30d", spend_minor: 1234, runs: 7, recorded: true },
  };
}

/** The Profile block the Settings read is sent. */
function profileWire(): Record<string, unknown> {
  return {
    tier: "main",
    model_pin_provider: null,
    model_pin_model: null,
    audience_level: "department",
    ceiling: {
      rows: "tickets in the Support department",
      reads: ["ticket subject"],
      reads_locked: false,
      tools: "It can search tickets and draft a reply.",
      largest_effect: "It drafts. It cannot send anything.",
      max_side_effect: "draft",
    },
    tools: [
      { name: "ticket.draft_reply", source: "helpdesk", side_effect: "draft", description: "Draft a reply", within_ceiling: true },
    ],
    leash: [{ target: "ticket.draft_reply", rung: "assisted", rungs: ["assisted"], configured: true, acts: true, entries: [] }],
  };
}

function body(agent: Record<string, unknown> = agentWire()): Record<string, unknown> {
  return { agent, tabs: stripWire(), composition: compositionWire(), ...assemblyWire(), profile: profileWire() };
}

function without(record: Record<string, unknown>, ...keys: string[]): Record<string, unknown> {
  const copy = { ...record };
  for (const key of keys) {
    delete copy[key];
  }
  return copy;
}

function read(payload: unknown): AgentWorkspaceAnswer {
  const answer = readAgentWorkspace(payload);
  if (answer === null) {
    throw new Error("The reader found no agent in a body that has one.");
  }
  return answer;
}

function diffMarkup(rows: unknown): string {
  return render(<CompositionDiff rows={read({ agent: agentWire(), composition: rows }).composition} />).container.innerHTML;
}

/** The About tab as the route sends it: numbered steps, an action line naming its tool. */
function aboutWire(): Record<string, unknown> {
  return {
    agent_id: "quote-helper",
    summary: "Drafts a first answer to a pricing question.",
    steps: [
      { number: 1, step: "starts", title: "What starts it", lines: [{ kind: "asked", text: "Somebody asks it in Lark." }] },
      {
        number: 2,
        step: "does",
        title: "What it does",
        lines: [{ kind: "action", text: "Draft a reply: prepares it, then waits for a person.", tool: "ticket.draft_reply", leash_entry: true }],
      },
    ],
    never: [{ text: "It never sees more than the person it is working for could see.", every_agent: true }],
  };
}

/** One agent's figures as `brain.console_stats_routes.AgentStatsView` sends them. */
function statsWire(cost: number | null = 18240, unrecorded: readonly Record<string, string>[] = []): Record<string, unknown> {
  return {
    agent_id: "quote-helper",
    basis: "own",
    cost_basis: "own",
    currency: "SGD",
    last_active: "2019-03-04T09:42:00Z",
    at_least: false,
    periods: [
      { range: "7d", since: "2019-02-25T00:00:00Z", until: "2019-03-04T12:00:00Z", runs: 97, answered: 90, nothing_returned: 7, p50_latency_ms: 950, cost_minor: cost },
      { range: "30d", since: "2019-02-02T00:00:00Z", until: "2019-03-04T12:00:00Z", runs: 391, answered: 360, nothing_returned: 31, p50_latency_ms: 1840, cost_minor: cost },
    ],
    unrecorded,
  };
}

// ------------------------------------------------------------------------------- mounting

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

/** Every answer one agent's page may ask for, by API path. */
function agentAnswers(agentId: string, workspace: unknown, extra: Readonly<Record<string, Answer>> = {}): Record<string, Answer> {
  return {
    [`/api/v1/agents/${agentId}/workspace`]: { body: workspace },
    [`/api/v1/agents/${agentId}/about`]: { body: aboutWire() },
    [`/api/v1${agentStatsApiPath(agentId)}`]: { body: statsWire() },
    "/api/v1/routing/rungs": { body: { items: [], next_cursor: null, truncated: false } },
    ...extra,
  };
}

async function consoleAt(path: string, answers: Readonly<Record<string, Answer>>): Promise<Mounted> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      // A key may name the method (`POST /api/...`) where one path answers a read and a write
      // differently; a bare path answers every method, as it always has.
      const pathname = new URL(url, CONSOLE_ORIGIN).pathname;
      const method = (init?.method ?? "GET").toUpperCase();
      const answer = answers[`${method} ${pathname}`] ?? answers[pathname];
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
    if (!container.querySelector("h1, .notice")) {
      throw new Error("the page has not arrived");
    }
  });
  await waitFor(() => {
    if (container.querySelector('[data-slot="loading-state"], [data-slot="stats-strip"] > [role="status"]')) {
      throw new Error("the page is still asking");
    }
  });
}

async function go(mounted: Mounted, address: string): Promise<void> {
  await act(async () => {
    await mounted.router.navigate(address);
  });
  await settled(mounted.container);
}

function currentView(container: HTMLElement): string {
  return container.querySelector(`nav[aria-label="${VIEWS_LABEL}"] [aria-current="page"]`)?.textContent ?? "";
}

function workspaceRequests(idp: FakeIdp): string[] {
  return idp.urls.map((url) => new URL(url, CONSOLE_ORIGIN).pathname).filter((path) => path.endsWith("/workspace"));
}

function header(container: HTMLElement): Element {
  const found = container.querySelector('[data-slot="detail-header"]');
  if (!found) {
    throw new Error("No header was drawn.");
  }
  return found;
}

// ------------------------------------------------------------------------- reachability

describe("where the page is reachable", () => {
  test("the bare address opens the Dashboard, and each view is a link to its own address", async () => {
    // What breaks if this is deleted: the page with no way in, or views held in state that a shared
    // link cannot open. The addresses are checked against the Python spelling first, so the page
    // answers the link `deep_link` would put in an alert.
    expect(readRepoFile(WORKSPACE_MODULE)).toMatch(/^ {4}return f"\{DEEP_LINK_PREFIX\}\{agent_id\}\/\{key\.value\}"$/m);
    expect(viewAddress("quote-helper", "profile")).toBe(`${backendDeepLinkPrefix()}quote-helper/profile`);
    expect(viewAddress("quote-helper", "dashboard")).toBe(`${backendDeepLinkPrefix()}quote-helper`);

    const mounted = await consoleAt("/agents/quote-helper", agentAnswers("quote-helper", body()));
    expect(header(mounted.container).querySelector("h1")?.textContent).toBe("Quote Helper");
    expect(currentView(mounted.container)).toBe("Dashboard");
    const nav = mounted.container.querySelector(`nav[aria-label="${VIEWS_LABEL}"]`) as Element;
    expect([...nav.querySelectorAll("a")].map((one) => one.getAttribute("href"))).toEqual([
      "/agents/quote-helper",
      "/agents/quote-helper/profile",
      "/agents/quote-helper/about",
    ]);

    await go(mounted, "/agents/quote-helper/about");
    expect(currentView(mounted.container)).toBe("About");
    await go(mounted, "/agents/quote-helper/settings");
    expect(currentView(mounted.container)).toBe("Profile");
  });

  test("an address naming a section this reader cannot open lands where the bare address does", async () => {
    // What breaks if this is deleted: a probe for a tab ("memory", "automations" for a reader without
    // it) that answers differently from an address with no tab, which tells the prober the tab exists.
    const strip = stripWire().filter((one) => one["tab"] !== "automations" && one["tab"] !== "memory");
    const answers = agentAnswers("quote-helper", { ...body(), tabs: strip });
    const bare = await consoleAt("/agents/quote-helper", answers);
    const bareView = currentView(bare.container);
    for (const probe of ["memory", "automations", "no-such-tab"]) {
      const probed = await consoleAt(`/agents/quote-helper/${probe}`, answers);
      expect(currentView(probed.container), probe).toBe(bareView);
    }
  });

  test("the page and its stylesheet are not in the first response, and the page reaches both", () => {
    // What breaks if this is deleted: the split, silently. A static import of the page in `App.tsx`
    // puts the agent page, its views and a stylesheet in front of everybody who never opens an agent.
    const pageFiles = [
      "src/pages/Agent.tsx",
      "src/pages/agents/AgentDetailPage.tsx",
      "src/pages/agents/AgentProfile.tsx",
      "src/components/CompositionDiff.tsx",
      "src/styles/agent-workspace.css",
    ];
    const entry = new Set(staticImportGraph("src/main.tsx").files);
    expect(pageFiles.filter((file) => entry.has(file))).toEqual([]);
    const page = new Set(staticImportGraph("src/pages/Agent.tsx").files);
    expect(pageFiles.filter((file) => !page.has(file))).toEqual([]);
  });

  test("the route the page asks is declared, and every name the header reads is a name it sends", () => {
    // What breaks if this is deleted: a reader and the route drifting apart on a name, which renders
    // an agent with a fact silently missing. The sets are exact.
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    expect(paths).toContain(WORKSPACE_ROUTE);
    const workspace = declaredResponseSchema(WORKSPACE_ROUTE, "get");
    expect(declaredPropertyNames(workspace)).toEqual([
      "agent",
      "channels",
      "composition",
      "connectors",
      "divergent",
      "headline",
      "profile",
      "skills",
      "tabs",
    ]);
    expect(declaredPropertyNames(declaredProperty(workspace, "agent"))).toEqual([
      "agent_id",
      "created_at",
      "created_by",
      "department",
      "display_name",
      "leash_up_to",
      "owner_id",
      "owner_name",
      "state",
      "summary",
      "template_id",
      "template_name",
      "template_version",
    ]);
    const rows = declaredPropertyNames(declaredProperty(workspace, "composition"));
    expect(rows).toEqual(["instance", "part", "path", "source", "template"]);
  });
});

// ------------------------------------------------------------------------------ the header

describe("the header", () => {
  test("it names the steward and states the agent, and its identifiers are only in the Advanced section", async () => {
    // What breaks if this is deleted: the old header's slug and principal id back on the face of the
    // page, which is the clutter the owner asked to be removed; or a header with no steward on it.
    const mounted = await consoleAt("/agents/quote-helper/profile", agentAnswers("quote-helper", body()));
    const top = header(mounted.container);
    expect(top.textContent).toContain("Steward One");
    expect(top.textContent).toContain("Disabled");
    expect(top.textContent).toContain("Assisted");
    expect(top.textContent).not.toMatch(/p_steward_one|p_builder|quote-helper|pricing-desk/);

    const outsideAdvanced = [...mounted.container.querySelectorAll("*")]
      .filter((one) => one.closest('[data-slot="advanced"]') === null && one.children.length === 0)
      .map((one) => one.textContent ?? "")
      .join(" ");
    expect(outsideAdvanced).not.toMatch(/p_steward_one|p_builder|pricing-desk/);
    const advanced = mounted.container.querySelector('[data-slot="advanced"]');
    expect(advanced?.textContent).toContain("p_steward_one");
    expect(advanced?.textContent).toContain("quote-helper");
  });

  test("a state, a rung or a steward sent as null, empty or the wrong type is the header with none", async () => {
    // What breaks if this is deleted: a pill reading "null" or an empty steward chip, which says a
    // value exists and was withheld. The sibling is the header with all three.
    const bare = readHeaderFacts({ agent: without(agentWire(), "owner_name", "state", "leash_up_to", "created_at", "summary") });
    for (const noise of [null, "", "  ", 7, ["enabled"]]) {
      expect(
        readHeaderFacts({
          agent: { ...agentWire(), owner_name: noise, state: noise, leash_up_to: noise, created_at: noise, summary: noise, department: noise, template_name: noise },
        }),
      ).toEqual(bare);
    }
    expect(bare).toEqual({});
    expect(readHeaderFacts({ agent: agentWire() })).toEqual({
      summary: "Drafts a first answer to a pricing question.",
      ownerName: "Steward One",
      createdAt: "2019-03-01T09:00:00Z",
      state: "disabled",
      leashUpTo: "assisted",
    });
  });

  test("spend nothing records is left out rather than drawn as nought, and a recorded figure is drawn", async () => {
    // What breaks if this is deleted: "0.00" on every install, where nothing writes what a run
    // costs, read as an agent that cost nothing.
    const unrecorded = { ...body(), headline: { basis: "own", range: "30d", spend_minor: 0, runs: 0, recorded: false } };
    const quiet = await consoleAt("/agents/quote-helper", agentAnswers("quote-helper", unrecorded));
    expect(header(quiet.container).textContent).toContain(NOT_RECORDED);
    expect(header(quiet.container).textContent).not.toContain("0.00");

    const loud = await consoleAt("/agents/quote-helper", agentAnswers("quote-helper", body()));
    expect(header(loud.container).textContent).toContain("12.34");
  });
});

// ---------------------------------------------------------------------------- the dashboard

describe("the Dashboard", () => {
  test("its figures are the stats route's, and a route that fails draws its sentence and no number", async () => {
    // What breaks if this is deleted: figures made up in the browser while the stats package is not
    // there yet, or a strip of zeros for a route that answered 404.
    const answered = await consoleAt("/agents/quote-helper", agentAnswers("quote-helper", body()));
    const headline = () => answered.container.querySelector('[data-slot="kpi-strip"][aria-label="Spend, runs and messages"]');
    const strip = answered.container.querySelector('[data-slot="kpi-strip"][aria-label="This agent\'s figures"]');
    expect(headline()?.textContent).toContain("391");
    expect(headline()?.textContent).toContain("SGD 182.40");
    expect(strip?.textContent).toContain("1.8 s");
    expect(strip?.textContent).toContain("your runs");

    // The other period is the route's own second set, chosen from the switch.
    fireEvent.click([...answered.container.querySelectorAll("button")].find((one) => one.textContent === "7 days") as Element);
    expect(headline()?.textContent).toContain("97");

    const failed = await consoleAt(
      "/agents/quote-helper",
      agentAnswers("quote-helper", body(), {
        [`/api/v1${agentStatsApiPath("quote-helper")}`]: { status: 404, body: { message: "Nothing here." }, traceId: "trace-stats" },
      }),
    );
    const block = failed.container.querySelector('[data-slot="stats-strip"]');
    expect(block?.textContent).toContain(FIGURES_FAILED);
    expect(block?.textContent).toContain("trace-stats");
    expect(block?.textContent).not.toMatch(/391|182/);
  });

  test("a cost nothing records is not recorded yet with the route's reason, and never nought", async () => {
    // What breaks if this is deleted: "SGD 0.00" on every install, where nothing writes a run's
    // cost, read as an agent that cost nothing; or the reason the route gave lost on the way.
    const why = "nothing on the request path writes a run's cost to the spend ledger yet";
    const mounted = await consoleAt(
      "/agents/quote-helper",
      agentAnswers("quote-helper", body(), {
        [`/api/v1${agentStatsApiPath("quote-helper")}`]: { body: statsWire(null, [{ figure: "model_cost", why }]) },
      }),
    );
    const cards = [...mounted.container.querySelectorAll('[aria-label="Spend, runs and messages"] [data-slot="stat-card"]')];
    const cost = cards.find((one) => one.querySelector("dt")?.textContent === "Spend") as Element;
    expect(cost.textContent).toContain(NOT_RECORDED);
    expect(cost.textContent).not.toMatch(/0\.00/);
    const trigger = cost.querySelector("[aria-describedby]") as Element;
    expect(document.getElementById(trigger.getAttribute("aria-describedby") ?? "")?.textContent).toBe(why);
  });
});

// ------------------------------------------------------------------------------ the profile

describe("the Profile", () => {
  test("every act with no route is inert with its reason, and pressing one changes nothing", async () => {
    // What breaks if this is deleted: a control drawn live over a route that does not exist, or one
    // removed so the page hides that the act is coming. Each carries a sentence from
    // `agentActions.ts`, and pressing any of them leaves the address and the requests as they were.
    const mounted = await consoleAt("/agents/quote-helper/profile", agentAnswers("quote-helper", body()));
    const inert = [...mounted.container.querySelectorAll<HTMLButtonElement>(`[${UNAVAILABLE_MARK}]`)];
    // Four since 2026-09-29: adding a source and changing permissions start a draft of the agent
    // now, and a preview as a person is asked of its own route, so none of the three is among these.
    // Since 2026-10-06 choosing where the agent answers is the live card `where the agent answers`
    // below holds, a rung is changed in the leash block, and installing it into a group chat is the
    // Group chats card (M39.2.4.4), so changing who can find it is what is left.
    expect(inert.length).toBeGreaterThanOrEqual(1);
    const permissions = [...mounted.container.querySelectorAll<HTMLButtonElement>("button")].find(
      (one) => one.textContent === "Change permissions",
    );
    expect(permissions?.hasAttribute(UNAVAILABLE_MARK)).toBe(false);
    const reasons = new Set(Object.values(UNAVAILABLE).map((one) => one.reason));
    for (const control of inert) {
      expect(control.getAttribute("aria-disabled")).toBe("true");
      expect(reasons.has(document.getElementById(control.getAttribute("aria-describedby") ?? "")?.textContent ?? "")).toBe(true);
    }
    const before = mounted.idp.urls.length;
    for (const control of inert) {
      fireEvent.click(control);
    }
    expect(mounted.router.state.location.pathname).toBe("/agents/quote-helper/profile");
    expect(mounted.idp.urls.length).toBe(before);
  });

  test("the cards the Settings read is sent are absent for a reader sent no profile, with no heading left over", async () => {
    // What breaks if this is deleted: a Permissions card reading "unknown" to a member of the
    // audience, which is a statement that the agent has a ceiling they may not see.
    const member = await consoleAt("/agents/quote-helper/profile", agentAnswers("quote-helper", without(body(), "profile")));
    const text = member.container.textContent ?? "";
    expect(text).not.toContain("Permissions");
    expect(text).not.toContain("Approval setting");
    expect(text).not.toContain("tickets in the Support department");

    const admin = await consoleAt("/agents/quote-helper/profile", agentAnswers("quote-helper", body()));
    expect(admin.container.textContent).toContain("tickets in the Support department");
    expect(admin.container.querySelector(`#${leashRowId("ticket.draft_reply")}`)?.textContent).toContain("Draft a reply");
  });

  test("computer use is a sentence saying it is not offered, with no control, to every reader", async () => {
    // What breaks if this is deleted: M27.15.32. A switch for computer use drawn before any isolated
    // desktop runner exists, or the card dropped so nobody is told why it is missing. The card is
    // the same for a reader sent no profile, because it describes the product and not the agent.
    for (const answer of [body(), without(body(), "profile")]) {
      const mounted = await consoleAt("/agents/quote-helper/profile", agentAnswers("quote-helper", answer));
      const cards = [...mounted.container.querySelectorAll<HTMLElement>('[data-slot="section-card"]')].filter((card) =>
        [...card.querySelectorAll("h1, h2, h3, h4")].some((heading) => heading.textContent === COMPUTER_HEADING),
      );
      expect(cards).toHaveLength(1);
      const [card] = cards;
      expect(card?.querySelector('[data-slot="not-offered"]')?.textContent).toMatch(/^Not offered\./);
      expect(card?.querySelectorAll("button, input, select, a, [role='switch']")).toHaveLength(0);
    }
  });

  test("a profile sent malformed is read as no profile, and a sound one is carried whole", () => {
    // What breaks if this is deleted: a Profile drawn from half a ceiling, which is a permission
    // described with a clause missing.
    for (const noise of [null, [], "profile", 7]) {
      expect(readProfile({ profile: noise })).toBeNull();
    }
    expect(readProfile({ profile: { ...profileWire(), ceiling: { rows: "x" } } })?.ceiling).toBeUndefined();
    expect(readProfile({ profile: profileWire() })).toEqual({
      tier: "main",
      audienceLevel: "department",
      ceiling: {
        rows: "tickets in the Support department",
        reads: ["ticket subject"],
        readsLocked: false,
        tools: "It can search tickets and draft a reply.",
        largestEffect: "It drafts. It cannot send anything.",
        maxSideEffect: "draft",
      },
      tools: [{ name: "ticket.draft_reply", description: "Draft a reply", sideEffect: "draft", withinCeiling: true }],
      leash: [{ target: "ticket.draft_reply", rung: "assisted", configured: true, acts: true, takenOverAt: [] }],
    });
  });

  test("an action people keep taking over is drawn at the rung it is held to, with the days behind it", async () => {
    // What breaks if this is deleted: the Profile states a rung the agent is no longer held to
    // (M8.3.5), or draws a lowered rung with nothing saying why or when it comes back. Two days
    // alone lower nothing and still say when; an instant that is not one is not drawn.
    const days = ["2019-03-02T10:00:00Z", "2019-03-03T10:00:00Z", "2019-03-04T10:00:00Z"];
    const lowered = {
      ...profileWire(),
      leash: [
        {
          target: "ticket.draft_reply",
          rung: "assisted",
          rungs: ["assisted"],
          configured: true,
          acts: true,
          entries: [],
          lowered_to: "shadow",
          taken_over_at: [...days, "not a day"],
        },
      ],
    };
    const read = readProfile({ profile: lowered });
    expect(read?.leash[0]).toEqual({
      target: "ticket.draft_reply",
      rung: "assisted",
      configured: true,
      acts: true,
      loweredTo: "shadow",
      takenOverAt: days,
    });

    const mounted = await consoleAt(
      "/agents/quote-helper/profile",
      agentAnswers("quote-helper", { ...body(), profile: lowered }),
    );
    const row = mounted.container.querySelector(`#${leashRowId("ticket.draft_reply")}`);
    expect(row?.textContent).toContain(takenOverWords("assisted", "shadow", days));
    expect(row?.textContent).toContain(rungWords("shadow"));

    expect(takenOverWords("assisted", undefined, days.slice(1))).toMatch(/^People did this themselves on /);
    expect(takenOverWords("assisted", "shadow", days)).toContain(rungWords("assisted"));
  });
});

// ------------------------------------------------------------------------------- the about

describe("the About view", () => {
  test("it draws the API's steps in their numbers, and an action opens its approval setting on the Profile", async () => {
    // What breaks if this is deleted: a flow composed in the browser, which can describe something
    // the agent is not set up to do, or an action whose link lands on a Profile with no row for it.
    const mounted = await consoleAt("/agents/quote-helper/about", agentAnswers("quote-helper", body()));
    const about = mounted.container.querySelector('[data-slot="agent-about"]') as Element;
    expect([...about.querySelectorAll("ol > li")].map((one) => one.querySelector("span")?.textContent)).toEqual(["1", "2"]);
    const action = [...about.querySelectorAll("a")].find((one) => one.textContent?.startsWith("Draft a reply"));
    expect(action?.getAttribute("href")).toBe(`/agents/quote-helper/profile#${leashRowId("ticket.draft_reply")}`);
    expect(about.textContent).toContain("true of every agent");

    fireEvent.click(action as Element);
    await settled(mounted.container);
    await waitFor(() => {
      expect(mounted.container.querySelector(`#${leashRowId("ticket.draft_reply")}`)?.getAttribute("aria-current")).toBe("location");
    });
  });
});

describe("what an answer becomes", () => {
  test("every wire name the reader shares with the Python side is a field that side declares", () => {
    // What breaks if this is deleted: a reader and a model that stopped agreeing about a
    // name, which renders an agent with a fact silently missing. Each name is read off the
    // model that owns it, including `created_by`, the field the owner is deliberately not.
    const origins: readonly (readonly [string, string, string])[] = [
      ["agent_id", MODEL_MODULE, "AgentRecord"],
      ["display_name", MODEL_MODULE, "AgentRecord"],
      ["created_by", MODEL_MODULE, "AgentRecord"],
      ["owner_id", MODEL_MODULE, "AgentAudience"],
      ["summary", TEMPLATE_MODULE, "ManifestIdentity"],
      ["template_id", TEMPLATE_MODULE, "TemplateInstance"],
      ["template_version", TEMPLATE_MODULE, "TemplateInstance"],
      ["tab", WORKSPACE_MODULE, "WorkspaceTab"],
      ["purpose", WORKSPACE_MODULE, "WorkspaceTab"],
      ["read", WORKSPACE_MODULE, "WorkspaceTab"],
      ["source", TEMPLATE_MODULE, "FieldOwner"],
      ["set_by", TEMPLATE_MODULE, "FieldOwner"],
    ];
    for (const [name, module, model] of origins) {
      expect(backendModelFields(module, model), `${model}.${name}`).toContain(name);
    }
  });

  test("everything the API sends about the agent, its strip and its composition is carried", () => {
    // What breaks if this is deleted: every refusal below is satisfied by a reader that
    // returns nothing. This is the positive sibling for all of them.
    expect(read(body())).toEqual({
      agent: {
        agentId: "quote-helper",
        displayName: "Quote Helper",
        roleLine: "Drafts a first answer to a pricing question.",
        ownerId: "p_steward_one",
        createdBy: "p_builder",
        lineage: { templateId: "pricing-desk", version: 4 },
      },
      tabs: stripWire(),
      divergent: ["persona"],
      skills: [{ name: "ssl-renewal-runbook", digest: "a".repeat(64) }],
      connectors: { shown: [{ source: "ledger", presence: "attached" }], overflow: 0 },
      channels: [{ channel: "lark", profile: "card" }],
      figures: { basis: "own", range: "30d", spendMinor: 1234, runs: 7 },
      composition: [
        {
          part: partOf("persona"),
          path: "persona",
          template: '"Answer briefly."',
          instance: '"Answer briefly and name the price list."',
          source: SET_HERE,
          setBy: "steward-one",
        },
        {
          part: partOf("skills"),
          path: "skills",
          template: '["quote-draft"]',
          instance: '["quote-draft"]',
          source: SET_HERE,
          setBy: "steward-one",
        },
        {
          part: partOf("tier"),
          path: "tier",
          template: '"standard"',
          instance: '"standard"',
          source: FROM_TEMPLATE,
        },
      ],
    });
  });

  test("a composition row missing either side is not a row, and the diff is the one without it", () => {
    // What breaks if this is deleted: "skills, set here" with this agent's value blank, which
    // tells the reader the path exists, that somebody set it, and that they may not see what
    // to. Every way a side can be missing is tried, and each diff must be byte for byte the
    // diff of the rows that carried both.
    const complete = compositionWire();
    const withheldSides = [
      without(compositionWire()[1] as Record<string, unknown>, "instance"),
      { ...(compositionWire()[1] as Record<string, unknown>), template: null },
      { ...(compositionWire()[1] as Record<string, unknown>), instance: "" },
      { ...(compositionWire()[1] as Record<string, unknown>), template: ["quote-draft"] },
    ];

    const expected = diffMarkup([complete[0], complete[2]]);
    for (const withheld of withheldSides) {
      const markup = diffMarkup([complete[0], withheld, complete[2]]);
      expect(markup).toBe(expected);
      expect(markup).not.toContain("quote-draft");
    }
    expect(diffMarkup(complete)).toContain("quote-draft");
  });

  test("the answer the page holds has no field for what was left out", () => {
    // What breaks if this is deleted: `hiddenTabs` added to the answer to make a heading
    // better. The names are `brain.ops.jobs`' own list, read rather than copied.
    const forbidden = new Set(backendHiddenCountNames());
    const members = membersOf(parseConsoleSource("src/pages/agentQuery.ts"), "AgentWorkspaceAnswer");

    expect(members).toEqual([
      "agent",
      "tabs",
      "composition",
      "divergent",
      "skills",
      "connectors",
      "channels",
      "figures",
    ]);
    expect(members.filter((member) => forbidden.has(asPythonName(member)))).toEqual([]);
  });

  test("no shape the agent page holds has a field for a count of what was left out", () => {
    // What breaks if this is deleted: a `hiddenTools` or a `withheldCount` added to a shape to make a
    // card friendlier, which is the subtraction the list rules forbid arriving by another door. The
    // forbidden names are `brain.ops.jobs`' own list; the sibling proves the shapes were read at all.
    const forbidden = new Set(backendHiddenCountNames());
    const shapes: readonly (readonly [string, string])[] = [
      ["src/components/agentWorkspaceState.ts", "AgentIdentity"],
      ["src/components/agentWorkspaceState.ts", "WorkspaceTabView"],
      ["src/components/agentWorkspaceState.ts", "DiffRow"],
      ["src/pages/agents/agentDetailQuery.ts", "HeaderFacts"],
      ["src/pages/agents/agentDetailQuery.ts", "ProfileShown"],
      ["src/pages/agents/agentDetailQuery.ts", "CeilingShown"],
      ["src/pages/agents/agentDetailQuery.ts", "AboutShown"],
      ["src/pages/agents/agentStats.ts", "AgentStats"],
    ];
    const every = shapes.flatMap(([file, name]) => membersOf(parseConsoleSource(file), name));
    expect(every.length).toBeGreaterThan(20);
    expect(every.filter((member) => forbidden.has(asPythonName(member)))).toEqual([]);
  });
});


// --------------------------------------------------------------------- what a failure is

describe("what a failure looks like", () => {
  test("an agent the API will not describe is the API's own sentence, whichever kind of 404 it was", async () => {
    // What breaks if this is deleted: a page that tells a refusal from an address nothing serves. A
    // withheld agent answers with the DENIED body and an unknown agent with a bare 404; both must
    // reach the screen as the one sentence the taxonomy gives DENIED and ABSENT, with no header.
    const messages = backendPublicMessages();
    const sentence = messages["DENIED"];
    expect(sentence).toBeTruthy();
    expect(messages["ABSENT"]).toBe(sentence);

    const refused = await consoleAt("/agents/quote-helper", {
      "/api/v1/agents/quote-helper/workspace": { status: 404, body: { message: sentence }, traceId: "trace-refused" },
    });
    const unserved = await consoleAt("/agents/quote-helper", {
      "/api/v1/agents/quote-helper/workspace": { status: 404, body: { detail: "Not Found" } },
    });
    for (const { container } of [refused, unserved]) {
      expect(container.querySelector(".notice__body")?.textContent).toBe(sentence);
      expect(container.querySelector('[data-slot="detail-header"]')).toBeNull();
      expect(container.textContent).not.toContain("No such page");
    }
    expect(refused.container.querySelector(".notice__trace code")?.textContent).toBe("trace-refused");
  });

  test("an answer with no readable agent draws no page and composes no sentence about it", async () => {
    // What breaks if this is deleted: a body that is not a workspace rendered as an agent with no
    // name, or explained in a sentence nobody sent.
    for (const unreadable of [null, [], {}, { agent: "quote-helper" }, { agent: { agent_id: "quote-helper" } }]) {
      expect(readAgentWorkspace(unreadable)).toBeNull();
    }
    const idp = fakeIdentityProvider({
      api(url) {
        return new URL(url, CONSOLE_ORIGIN).pathname === "/api/v1/agents/quote-helper/workspace"
          ? new Response("{}", { status: 200, headers: { "content-type": "application/json" } })
          : null;
      },
    });
    const loaded = await loadConsole({ idp });
    await signIn(loaded);
    const { routes } = await import("../src/App");
    const router = createMemoryRouter(routes, { initialEntries: ["/agents/quote-helper"] });
    const { container } = render(<RouterProvider router={router} />);
    await waitFor(() => {
      expect(idp.urls.some((url) => url.endsWith("/workspace"))).toBe(true);
    });
    await waitFor(() => {
      expect(container.querySelector('[data-slot="loading-state"]')).toBeNull();
    });
    expect(container.querySelector('[data-slot="detail-header"]')).toBeNull();
    expect(container.querySelector("main .notice")).toBeNull();
  });

  test("a count or a capability the API sends reaches nothing on the page", async () => {
    // What breaks if this is deleted: "showing 5 of 7 tabs", or a tab's required capability in an
    // attribute. A route serialising `WorkspaceTab` whole would send its `read`, which names the
    // grant each tab needs, and a total beside a narrowed strip is the subtraction.
    const leaky = {
      ...body({ ...agentWire(), hidden_count: 4700 }),
      tabs: stripWire().map((tab) => ({ ...tab, read: { screen: `agent_workspace.${String(tab["tab"])}`, requires: "read:memory" } })),
      total: 4700,
      hidden: 4700,
      of_total: "4700",
    };
    expect(JSON.stringify(read(leaky))).not.toMatch(/4700|read:memory|agent_workspace/);
    for (const view of ["", "/profile", "/about"]) {
      const { container } = await consoleAt(`/agents/quote-helper${view}`, agentAnswers("quote-helper", leaky));
      expect(container.innerHTML, view).not.toMatch(/4700|read:memory|agent_workspace\./);
    }
  });
});

// ------------------------------------------------------------ moving between agents and views

describe("moving between agents and views", () => {
  const answers: Record<string, Answer> = {
    ...agentAnswers("quote-helper", body()),
    ...agentAnswers("rota-helper", body(agentWire("rota-helper", "Rota Helper"))),
  };

  test("another agent at the same route opens on its own Dashboard", async () => {
    // What breaks if this is deleted: one agent's open view, or a number from its figures, turning up
    // on the next agent opened from the same page.
    const mounted = await consoleAt("/agents/quote-helper/about", answers);
    expect(currentView(mounted.container)).toBe("About");
    await go(mounted, "/agents/rota-helper");
    await waitFor(() => {
      expect(header(mounted.container).querySelector("h1")?.textContent).toBe("Rota Helper");
    });
    expect(currentView(mounted.container)).toBe("Dashboard");
  });

  test("moving between one agent's views asks for the workspace once", async () => {
    // What breaks if this is deleted: a page that reads the whole workspace again for every view,
    // because the view was put in the component's key rather than in the address it reads.
    const mounted = await consoleAt("/agents/quote-helper/profile", answers);
    await go(mounted, "/agents/quote-helper/about");
    await go(mounted, "/agents/quote-helper/settings");
    expect(currentView(mounted.container)).toBe("Profile");
    expect(workspaceRequests(mounted.idp)).toEqual(["/api/v1/agents/quote-helper/workspace"]);
  });
});

// ------------------------------------------------------------------------ where it answers

const CHANNELS_LIFECYCLE_API = "/api/v1/agents/quote-helper/lifecycle";
const CHANNELS_API = "/api/v1/agents/quote-helper/channels";

/** `LifecycleView` on the wire, for the steward of an agent answering on the console and Lark. */
function lifecycleWire(overrides: Readonly<Record<string, unknown>> = {}): Record<string, unknown> {
  return {
    agent_id: "quote-helper",
    display_name: "Quote Helper",
    state: "enabled",
    owner_id: "p_steward_one",
    effective_hash: "a".repeat(64),
    may_change: false,
    may_duplicate: false,
    duplicate_unavailable: null,
    level: "department",
    may_publish: false,
    channels: ["console", "lark"],
    channel_choices: [
      { name: "console", label: "Web console" },
      { name: "lark", label: "Lark" },
      { name: "whatsapp", label: "WhatsApp" },
    ],
    channels_note: "An agent with no channel ticked answers nowhere: nobody can ask it anything until one is.",
    may_change_channels: true,
    ...overrides,
  };
}

function channelPosts(idp: FakeIdp): { readonly path: string; readonly body: unknown }[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST" && new URL(call.url, CONSOLE_ORIGIN).pathname === CHANNELS_API)
    .map((call) => ({ path: new URL(call.url, CONSOLE_ORIGIN).pathname, body: JSON.parse(String(call.init?.body ?? "null")) }));
}

function channelsCard(container: HTMLElement): Element | null {
  return (
    [...container.querySelectorAll('[data-slot="section-card"]')].find(
      (card) => card.querySelector("h2")?.textContent === WHERE_IT_ANSWERS,
    ) ?? null
  );
}

async function profileWith(lifecycle: Answer, extra: Readonly<Record<string, Answer>> = {}): Promise<Mounted> {
  const mounted = await consoleAt(
    "/agents/quote-helper/profile",
    agentAnswers("quote-helper", body(), { [CHANNELS_LIFECYCLE_API]: lifecycle, ...extra }),
  );
  await waitFor(() => {
    if (!mounted.idp.urls.some((url) => new URL(url, CONSOLE_ORIGIN).pathname === CHANNELS_LIFECYCLE_API)) {
      throw new Error("the channels have not been asked for");
    }
  });
  return mounted;
}

// ------------------------------------------------------------------------ group chats (M39.2.4.4)

const GROUPS_API = "/api/v1/agents/quote-helper/groups";
const GROUP_REMOVAL_API = "/api/v1/agents/quote-helper/groups/removal";

/** `AgentGroupsView` on the wire: one install, and one chat the bot is in that it could go into. */
function groupsWire(overrides: Readonly<Record<string, unknown>> = {}): Record<string, unknown> {
  return {
    agent_id: "quote-helper",
    installs: [
      { id: "11111111-1111-4111-8111-000000000001", channel: "lark", room_ref: "oc_sales", name: "Sales team", present: true, answering: true, installed_at: "2019-03-04T09:00:00Z" },
    ],
    rooms: [{ channel: "lark", room_ref: "oc_pricing", name: "Pricing desk" }],
    ...overrides,
  };
}

function groupPosts(idp: FakeIdp): { readonly path: string; readonly body: unknown }[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST" && new URL(call.url, CONSOLE_ORIGIN).pathname.startsWith(GROUPS_API))
    .map((call) => ({ path: new URL(call.url, CONSOLE_ORIGIN).pathname, body: JSON.parse(String(call.init?.body ?? "null")) }));
}

function groupsCard(container: HTMLElement): HTMLElement | null {
  const found = [...container.querySelectorAll('[data-slot="section-card"]')].find((card) => card.querySelector("h2")?.textContent === GROUP_CHATS);
  return (found as HTMLElement | undefined) ?? null;
}

async function withGroups(groups: Answer, extra: Readonly<Record<string, Answer>> = {}): Promise<{ readonly mounted: Mounted; readonly card: HTMLElement }> {
  const mounted = await profileWith({ body: lifecycleWire() }, { [GROUPS_API]: groups, ...extra });
  const card = await waitFor(() => {
    const found = groupsCard(mounted.container);
    if (found === null) {
      throw new Error("no card");
    }
    return found;
  });
  return { mounted, card };
}

describe("group chats", () => {
  test("a chat the bot is in is installed and an install taken out, each through a confirmation that sends the chat it named", async () => {
    // What breaks if this is deleted: the one live control for M39.2.4.4, or a write sent before the
    // person agreed to it, or one naming a chat other than the one chosen.
    const { mounted, card } = await withGroups({ body: groupsWire() }, { [GROUP_REMOVAL_API]: { body: groupsWire({ installs: [] }) } });
    expect(card.textContent).toContain("Sales team");
    fireEvent.change(within(card).getByLabelText(CHOOSE_A_CHAT), { target: { value: "lark:oc_pricing" } });
    fireEvent.click(within(card).getByRole("button", { name: INSTALL_HERE }));
    const asking = await screen.findByRole("alertdialog", { name: INSTALL_QUESTION("Pricing desk") });
    expect(groupPosts(mounted.idp)).toEqual([]);
    await act(async () => {
      fireEvent.click(within(asking).getByRole("button", { name: "Install it" }));
    });
    await waitFor(() => {
      expect(groupPosts(mounted.idp)).toEqual([{ path: GROUPS_API, body: { channel: "lark", room_ref: "oc_pricing" } }]);
    });

    fireEvent.click(within(groupsCard(mounted.container) as HTMLElement).getByRole("button", { name: "Take this agent out of Sales team" }));
    const removing = await screen.findByRole("alertdialog", { name: REMOVE_QUESTION("Sales team") });
    await act(async () => {
      fireEvent.click(within(removing).getByRole("button", { name: "Take it out" }));
    });
    await waitFor(() => {
      expect(groupPosts(mounted.idp)[1]).toEqual({ path: GROUP_REMOVAL_API, body: { install_id: "11111111-1111-4111-8111-000000000001" } });
    });
  });

  test("a reader the groups route refuses is shown no card, and an agent in no chat says how one is offered", async () => {
    // What breaks if this is deleted: a heading over nothing for somebody who may not install, which
    // says there are chats they may not see, or an empty card a steward reads as still loading.
    const refused = await profileWith({ body: lifecycleWire() }, { [GROUPS_API]: { status: 404, body: { message: "No such agent." } } });
    await waitFor(() => {
      expect(refused.idp.urls.some((url) => new URL(url, CONSOLE_ORIGIN).pathname === GROUPS_API)).toBe(true);
    });
    expect(groupsCard(refused.container)).toBeNull();
    const { card } = await withGroups({ body: groupsWire({ installs: [], rooms: [] }) });
    expect(card.textContent).toContain(NO_GROUPS);
    expect(within(card).queryByRole("button", { name: INSTALL_HERE })).toBeNull();
  });

  test("an install the route refuses is its own sentence, and a chat the bot left says so", async () => {
    // What breaks if this is deleted: a 409 drawn as installed, or an install in a chat the bot has
    // left drawn as if it still answers there.
    const { card } = await withGroups(
      { body: groupsWire({ installs: [{ id: "i-1", channel: "lark", room_ref: "oc_old", name: "Old chat", present: false, answering: false, installed_at: "2019-03-04T09:00:00Z" }] }) },
      { [`POST ${GROUPS_API}`]: { status: 409, body: { outcome: "refused", sentence: "That group chat could not take this agent." } } },
    );
    expect(card.textContent).toContain(THE_BOT_LEFT);
    // Switched off the channel, it is shown paused rather than live.
    expect(card.textContent).toContain(PAUSED);
    fireEvent.change(within(card).getByLabelText(CHOOSE_A_CHAT), { target: { value: "lark:oc_pricing" } });
    fireEvent.click(within(card).getByRole("button", { name: INSTALL_HERE }));
    const asking = await screen.findByRole("alertdialog", { name: INSTALL_QUESTION("Pricing desk") });
    await act(async () => {
      fireEvent.click(within(asking).getByRole("button", { name: "Install it" }));
    });
    await screen.findByText("That group chat could not take this agent.");
  });
});

describe("where the agent answers", () => {
  test("the steward sees the channels it answers on and switches them through a confirmation that sends what was drawn", async () => {
    // What breaks if this is deleted: the one live control for M13.7.4's switch, so a steward has no
    // way to make an agent answer on WhatsApp, or a switch sent without the channels the card drew,
    // so the route's stale-page check compares against a guess. The positive case of every refusal
    // below.
    const mounted = await profileWith(
      { body: lifecycleWire() },
      { [CHANNELS_API]: { body: lifecycleWire({ channels: ["console", "whatsapp"] }) } },
    );
    const card = await waitFor(() => {
      const found = channelsCard(mounted.container);
      if (found === null) {
        throw new Error("no card");
      }
      return found;
    });
    expect([...card.querySelectorAll('[data-slot="agent-channels"] > :not(svg)')].map((chip) => chip.textContent)).toEqual([
      "Web console",
      "Lark",
    ]);

    fireEvent.click(within(card as HTMLElement).getByRole("button", { name: CHANGE_CHANNELS }));
    const dialog = await screen.findByRole("alertdialog", { name: CHANNELS_QUESTION("Quote Helper") });
    const box = (label: string) => within(dialog).getByRole("checkbox", { name: label }) as HTMLInputElement;
    expect([box("Web console").checked, box("Lark").checked, box("WhatsApp").checked]).toEqual([true, true, false]);
    expect(channelPosts(mounted.idp)).toEqual([]);

    fireEvent.click(box("Lark"));
    fireEvent.click(box("WhatsApp"));
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: SAVE_CHANNELS }));
    });
    await screen.findByText(CHANNELS_DONE);
    expect(channelPosts(mounted.idp)).toEqual([
      { path: CHANNELS_API, body: { channels: ["console", "whatsapp"], expected: ["console", "lark"] } },
    ]);
  });

  test("a reader the route says may not switch them sees where it answers and no control", async () => {
    // What breaks if this is deleted: a button offered to an administrator of something else, whose
    // press the route refuses as the one 404 after they agreed to it.
    const mounted = await profileWith({ body: lifecycleWire({ may_change_channels: false }) });
    const card = await waitFor(() => {
      const found = channelsCard(mounted.container);
      if (found === null) {
        throw new Error("no card");
      }
      return found;
    });
    expect(card.textContent).toContain("Lark");
    expect(within(card as HTMLElement).queryByRole("button", { name: CHANGE_CHANNELS })).toBeNull();
  });

  test("a reader the lifecycle route refuses is shown no card, not an empty one", async () => {
    // What breaks if this is deleted: a heading over nothing for a member of the audience, which says
    // there is something about this agent they may not see. DENIED and ABSENT are one answer.
    const mounted = await profileWith({ status: 404, body: { message: "No such agent." } });
    await waitFor(() => {
      expect(mounted.container.querySelector('[data-slot="agent-profile"]')).not.toBeNull();
    });
    expect(channelsCard(mounted.container)).toBeNull();
  });

  test("an agent on no channel says nobody can ask it, rather than drawing an empty row", async () => {
    // What breaks if this is deleted: a mute agent drawn as a card with nothing in it, which a steward
    // reads as a page still loading rather than an agent nobody can reach.
    const mounted = await profileWith({ body: lifecycleWire({ channels: [] }) });
    await waitFor(() => {
      expect(channelsCard(mounted.container)?.textContent).toContain(ANSWERS_NOWHERE);
    });
  });

  test("a stale page is the route's own sentence, and nothing is said to have changed", async () => {
    // What breaks if this is deleted: a 409 drawn as done, so a steward believes a channel is off
    // that somebody else has just switched back on.
    const sentence = "This agent changed after you opened it, so nothing was changed. Look again and choose.";
    const mounted = await profileWith(
      { body: lifecycleWire() },
      { [CHANNELS_API]: { status: 409, body: { outcome: "moved", sentence } } },
    );
    const card = await waitFor(() => {
      const found = channelsCard(mounted.container);
      if (found === null) {
        throw new Error("no card");
      }
      return found;
    });
    fireEvent.click(within(card as HTMLElement).getByRole("button", { name: CHANGE_CHANNELS }));
    const dialog = await screen.findByRole("alertdialog", { name: CHANNELS_QUESTION("Quote Helper") });
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: SAVE_CHANNELS }));
    });
    await screen.findByText(sentence);
    expect(screen.queryByText(CHANNELS_DONE)).toBeNull();
  });

  test("the card reads and sends exactly the fields the API document declares", () => {
    // What breaks if this is deleted: a field renamed on one side, read as absent on the other, so the
    // card shows an agent on no channel and offers a steward no button.
    const view = declaredResponseSchema("/api/v1/agents/{agent_id}/lifecycle", "get");
    expect(declaredPropertyNames(view)).toEqual(Object.keys(lifecycleWire()).sort());
    expect(declaredPropertyNames(declaredResponseSchema("/api/v1/agents/{agent_id}/channels", "post"))).toEqual(
      declaredPropertyNames(view),
    );
    expect(declaredPropertyNames(declaredRequestBodySchema("/api/v1/agents/{agent_id}/channels", "post"))).toEqual([
      "channels",
      "expected",
    ]);
  });
});
