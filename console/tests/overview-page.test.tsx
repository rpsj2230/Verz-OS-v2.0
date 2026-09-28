/**
 * The Overview, the first screen an administrator sees: a health strip, the last week's figures,
 * Needs you, recent activity and quick actions, each from the route that owns it.
 *
 * **A queue the reader may not act on is absent, never nought.** The route leaves it out, and the
 * page must add nothing in its place: no list of queues filled with zeros. **A figure nothing
 * records is "Not recorded yet" with the API's reason, and never 0.** **A block whose route answers
 * a plain 404 is not this reader's and is left out**, while any other failure is drawn with its
 * reference. **The week's cost is drawn in the install's currency only when the route sent both,
 * and otherwise as "Not recorded yet" with the route's reason.** **Identifiers are only in
 * Advanced.**
 *
 * Mounted through the real route table and shell with the stand-in API from `support/pageCases.ts`,
 * and the readers are held against raw bodies, so a test of what the page draws is not also a test
 * of what the reader built.
 *
 * Task ids: M27.15.17, M27.16.1
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { cleanup, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { NOT_RECORDED } from "../src/components/kit";
import {
  ACTIVITY,
  AGENTS_LABEL,
  ANSWERED_LABEL,
  COST_LABEL,
  NEEDS_YOU,
  NOT_COUNTED,
  NOTHING_RETURNED_LABEL,
  NOTHING_WAITING,
  QUICK_ACTIONS,
  SOURCES_LABEL,
} from "../src/pages/overview/OverviewPage";
import {
  activeAgents,
  basisWords,
  connectedSources,
  costWords,
  queueLabel,
  readFigures,
  readOverview,
  recentActivity,
} from "../src/pages/overview/overviewQuery";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { COMPANY_CONSOLE, NAVIGATION_ADDRESS, addressesOf, departmentConsole } from "./support/navigation";
import { PAGES, UNBROKEN } from "./support/pageCases";
import { installRadixStubs } from "./support/radix";

const CASE = PAGES["/"];
if (CASE === undefined) {
  throw new Error("The Overview has no page case.");
}
const ANSWERS = CASE.answers;
const OVERVIEW = "/api/v1/console/overview";
const FIGURES = "/api/v1/console/overview/figures";
const AGENTS = "/api/v1/agents";
const AUDIT = "/api/v1/audit";

beforeAll(() => {
  installRadixStubs();
});

/** The reference a refused or failed answer carries, which the page must show for a failure. */
const TRACE = "trace-overview";

interface Page {
  readonly root: Element;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "x-trace-id": TRACE },
  });
}

/**
 * The console at `/`, signed in, with the page case's answers changed by `changes`, and each path in
 * `statuses` answered with that status instead. Read once nothing on the page is still loading.
 */
async function overviewWith(
  changes: Readonly<Record<string, unknown>> = {},
  statuses: Readonly<Record<string, number>> = {},
): Promise<Page> {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
  const answers: Readonly<Record<string, unknown>> = { ...ANSWERS, ...changes };
  const idp = fakeIdentityProvider({
    api(url) {
      const path = new URL(url, "https://console.test").pathname;
      const status = statuses[path];
      if (status !== undefined) {
        return json({ message: "The API explained itself.", trace_id: TRACE }, status);
      }
      if (path === NAVIGATION_ADDRESS) {
        return json(answers[NAVIGATION_ADDRESS] ?? COMPANY_CONSOLE);
      }
      return path in answers ? json(answers[path]) : null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: ["/"] });
  const { container } = render(<RouterProvider router={router} />);
  const root = (): Element => container.querySelector("main#main") ?? container;
  await waitFor(
    () => {
      expect(root().querySelector("[data-slot='overview-page']")).not.toBeNull();
      expect(root().textContent).not.toMatch(/Loading/);
    },
    { timeout: 10_000 },
  );
  return { root: root() };
}

function section(root: Element, name: string): Element | null {
  for (const one of root.querySelectorAll("section")) {
    const labelled = one.getAttribute("aria-labelledby");
    const heading = labelled === null ? null : one.ownerDocument.getElementById(labelled);
    if (one.getAttribute("aria-label") === name || heading?.textContent === name) {
      return one;
    }
  }
  return null;
}

/** The value a figure card drew beside its label, or null when the card is not on the page. */
function figure(root: Element, label: string): string | null {
  for (const card of root.querySelectorAll("[data-slot='stat-card']")) {
    if (card.querySelector("dt")?.textContent === label) {
      return card.querySelector("dd > span")?.textContent ?? "";
    }
  }
  return null;
}

/** The line beneath a figure card's value, or null when the card is not on the page or has none. */
function beneath(root: Element, label: string): string | null {
  for (const card of root.querySelectorAll("[data-slot='stat-card']")) {
    if (card.querySelector("dt")?.textContent === label) {
      return card.querySelector("dd > span:nth-of-type(2)")?.textContent ?? null;
    }
  }
  return null;
}

/** Text outside the Advanced section, which is the only place an identifier may appear. */
function textOutsideAdvanced(root: Element): string {
  const copy = root.cloneNode(true) as Element;
  copy.querySelectorAll("[data-slot='advanced']").forEach((one) => one.remove());
  return copy.textContent ?? "";
}

describe("what the Overview draws", () => {
  test("Needs you draws each queue the API sent with its count and link, and no queue it did not send", async () => {
    // What breaks if this is deleted: a Needs you that fills in the queues the reader may not act on
    // with zeros, which says those queues exist and are being kept from them, or one that drops the
    // count or the way to the list it counted.
    const page = await overviewWith();
    const needs = section(page.root, NEEDS_YOU);
    expect(needs).not.toBeNull();
    const lines = [...(needs?.querySelectorAll("li") ?? [])].map((one) => one.textContent ?? "");
    expect(lines).toHaveLength(3);
    expect(lines[0]).toContain(queueLabel("approvals"));
    expect(lines[0]).toContain("3");
    expect(lines[1]).toContain(`${UNBROKEN}`);
    expect(lines[1]).toContain("at least 1");
    expect(needs?.querySelector("a[href='/approvals']")).not.toBeNull();
    for (const absent of ["access_review", "elevation", "skill_reviews", "knowledge_past_review"]) {
      expect(needs?.textContent).not.toContain(queueLabel(absent));
    }
  });

  test("a queue the API could not count says so with its reason, and draws no number", async () => {
    // What breaks if this is deleted: a queue that could not be read shown as nought, which is the
    // reassuring answer nobody measured.
    const page = await overviewWith();
    const needs = section(page.root, NEEDS_YOU);
    const line = [...(needs?.querySelectorAll("li") ?? [])].find((one) => one.textContent?.includes(queueLabel("publish_approvals")));
    expect(line?.textContent).toContain(NOT_COUNTED);
    expect(line?.textContent).not.toMatch(/\d/);
    const described = line?.querySelector("[aria-describedby]")?.getAttribute("aria-describedby");
    expect(described === null || described === undefined ? null : page.root.ownerDocument.getElementById(described)?.textContent).toBe(UNBROKEN);
  });

  test("a reader with nothing waiting is told so, and not shown a list of noughts", async () => {
    // What breaks if this is deleted: an empty Needs you drawn as a blank card that reads as loading.
    const body = ANSWERS[OVERVIEW] as Record<string, unknown>;
    const page = await overviewWith({ [OVERVIEW]: { ...body, needs_you: [], uncounted: [] } });
    expect(section(page.root, NEEDS_YOU)?.textContent).toContain(NOTHING_WAITING);
  });

  test("the figure row draws the API's counts, and the week's cost in the install's currency", async () => {
    // What breaks if this is deleted: refused and abstained drawn as anything other than the one
    // figure the API sent, or a cost the route served drawn with no currency, in the wrong unit, or
    // still as not recorded.
    const page = await overviewWith();
    expect(figure(page.root, ANSWERED_LABEL)).toBe("1,847");
    expect(figure(page.root, NOTHING_RETURNED_LABEL)).toBe("312");
    expect(figure(page.root, AGENTS_LABEL)).toBe("1");
    expect(figure(page.root, SOURCES_LABEL)).toBe("1");
    expect(figure(page.root, COST_LABEL)).toBe(`${UNBROKEN} 1,284.50`);
    expect(beneath(page.root, COST_LABEL)).toBe(basisWords("everyone"));
  });

  test("a cost summed over the reader's own requests says so, even beside everybody's counts", async () => {
    // What breaks if this is deleted: a reader who may read everybody's usage and only their own
    // spend shown their own cost under a line that reads as the company's.
    const body = ANSWERS[FIGURES] as Record<string, unknown>;
    const page = await overviewWith({ [FIGURES]: { ...body, cost_basis: "own", cost_minor: 0, currency: "SGD" } });
    expect(beneath(page.root, ANSWERED_LABEL)).toBe(basisWords("everyone"));
    expect(figure(page.root, COST_LABEL)).toBe("SGD 0.00");
    expect(beneath(page.root, COST_LABEL)).toBe(basisWords("own"));
  });

  test("a cost the route says is not recorded reads Not recorded yet with its reason, never nought", async () => {
    // What breaks if this is deleted: an install with no model priced shown 0.00, which says the
    // company spent nothing, or the sentence drawn without the reason that says what to do.
    const why = "no model has a price in this install's currency yet";
    const body = ANSWERS[FIGURES] as Record<string, unknown>;
    const page = await overviewWith({
      [FIGURES]: { ...body, cost_minor: null, currency: null, not_recorded: [{ figure: "cost", why }] },
    });
    // The reason is read out after the words, so the card starts with them and carries no number.
    expect(figure(page.root, COST_LABEL)?.startsWith(NOT_RECORDED)).toBe(true);
    expect(figure(page.root, COST_LABEL)).toContain(why);
    expect(figure(page.root, COST_LABEL)).not.toMatch(/\d/);
  });

  test("a block whose route answers 404 is left out, and any other failure is drawn with its reference", async () => {
    // What breaks if this is deleted: a reader who may not open the overview shown "I could not find
    // that" on the first screen they see, or a fault on the audit log hidden as if there were none.
    const refusedOverview = await overviewWith({}, { [OVERVIEW]: 404 });
    expect(section(refusedOverview.root, NEEDS_YOU)).toBeNull();
    expect(section(refusedOverview.root, "This install")).toBeNull();
    expect(refusedOverview.root.textContent).not.toContain(TRACE);
    expect(figure(refusedOverview.root, ANSWERED_LABEL)).toBe("1,847");

    const brokenAudit = await overviewWith({}, { [AUDIT]: 500 });
    expect(section(brokenAudit.root, ACTIVITY)?.textContent).toContain(TRACE);
    expect(section(brokenAudit.root, NEEDS_YOU)).not.toBeNull();
  });

  test("the agent card counts switched-on agents, and is left out when the roster does not say which are", async () => {
    // What breaks if this is deleted: every agent counted as active, or agents whose state the
    // reader was not told counted as switched off.
    const page = await overviewWith({
      [AGENTS]: {
        items: [
          { agent_id: "a", display_name: "A", state: "enabled" },
          { agent_id: "b", display_name: "B", state: "disabled" },
        ],
        next_cursor: "more",
        truncated: true,
      },
    });
    expect(figure(page.root, AGENTS_LABEL)).toBe("1+");

    const untold = await overviewWith({ [AGENTS]: { items: [{ agent_id: "a", display_name: "A" }], truncated: false } });
    expect(figure(untold.root, AGENTS_LABEL)).toBeNull();
  });

  test("activity says what was done and to what, with no identifier outside Advanced", async () => {
    // What breaks if this is deleted: principal ids and slugs back in the page text, which the owner
    // found cluttered, or an activity row that cannot be followed to its entry.
    const page = await overviewWith();
    const activity = section(page.root, ACTIVITY);
    expect(activity?.textContent).toContain("Granted a capability to a person");
    expect(activity?.querySelector("a[href^='/audit?']")).not.toBeNull();
    expect(textOutsideAdvanced(page.root)).not.toContain("f".repeat(64));
    const advanced = page.root.querySelector("[data-slot='advanced']");
    expect(advanced?.textContent).toContain("f".repeat(64));
  });

  test("quick actions offer only the pages in this reader's menu, and Ask always", async () => {
    // What breaks if this is deleted: a department administrator offered "Connect a source", which
    // opens a page their menu does not list and answers them with a refusal.
    const company = await overviewWith();
    const everything = [...(section(company.root, QUICK_ACTIONS)?.querySelectorAll("a") ?? [])].map((one) => one.getAttribute("href"));
    expect(everything).toEqual(["/library", "/connectors", "/people", "/ask"]);

    const department = departmentConsole("maintenance");
    const listed = new Set(addressesOf(department as { sections: unknown }));
    const narrower = await overviewWith({ [NAVIGATION_ADDRESS]: department });
    const offered = [...(section(narrower.root, QUICK_ACTIONS)?.querySelectorAll("a") ?? [])].map((one) => one.getAttribute("href"));
    expect(offered).toEqual(["/library", "/connectors", "/people", "/ask"].filter((one) => one === "/ask" || listed.has(one)));

    const bare = await overviewWith({ [NAVIGATION_ADDRESS]: { console: "department", departments: ["maintenance"], sections: [] } });
    const only = [...(section(bare.root, QUICK_ACTIONS)?.querySelectorAll("a") ?? [])].map((one) => one.getAttribute("href"));
    expect(only).toEqual(["/ask"]);
  });
});

describe("what the readers keep", () => {
  test("an overview line that is not a count is dropped, never drawn as nought", () => {
    // What breaks if this is deleted: a malformed line arriving as "0 waiting".
    const read = readOverview({
      health: { status: "ok", parts: [], worker_last_seen: null, unrecorded: [] },
      needs_you: [
        { queue: "approvals", waiting: 2, at_least: false, opens: "/approvals" },
        { queue: "elevation", waiting: -1, at_least: false, opens: "/elevation" },
        { queue: "skill_reviews", waiting: "3", at_least: false, opens: "/skills" },
        { queue: "access_review", waiting: 1, at_least: false, opens: "https://elsewhere.example/x" },
      ],
      uncounted: [],
    });
    expect(read?.needsYou.map((one) => [one.queue, one.waiting, one.opens])).toEqual([
      ["approvals", 2, "/approvals"],
      ["access_review", 1, undefined],
    ]);
    expect(readOverview({ needs_you: [] })).toBeNull();
  });

  test("figures that are not counts are no figures at all", () => {
    // What breaks if this is deleted: a figure row drawn from a body that is not one.
    expect(readFigures({ basis: "own", answered: 1, nothing_returned: 0, not_recorded: [] })?.answered).toBe(1);
    expect(readFigures({ basis: "own", answered: null, nothing_returned: 0 })).toBeNull();
  });

  test("a cost is kept only with its currency and its basis, and never from a sum that is not one", () => {
    // What breaks if this is deleted: a sum drawn in whichever currency the reader assumes, or a
    // null, a fraction or a negative drawn as a cost.
    const counts = { basis: "everyone", answered: 1, nothing_returned: 0, not_recorded: [] };
    expect(readFigures({ ...counts, cost_minor: 250, currency: "SGD", cost_basis: "own" })?.cost).toEqual({
      minor: 250,
      currency: "SGD",
      basis: "own",
    });
    for (const broken of [
      { cost_minor: 250, currency: null, cost_basis: "own" },
      { cost_minor: 250, currency: "SGD" },
      { cost_minor: null, currency: "SGD", cost_basis: "own" },
      { cost_minor: 2.5, currency: "SGD", cost_basis: "own" },
      { cost_minor: -1, currency: "SGD", cost_basis: "own" },
    ]) {
      expect(readFigures({ ...counts, ...broken })?.cost).toBeUndefined();
    }
    expect(costWords({ minor: 128450, currency: "SGD", basis: "own" })).toBe("SGD 1,284.50");
    expect(costWords({ minor: 7, currency: "EUR", basis: "own" })).toBe("EUR 0.07");
  });

  test("sources are counted over the list sent, and a list nobody read is a sentence", () => {
    // What breaks if this is deleted: an unread list drawn as nought sources.
    expect(connectedSources({ connectors: [{ name: "a" }, { name: "b" }], unread: "" })).toEqual({ value: 2, atLeast: false });
    expect(connectedSources({ connectors: null, unread: "nothing looked" })).toEqual({ unread: "nothing looked" });
    expect(activeAgents({ items: [] })).toEqual({ value: 0, atLeast: false });
  });

  test("activity keeps at most the newest six entries the ledger sent", () => {
    // What breaks if this is deleted: the landing screen growing into a second audit log.
    const row = { at: "2019-03-04T09:00:00Z", action: "grant", actor_id: "u", subject_kind: "principal", subject_id: "p", details: {} };
    expect(recentActivity({ items: Array.from({ length: 9 }, () => row) })).toHaveLength(6);
  });
});
