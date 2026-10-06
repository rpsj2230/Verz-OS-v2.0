/**
 * One agent's header and figures: the role line, the sections beside the views, the period that
 * survives a trip to the Profile, the three headline figures over four periods, the cost per person
 * and the month against the agent's own budget.
 *
 * **Mounted through the application's own route table**, signed in through the real session modules
 * and answered by a stand-in API that records every request, as `agent-page.test.tsx` mounts it, so a
 * route or a reader deleted fails here rather than passing a component rendered on its own.
 *
 * **Every absence has a sibling proving the thing is drawn when it is sent**: no projection without a
 * budget, no cost list without a recorded cost, and no budget control for a reader of their own spend.
 *
 * Task ids: M39.1.2.1, M39.1.2.2, M39.1.2.3, M39.1.3.1, M39.1.3.2, M39.1.3.3, M39.1.3.4
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { CONVERSATIONS_SECTION, CONVERSATIONS_TAB, SECTIONS_LABEL, viewAddress } from "../src/pages/agents/AgentDetailPage";
import { HEADLINE_LABEL, MESSAGES_LABEL } from "../src/pages/agents/AgentDashboard";
import {
  BUDGET_FORMAT,
  COST_BY_PERSON,
  MONTH_HEADING,
  NO_BUDGET,
  OVER_BUDGET,
  SET_BUDGET,
  agentBudgetApiPath,
  minorOf,
} from "../src/pages/agents/AgentSpend";
import { AGENT_PERIODS, agentStatsApiPath, rangeWords } from "../src/pages/agents/agentStats";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { apiDocument, declaredPropertyNames, declaredProperty, declaredResponseSchema } from "./support/openapi";
import { installRadixStubs } from "./support/radix";

const CONSOLE_ORIGIN = "https://console.test";
const AGENT = "quote-helper";

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/Agent");
}, 60_000);

// ------------------------------------------------------------------------------- fixtures

function agentWire(extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    agent_id: AGENT,
    display_name: "Quote Helper",
    summary: "Drafts a first answer to a pricing question.",
    owner_id: "p_steward_one",
    owner_name: "Steward One",
    template_id: "pricing-desk",
    template_version: 4,
    template_name: "Pricing desk",
    department: "sales",
    created_at: "2019-03-01T09:00:00Z",
    state: "enabled",
    leash_up_to: "assisted",
    ...extra,
  };
}

function workspaceWire(agent: Record<string, unknown> = agentWire(), tabs: readonly string[] = ["automations", "settings"]): unknown {
  return {
    agent,
    tabs: tabs.map((tab) => ({ tab, label: tab, purpose: `What the ${tab} tab is for.` })),
    composition: [],
    skills: [],
    connectors: { shown: [], overflow: 0 },
    channels: [],
    headline: { basis: "everyone", range: "30d", spend_minor: 1234, runs: 7, recorded: true },
  };
}

function period(range: string, runs: number, messages: number, cost: number | null, callers: unknown[] = []): unknown {
  return {
    range,
    since: "2019-02-02T00:00:00Z",
    until: "2019-03-04T12:00:00Z",
    runs,
    messages,
    answered: runs,
    nothing_returned: 0,
    p50_latency_ms: 900,
    cost_minor: cost,
    callers,
  };
}

function statsWire(options: { basis?: string; projection?: unknown; recorded?: boolean } = {}): unknown {
  const recorded = options.recorded ?? true;
  const cost = (value: number): number | null => (recorded ? value : null);
  const callers = (heavy: number, light: number): unknown[] =>
    recorded
      ? [
          { principal_id: "p_heavy", name: "Heavy Person", spend_minor: heavy },
          { principal_id: "p_light", name: "Light Person", spend_minor: light },
        ]
      : [];
  return {
    agent_id: AGENT,
    basis: options.basis ?? "everyone",
    cost_basis: options.basis ?? "everyone",
    currency: "SGD",
    last_active: "2019-03-04T09:42:00Z",
    at_least: false,
    periods: [
      period("7d", 11, 9, cost(700), callers(500, 200)),
      period("30d", 41, 30, cost(2400), callers(1800, 600)),
      period("90d", 121, 90, cost(7200), callers(5400, 1800)),
      period("mtd", 33, 25, cost(1900), callers(1400, 500)),
    ],
    unrecorded: recorded ? [] : [{ figure: "model_cost", why: "Nothing records a run's cost yet." }],
    projection: options.projection ?? null,
  };
}

interface Answer {
  readonly status?: number;
  readonly body: unknown;
}

interface Mounted {
  readonly container: HTMLElement;
  readonly idp: FakeIdp;
  readonly router: ReturnType<typeof createMemoryRouter>;
}

async function consoleAt(path: string, answers: Readonly<Record<string, Answer>>): Promise<Mounted> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      const method = init?.method ?? "GET";
      const pathname = new URL(url, CONSOLE_ORIGIN).pathname;
      const answer = answers[`${method} ${pathname}`] ?? (method === "GET" ? answers[pathname] : undefined);
      if (answer === undefined) {
        return null;
      }
      return new Response(JSON.stringify(answer.body), {
        status: answer.status ?? 200,
        headers: { "content-type": "application/json" },
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

function answers(stats: unknown = statsWire(), workspace: unknown = workspaceWire()): Record<string, Answer> {
  return {
    [`/api/v1/agents/${AGENT}/workspace`]: { body: workspace },
    [`/api/v1/agents/${AGENT}/about`]: { body: { agent_id: AGENT, summary: "x", steps: [], never: [] } },
    [`/api/v1${agentStatsApiPath(AGENT)}`]: { body: stats },
    [`/api/v1/agents/${AGENT}/automations`]: { body: { items: [], result_rule: "What each run returned." } },
    "/api/v1/routing/rungs": { body: { items: [], next_cursor: null, truncated: false } },
  };
}

function statsRequests(idp: FakeIdp): number {
  return idp.urls.filter((url) => new URL(url, CONSOLE_ORIGIN).pathname.endsWith("/stats")).length;
}

function strip(container: HTMLElement, label: string): Element {
  const found = container.querySelector(`[aria-label="${label}"]`);
  if (found === null) {
    throw new Error(`No strip labelled ${label} was drawn.`);
  }
  return found;
}

/** Press the confirmation's own button, after checking it names the amount being set. */
async function confirm(amount: string): Promise<void> {
  const dialog = await waitFor(() => {
    const found = document.querySelector('[role="alertdialog"]');
    if (found === null) {
      throw new Error("no confirmation opened");
    }
    return found;
  });
  expect(dialog.textContent).toContain(amount);
  const button = [...dialog.querySelectorAll("button")].find((one) => one.textContent === SET_BUDGET);
  await act(async () => {
    fireEvent.click(button as Element);
  });
}

async function choose(container: HTMLElement, range: string): Promise<void> {
  const button = [...container.querySelectorAll('[data-slot="agent-dashboard"] button')].find(
    (one) => one.textContent === rangeWords(range),
  );
  if (button === undefined) {
    throw new Error(`No period switch reads ${rangeWords(range)}.`);
  }
  await act(async () => {
    fireEvent.click(button);
  });
}

// ------------------------------------------------------------------------------ the header

describe("the header's role line", () => {
  test("it says what the agent is for, its department, its steward and its template by name and version", async () => {
    // What breaks if this is deleted: a header naming the agent and nothing about what it is for or
    // where it came from, which is M39.1.2.1's role line, owner and lineage.
    const mounted = await consoleAt(`/agents/${AGENT}`, answers());
    const line = mounted.container.querySelector('[data-slot="role-line"]');
    expect(line?.textContent).toContain("Drafts a first answer to a pricing question.");
    expect(line?.textContent).toContain("sales · steward Steward One · from Pricing desk, version 4");
    // The avatar is the agent's initials, beside its name.
    expect(mounted.container.querySelector('[data-slot="detail-header"] [aria-hidden]')?.textContent).toBe("QH");
  });

  test("a part the API did not send is left out, and a header sent none of them has no role line", async () => {
    // The sibling of the test above: the line is drawn only from what was sent, never as separators
    // around nothing, and a template with no name is still read as a template and a version.
    const bare = agentWire({ summary: null, department: null, template_name: null });
    const mounted = await consoleAt(`/agents/${AGENT}`, answers(statsWire(), workspaceWire(bare)));
    expect(mounted.container.querySelector('[data-slot="role-line"]')?.textContent).toBe(
      "steward Steward One · from a template, version 4",
    );
    const nothing = agentWire({ summary: null, department: null, owner_name: null, template_version: null, template_id: null });
    const blank = await consoleAt(`/agents/${AGENT}`, answers(statsWire(), workspaceWire(nothing)));
    expect(blank.container.querySelector('[data-slot="role-line"]')).toBeNull();
  });

  test("the header's names are names the workspace route declares", () => {
    // What breaks if this is deleted: the reader asking for a department or a template name the
    // route never sends, which renders a role line silently missing its middle.
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    expect(paths).toContain("/api/v1/agents/{agent_id}/workspace");
    const agent = declaredProperty(declaredResponseSchema("/api/v1/agents/{agent_id}/workspace", "get"), "agent");
    expect(declaredPropertyNames(agent)).toEqual(expect.arrayContaining(["department", "summary", "template_name", "template_version"]));
  });
});

describe("the sections beside the views", () => {
  test("a section the API's strip holds and this page draws is listed at its own address", async () => {
    // What breaks if this is deleted: M39.1.2.2's sections reachable only by typing an address.
    const mounted = await consoleAt(`/agents/${AGENT}`, answers());
    const trigger = [...mounted.container.querySelectorAll("button")].find((one) => one.textContent?.includes(SECTIONS_LABEL));
    expect(trigger).toBeDefined();
    await act(async () => {
      fireEvent.pointerDown(trigger as Element, { button: 0 });
      fireEvent.click(trigger as Element);
    });
    const link = await waitFor(() => {
      const found = [...document.querySelectorAll("a")].find((one) => one.textContent === "Automations");
      if (found === undefined) {
        throw new Error("the Automations section is not listed");
      }
      return found;
    });
    expect(link.getAttribute("href")).toBe(viewAddress(AGENT, "automations"));
  });

  test("a reader whose strip holds no drawn section is offered their own conversations and no other section", async () => {
    // The sibling: a section the strip did not list is a section this reader may not open, so the
    // menu names none of them. Conversations is the one item it always holds, because a person's
    // own threads with an agent need no grant (`brain.agent_conversation_routes`), which is also
    // why the menu is never a heading over nothing. What breaks if this is deleted: a section the
    // reader's strip withholds listed beside the views, or the reader's own conversations reachable
    // only by typing an address.
    const mounted = await consoleAt(`/agents/${AGENT}`, answers(statsWire(), workspaceWire(agentWire(), ["settings"])));
    const trigger = [...mounted.container.querySelectorAll("button")].find((one) => one.textContent?.includes(SECTIONS_LABEL));
    expect(trigger).toBeDefined();
    await act(async () => {
      fireEvent.pointerDown(trigger as Element, { button: 0 });
      fireEvent.click(trigger as Element);
    });
    const items = await waitFor(() => {
      const found = [...document.querySelectorAll('[role="menuitem"]')];
      if (found.length === 0) {
        throw new Error("the Sections menu did not open");
      }
      return found;
    });
    expect(items.map((one) => one.textContent)).toEqual([CONVERSATIONS_SECTION]);
    expect(items[0]?.getAttribute("href")).toBe(viewAddress(AGENT, CONVERSATIONS_TAB));
  });
});

// ------------------------------------------------------------------------------ the figures

describe("the headline figures", () => {
  test("spend, runs and messages lead the Dashboard, and an automation's run is not a message", async () => {
    // What breaks if this is deleted: M39.1.3.1's three figures back inside a report nobody opens.
    const mounted = await consoleAt(`/agents/${AGENT}`, answers());
    const headline = strip(mounted.container, HEADLINE_LABEL);
    expect(headline.textContent).toContain("Spend");
    expect(headline.textContent).toContain("SGD 24.00");
    expect(headline.textContent).toContain("41");
    expect(headline.textContent).toContain(MESSAGES_LABEL);
    expect(headline.textContent).toContain("30");
  });

  test("the period switch offers seven, thirty and ninety days and the month to date, and each shows its own figures", async () => {
    // What breaks if this is deleted: M39.1.3.2's selector offering two windows, or a window whose
    // figures are another window's.
    const mounted = await consoleAt(`/agents/${AGENT}`, answers());
    const labels = [...mounted.container.querySelectorAll('[data-slot="agent-dashboard"] [role="group"] button')].map((one) => one.textContent);
    expect(labels).toEqual(AGENT_PERIODS.map((one) => rangeWords(one)));
    expect(labels).toContain("Month to date");
    await choose(mounted.container, "90d");
    expect(strip(mounted.container, HEADLINE_LABEL).textContent).toContain("121");
    await choose(mounted.container, "mtd");
    expect(strip(mounted.container, HEADLINE_LABEL).textContent).toContain("SGD 19.00");
  });

  test("a period chosen on the Dashboard is still chosen after a trip to the Profile, and nothing is asked twice", async () => {
    // What breaks if this is deleted: M39.1.2.3, the right pane switching views and losing what the
    // reader had chosen, or the page asking the API again for every view change.
    const mounted = await consoleAt(`/agents/${AGENT}`, answers());
    await choose(mounted.container, "90d");
    const asked = statsRequests(mounted.idp);
    await go(mounted, viewAddress(AGENT, "profile"));
    await go(mounted, viewAddress(AGENT, "dashboard"));
    const pressed = mounted.container.querySelector('[data-slot="agent-dashboard"] [role="group"] [aria-pressed="true"]');
    expect(pressed?.textContent).toBe("90 days");
    expect(strip(mounted.container, HEADLINE_LABEL).textContent).toContain("121");
    // The Dashboard asks for its figures when it is drawn again, and once only.
    expect(statsRequests(mounted.idp)).toBe(asked + 1);
  });
});

describe("cost by person", () => {
  test("a reader of everybody's spend is shown each person's cost, heaviest first, for the period chosen", async () => {
    // What breaks if this is deleted: M39.1.3.3's heavy user invisible on the agent's own page.
    const mounted = await consoleAt(`/agents/${AGENT}`, answers());
    const rows = () => [...mounted.container.querySelectorAll('[data-slot="cost-by-person"] li')].map((one) => one.textContent);
    expect(rows()).toEqual(["Heavy PersonSGD 18.00", "Light PersonSGD 6.00"]);
    await choose(mounted.container, "7d");
    expect(rows()).toEqual(["Heavy PersonSGD 5.00", "Light PersonSGD 2.00"]);
  });

  test("with no run's cost recorded, no cost list is drawn", async () => {
    // The sibling: a list of noughts would read as a measurement nobody made.
    const mounted = await consoleAt(`/agents/${AGENT}`, answers(statsWire({ recorded: false })));
    expect(mounted.container.textContent).not.toContain(COST_BY_PERSON);
  });
});

describe("the month against the agent's own budget", () => {
  test("the projection is drawn when the API sends one, and says when the month ends over budget", async () => {
    // What breaks if this is deleted: M39.1.3.4, the projection the route computes never drawn.
    const projection = { spent_minor: 1900, projected_minor: 3100, ceiling_minor: 3000, over_ceiling: true };
    const mounted = await consoleAt(`/agents/${AGENT}`, answers(statsWire({ projection })));
    const drawn = mounted.container.querySelector('[data-slot="projection"]');
    expect(drawn?.textContent).toContain("SGD 19.00");
    expect(drawn?.textContent).toContain("SGD 31.00");
    expect(drawn?.textContent).toContain("SGD 30.00");
    expect(mounted.container.textContent).toContain(OVER_BUDGET);
  });

  test("with no budget set, a reader of everybody's spend is told so and can set one, in a format said first", async () => {
    // What breaks if this is deleted: an agent whose projection can never be drawn because nothing
    // on the page sets the budget it is projected against.
    const saved = { agent_id: AGENT, ceiling_minor: 25050, version: 1, effective_from: "2019-03-04T12:00:00Z" };
    const mounted = await consoleAt(`/agents/${AGENT}`, {
      ...answers(),
      [`PUT /api/v1${agentBudgetApiPath(AGENT)}`]: { body: saved },
    });
    expect(mounted.container.textContent).toContain(NO_BUDGET);
    expect(mounted.container.textContent).toContain(BUDGET_FORMAT);
    const form = mounted.container.querySelector('[data-slot="budget-form"]') as HTMLFormElement;
    const [amount, reason] = [...form.querySelectorAll("input")];
    await act(async () => {
      fireEvent.change(amount as Element, { target: { value: "250.50" } });
      fireEvent.change(reason as Element, { target: { value: "The pricing team's month." } });
      fireEvent.submit(form);
    });
    // Nothing is sent until the confirmation, which names the amount, is pressed.
    expect(mounted.idp.calls.find((one) => one.init?.method === "PUT")).toBeUndefined();
    await confirm("SGD 250.50");
    const put = mounted.idp.calls.find((one) => one.init?.method === "PUT");
    expect(put?.url).toContain(agentBudgetApiPath(AGENT));
    expect(JSON.parse(String(put?.init?.body))).toEqual({ ceiling_minor: 25050, reason: "The pricing team's month." });
  });

  test("a refusal is the API's sentence, and a reader of their own spend is offered no budget at all", async () => {
    // The siblings: the server decides who may set a budget and says which role would let them, and
    // the month's projection and control are withheld from a reader whose figures are their own.
    const said = "Setting this agent's monthly budget needs the budget administrator's role over its department.";
    const refused = await consoleAt(`/agents/${AGENT}`, {
      ...answers(),
      [`PUT /api/v1${agentBudgetApiPath(AGENT)}`]: { status: 403, body: { message: said } },
    });
    const form = refused.container.querySelector('[data-slot="budget-form"]') as HTMLFormElement;
    const [amount, reason] = [...form.querySelectorAll("input")];
    await act(async () => {
      fireEvent.change(amount as Element, { target: { value: "not money" } });
      fireEvent.submit(form);
    });
    expect(form.querySelector('[role="alert"]')?.textContent).toBe(BUDGET_FORMAT);
    await act(async () => {
      fireEvent.change(amount as Element, { target: { value: "100" } });
      fireEvent.change(reason as Element, { target: { value: "A month." } });
      fireEvent.submit(form);
    });
    await confirm("SGD 100.00");
    await waitFor(() => {
      expect(form.querySelector('[role="alert"]')?.textContent).toBe(said);
    });

    const own = await consoleAt(`/agents/${AGENT}`, answers(statsWire({ basis: "own" })));
    expect(own.container.textContent).not.toContain(MONTH_HEADING);
    expect(own.container.textContent).not.toContain(SET_BUDGET);
  });

  test("an amount is read in the currency's major units to two places and nothing else", () => {
    // What breaks if this is deleted: a typed "1,000" or "-5" sent as a ceiling.
    expect(minorOf("250")).toBe(25000);
    expect(minorOf("250.5")).toBe(25050);
    expect(minorOf(" 0.01 ")).toBe(1);
    for (const refused of ["", "0", "0.00", "-5", "1,000", "1.234", "ten"]) {
      expect(minorOf(refused), refused).toBeNull();
    }
  });
});
