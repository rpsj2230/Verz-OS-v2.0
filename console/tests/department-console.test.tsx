/**
 * A department's console in the browser: the menu the API gives, the menu before it has, and the
 * Department page SCREEN 2 draws.
 *
 * **The shell draws what the API answered and decides nothing.** A department's answer is drawn
 * as sent, followed by the reader's own work, and nothing about this server is offered in it. The
 * menu before an answer, after a failure and after a body that cannot be read is the reader's own
 * work alone, which is `navigationQuery.A_MENU_NOBODY_ANSWERED_OFFERS_ONLY_YOUR_OWN_WORK`, and the
 * failing direction is asserted as well as the answering one.
 *
 * **The stand-in body is held to the Python.** The field names are read off
 * `brain.navigation_routes.NavigationView`, and both menus the support file sends are read off
 * `brain.console.department_console`, so the menu these tests draw is the one the route serves.
 *
 * **The Department page asks routes other screens already ask**, on the page kit, and each block is
 * held to drawing that route's answer, to failing on its own, and to being left out when its route
 * says it is not this reader's. It is mounted through the application's own route table, so its
 * view addresses are held too.
 *
 * Task ids: M27.7.29, M27.10.1, M27.16.1, M33.2.1.3, M33.2.1.4
 */

import { createMemoryRouter, MemoryRouter, RouterProvider } from "react-router-dom";
import { render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  A_MENU_NOBODY_ANSWERED_OFFERS_ONLY_YOUR_OWN_WORK,
  menuFor,
  readNavigation,
  type NavGroup,
} from "../src/layout/navigationQuery";
import {
  AGENTS_HEADING,
  AHEAD_OF_PACE,
  COVERAGE_HEADING,
  KNOWLEDGE_HEADING,
  NO_CEILING,
  NOT_A_DEPARTMENT_CONSOLE,
  PACE_HEADING,
  PROFILE_ELSEWHERE,
  USAGE_HEADING,
} from "../src/pages/department/DepartmentHomePage";
import { DEPARTMENT_COVERAGE_API_PATH, DEPARTMENT_PACE_API_PATH } from "../src/pages/department/departmentFigures";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { installRadixStubs } from "./support/radix";
import {
  COMPANY_CONSOLE,
  NAVIGATION_ADDRESS,
  addressesOf,
  answerNavigation,
  declaredNavigation,
  departmentConsole,
} from "./support/navigation";
import { OWN_WORK } from "../src/routes/registry";
import { backendModelFields } from "./support/python";
import { readRepoFile } from "./support/repo";

/** A value that appears nowhere else, so a dropped one cannot be covered by another. */
function sentinel(name: string): string {
  return `${name.toUpperCase()}-SENTINEL`;
}

/** The addresses of the screens about this server, none of which a department is offered. */
const ABOUT_THE_SERVER = ["/updates", "/recovery", "/limits", "/features", "/storage", "/credentials", "/settings"];

/** The reader's own work, as every console lists it. */
const OWN_WORK_ADDRESSES = OWN_WORK.sections.map((one) => one.to);

/** Mount the shell against a stand-in API answering the navigation with `answer`. */
async function shellAnswering(answer: (url: string) => Response | null): Promise<HTMLElement> {
  const idp = fakeIdentityProvider({ api: answer });
  await signIn(await loadConsole({ idp }));
  const { Shell } = await import("../src/layout/Shell");
  const { container } = render(
    <MemoryRouter initialEntries={["/"]}>
      <Shell />
    </MemoryRouter>,
  );
  return container;
}

async function answered(container: HTMLElement): Promise<void> {
  await waitFor(() => {
    if (container.querySelector('nav [role="status"]')) {
      throw new Error("the menu has not been answered yet");
    }
  });
}

function menu(container: HTMLElement): { headings: string[]; hrefs: string[] } {
  const nav = container.querySelector("nav");
  return {
    headings: [...(nav?.querySelectorAll("h2") ?? [])].map((one) => one.textContent ?? ""),
    hrefs: [...(nav?.querySelectorAll("a") ?? [])].map((one) => one.getAttribute("href") ?? ""),
  };
}

describe("the menu a department is given", () => {
  test("a department's answer is drawn as sent, then the reader's own work, and nothing about the server", async () => {
    // What breaks if this is deleted: the shell can keep drawing the company console for everybody,
    // or filter it here, and a department admin is offered every screen about this server.
    const body = departmentConsole(sentinel("department"));
    const container = await shellAnswering((url) => answerNavigation(url, body));
    await answered(container);

    const drawn = menu(container);
    expect(drawn.headings).toEqual([
      "Use",
      "Home",
      "People and access",
      "Agents and AI",
      "Knowledge and data",
      "Operations",
      "Governance",
      "Reports",
    ]);
    expect(drawn.hrefs).toEqual([
      ...OWN_WORK_ADDRESSES,
      "/department",
      "/people",
      "/agents",
      "/skills",
      "/connectors",
      "/library",
      "/learning",
      "/runs",
      "/audit",
      "/questions",
      "/usage",
    ]);
    for (const address of ABOUT_THE_SERVER) {
      expect(drawn.hrefs).not.toContain(address);
    }
    expect(container.querySelector("header")?.textContent).toContain(sentinel("department"));
  });

  test("the company's answer is the company console whole, install screens included", async () => {
    // What breaks if this is deleted: every assertion above is satisfied by a shell that never
    // offers anybody a screen about the server.
    const container = await shellAnswering((url) => answerNavigation(url, COMPANY_CONSOLE));
    await answered(container);

    const drawn = menu(container);
    expect(drawn.headings).toEqual(["Use", ...COMPANY_CONSOLE.sections.map((one) => one.heading)]);
    expect(drawn.headings).toContain("Platform");
    for (const address of ABOUT_THE_SERVER) {
      expect(drawn.hrefs).toContain(address);
    }
    expect(drawn.hrefs).not.toContain("/department");
  });

  test("before the answer, after a failure and after an unreadable body, only the reader's own work is offered", async () => {
    // What breaks if this is deleted: the fallback can become the company console, which offers a
    // department admin every screen about this server while the request is in flight and for good
    // when it fails. `A_MENU_NOBODY_ANSWERED_OFFERS_ONLY_YOUR_OWN_WORK` is the argument.
    expect(A_MENU_NOBODY_ANSWERED_OFFERS_ONLY_YOUR_OWN_WORK).toContain("only the screens");
    const ownWork = ["/ask", "/me", "/approvals", "/records", "/access-requests", "/referrals"];
    expect(OWN_WORK_ADDRESSES).toEqual(ownWork);

    const pending = await shellAnswering((url) => answerNavigation(url, departmentConsole()));
    expect(menu(pending).hrefs).toEqual(ownWork);
    expect(pending.querySelector('nav [role="status"]')).not.toBeNull();

    const refused = await shellAnswering(() => null);
    await answered(refused);
    expect(menu(refused).hrefs).toEqual(ownWork);
    expect(refused.querySelector("nav")?.textContent).toContain("could not be loaded");

    const unreadable = await shellAnswering((url) =>
      answerNavigation(url, { console: "everything", departments: [], sections: [] }),
    );
    await answered(unreadable);
    expect(menu(unreadable).hrefs).toEqual(ownWork);
  });
});

describe("reading the answer", () => {
  test("the body's fields are the Python model's, and both menus are read whole from the Python declaration", () => {
    // What breaks if this is deleted: the stand-in the shell tests answer with can drift from what
    // the route sends, and every test above passes against a menu the API never serves.
    expect(backendModelFields("src/brain/navigation_routes.py", "NavigationView")).toEqual([
      "console",
      "departments",
      "sections",
    ]);
    expect(backendModelFields("src/brain/navigation_routes.py", "SectionView")).toEqual([
      "group",
      "heading",
      "entries",
    ]);
    expect(backendModelFields("src/brain/navigation_routes.py", "EntryView")).toEqual(["key", "label", "to", "tabs"]);
    expect(backendModelFields("src/brain/navigation_routes.py", "TabView")).toEqual(["key", "label", "to"]);

    // The support file reads the declaration token by token; a page written in a shape it skips
    // would be a page these tests never draw. Every page the declaration spells is counted here.
    const declared = readRepoFile("src/brain/console/department_console.py");
    const body = declared.slice(declared.indexOf("COMPANY_NAVIGATION: Final"), declared.indexOf("class ConsoleNavigation"));
    const spelled = [...body.matchAll(/\bPage\(|\b_one\(/g)].length;
    const read = [...declaredNavigation("company"), ...declaredNavigation("department")].flatMap((one) =>
      one.entries.flatMap((entry) => (entry.tabs.length > 0 ? entry.tabs : [entry])),
    );
    expect(read.length).toBe(spelled);
    expect(addressesOf(COMPANY_CONSOLE)).toContain("/capabilities");
    expect(declaredNavigation("department").map((one) => one.group)).not.toContain("platform");
  });

  test("a body is read whole or not at all", () => {
    // What breaks if this is deleted: a menu with one group missing, drawn from a body the reader
    // half understood, which is a menu the API did not send.
    expect(readNavigation(departmentConsole())?.groups.map((one) => one.heading)).toEqual([
      "Home",
      "People and access",
      "Agents and AI",
      "Knowledge and data",
      "Operations",
      "Governance",
      "Reports",
    ]);
    const company = readNavigation(COMPANY_CONSOLE);
    expect(company?.console).toBe("company");
    expect(company?.groups.map((one) => one.key)).toEqual(COMPANY_CONSOLE.sections.map((one) => one.group));
    const roles = company?.groups.flatMap((one) => one.sections).find((one) => one.label === "Roles and permissions");
    expect(roles?.tabs.map((one) => one.to)).toEqual(["/roles", "/capabilities", "/scopes", "/packs"]);

    const broken = departmentConsole();
    (broken.sections as unknown[]).push({ group: "platform", heading: "Platform", entries: [{ label: "No address", tabs: [] }] });
    expect(readNavigation(broken)).toBeNull();
    const untabbed = departmentConsole();
    (untabbed.sections as { entries: { tabs?: unknown }[] }[])[0]!.entries[0]!.tabs = undefined;
    expect(readNavigation(untabbed)).toBeNull();
    const ungrouped = departmentConsole();
    (ungrouped.sections as { group?: unknown }[])[0]!.group = undefined;
    expect(readNavigation(ungrouped)).toBeNull();
    expect(readNavigation({ ...departmentConsole(), departments: [7] })).toBeNull();
    expect(readNavigation({ ...departmentConsole(), sections: "all" })).toBeNull();
    expect(readNavigation(null)).toBeNull();
  });

  test("the menu for no answer is the reader's own work, and an answer follows it whichever console it is", () => {
    // What breaks if this is deleted: `menuFor` can hand back a served menu for a null answer, which
    // is the fallback the shell test above refuses, proved here without a render.
    const own: NavGroup = { key: "use", heading: "Use", sections: [{ to: "/ask", label: "Ask", tabs: [] }] };
    const department = readNavigation(departmentConsole());
    const company = readNavigation(COMPANY_CONSOLE);

    expect(menuFor(null, own)).toEqual([own]);
    expect(menuFor(company, own).map((one) => one.heading)).toEqual(["Use", ...COMPANY_CONSOLE.sections.map((one) => one.heading)]);
    expect(menuFor(department, own).map((one) => one.heading)[0]).toBe("Use");
    expect(menuFor(department, own).map((one) => one.heading)).not.toContain("Platform");
  });
});

describe("the Department page", () => {
  beforeAll(() => {
    installRadixStubs();
  });

  function json(body: unknown, status = 200): () => Response {
    return () => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
  }

  /** Mount the console at a Department address with a department's menu and these answers. */
  async function departmentPage(address: string, answers: Record<string, () => Response>): Promise<HTMLElement> {
    const idp = fakeIdentityProvider({
      api(url) {
        const asked = new URL(url, "https://console.test").pathname;
        return answers[asked]?.() ?? null;
      },
    });
    await signIn(await loadConsole({ idp }));
    const { routes } = await import("../src/App");
    const router = createMemoryRouter(routes, { initialEntries: [address] });
    const { container } = render(<RouterProvider router={router} />);
    await waitFor(() => {
      if (!container.querySelector("main h1") || container.querySelector('main [data-slot="loading-state"]')) {
        throw new Error("the page has not been answered yet");
      }
    });
    return container;
  }

  const USAGE = {
    start: "2019-02-26T09:00:00Z",
    end: "2019-03-05T09:00:00Z",
    departments: [
      { department: "maintenance", questions: 926, people: 31 },
      { department: "web", questions: 4, people: 2 },
    ],
    people: [{ person: "u_one", questions: 900 }],
    questions: 930,
    machine_included: false,
    not_measured: [],
    tokens: [],
  };

  const ORGANISATION = {
    items: [
      {
        slug: "maintenance",
        name: sentinel("department name"),
        teams: [{ slug: "night", name: "Night shift", members: [] }],
        members: [{ principal_id: "u_lead", display_name: "Lee Lead", disabled: false }],
        lead: { principal_id: "u_lead", display_name: "Lee Lead", disabled: false },
        shapeable: true,
      },
    ],
    next_cursor: null,
    unplaced: [],
    truncated: false,
    may_organise: true,
    may_found: true,
    may_draw_scopes: false,
    staleness: null,
    teams: "t",
    leads: "l",
    counted: "c",
    organising: "o",
    shaping: "s",
    retiring_department: "Retiring it keeps its history.",
    retiring_team: "r",
    retiring_scope: "r",
  };

  const PEOPLE = {
    items: [{ principal_id: "u_ada", display_name: sentinel("person"), department: "maintenance", department_name: sentinel("directory name"), standing: "live", packs: [] }],
    next_cursor: null,
    truncated: false,
  };

  const QUESTIONS = {
    start: "2019-02-26T09:00:00Z",
    end: "2019-03-05T09:00:00Z",
    gaps: [],
    nothing_connected: true,
    answered_when_nothing_connected: sentinel("told"),
    answered_when_nothing_found: "not found",
    unanswered_are_recorded: false,
  };

  function everything(over: Record<string, () => Response> = {}): Record<string, () => Response> {
    return {
      [NAVIGATION_ADDRESS]: json(departmentConsole("maintenance")),
      "/api/v1/govern/departments": json(ORGANISATION),
      "/api/v1/govern/directory": json(PEOPLE),
      "/api/v1/report/usage": json(USAGE),
      "/api/v1/agents": json({ items: [{ agent_id: "site-health", display_name: sentinel("agent") }] }),
      "/api/v1/knowledge/documents": json({ items: [{ item_id: "doc-1", title: sentinel("document"), level: "department", state: "published", verification: "verified", due: false, you_steward: false }], next_cursor: null }),
      "/api/v1/report/questions": json(QUESTIONS),
      ...over,
    };
  }

  function block(container: HTMLElement, heading: string): Element | undefined {
    return [...container.querySelectorAll('[data-slot="section-card"]')].find((one) => one.querySelector("h2")?.textContent === heading);
  }

  test("the Dashboard draws each block from its own route, the department's own line of usage, and links to where each came from", async () => {
    // What breaks if this is deleted: the page draws a figure it computed, the company's questions
    // stand for one department's, or a block has nothing from the API on it.
    const container = await departmentPage("/department", everything());
    expect(container.querySelector("main h1")?.textContent).toBe(sentinel("department name"));
    const figures = container.querySelector(`[aria-label="${USAGE_HEADING}"]`)?.textContent ?? "";
    expect(figures).toContain("926");
    expect(figures).toContain("31");
    expect(figures).not.toContain("930");
    const text = container.querySelector("main")?.textContent ?? "";
    expect(text).toContain(sentinel("person"));
    expect(text).toContain(sentinel("agent"));
    expect(text).toContain(sentinel("document"));
    expect(text).toContain(sentinel("told"));
    const hrefs = [...container.querySelectorAll("main a")].map((one) => one.getAttribute("href"));
    expect(hrefs).toEqual(expect.arrayContaining(["/usage", "/agents/site-health", "/people/u_ada", "/library/doc-1", "/approvals"]));
    expect(text).not.toContain("maintenance");
  });

  test("a block whose route failed says so in the API's words, and the other blocks still draw", async () => {
    // What breaks if this is deleted: one refused read blanks the whole page, or a failure is drawn
    // as a department with no questions in it.
    const container = await departmentPage(
      "/department",
      everything({ "/api/v1/report/usage": json({ message: sentinel("refused"), trace_id: "t-1" }, 503) }),
    );
    const text = container.querySelector("main")?.textContent ?? "";
    expect(text).toContain(sentinel("refused"));
    expect(text).not.toContain("926");
    expect(text).toContain(sentinel("agent"));
  });

  test("a block whose route says it is not this reader's is left out, never drawn empty", async () => {
    // What breaks if this is deleted: a department admin who may not open Knowledge shown a Knowledge
    // block saying nothing is filed, which is a statement about documents they may not see.
    const container = await departmentPage(
      "/department",
      everything({ "/api/v1/knowledge/documents": json({ message: "I could not find that.", trace_id: "t-2" }, 404) }),
    );
    expect(block(container, KNOWLEDGE_HEADING)).toBeUndefined();
    expect(block(container, AGENTS_HEADING)).not.toBeUndefined();
  });

  test("a usage answer with no axis offered draws no figure, never a zero", async () => {
    // What breaks if this is deleted: a reader offered no usage table is shown "0", which says their
    // department asked nothing.
    const container = await departmentPage(
      "/department",
      everything({ "/api/v1/report/usage": json({ ...USAGE, departments: null, people: null, questions: null }) }),
    );
    expect(container.querySelector(`[aria-label="${USAGE_HEADING}"]`)).toBeNull();
  });

  test("named from the directory when the Departments row is not the reader's, and the short name is only in Advanced", async () => {
    // What breaks if this is deleted: a department admin who may not open Departments sees their
    // department by its short name, or by no name at all.
    const container = await departmentPage(
      "/department/profile",
      everything({ "/api/v1/govern/departments": json({ message: "I could not find that.", trace_id: "t-3" }, 404) }),
    );
    expect(container.querySelector("main h1")?.textContent).toBe(sentinel("directory name"));
    expect(container.querySelector("main")?.textContent).toContain(PROFILE_ELSEWHERE);
    const advanced = container.querySelector('main [data-slot="advanced"]')?.textContent ?? "";
    expect(advanced).toContain("maintenance");
    const outside = (container.querySelector("main")?.textContent ?? "").replace(advanced, "");
    expect(outside).not.toContain("maintenance");
    expect([...container.querySelectorAll("main button")].some((one) => one.textContent === "Rename")).toBe(false);
  });

  test("the Profile names the lead and teams and offers rename and retire where the API says the reader may", async () => {
    // What breaks if this is deleted: the department's own acts missing from its page, or offered to
    // a reader every route refuses.
    const container = await departmentPage("/department/profile", everything({ "/api/v1/govern/scopes": json({ items: [], next_cursor: null }) }));
    const text = container.querySelector("main")?.textContent ?? "";
    expect(text).toContain("Lee Lead");
    expect(text).toContain("Night shift");
    const buttons = [...container.querySelectorAll("main button")].map((one) => one.textContent);
    expect(buttons).toEqual(expect.arrayContaining(["Rename", "Retire"]));

    const narrower = await departmentPage(
      "/department/profile",
      everything({
        "/api/v1/govern/departments": json({ ...ORGANISATION, may_found: false, items: [{ ...ORGANISATION.items[0], shapeable: false }] }),
        "/api/v1/govern/scopes": json({ items: [], next_cursor: null }),
      }),
    );
    const fewer = [...narrower.querySelectorAll("main button")].map((one) => one.textContent);
    expect(fewer).not.toContain("Rename");
    expect(fewer).not.toContain("Retire");
  });

  test("About lists the audit trail's entries about this department alone, by who made them", async () => {
    // What breaks if this is deleted: another department's history drawn on this one's page, or a
    // change attributed to a reference nobody can read.
    const entry = (subject: string, change: string) => ({
      at: "2019-03-04T09:00:00Z",
      action: "organisation",
      actor_id: "u_ada",
      subject_kind: "department",
      subject_id: subject,
      details: { change },
    });
    const container = await departmentPage(
      "/department/about",
      everything({
        "/api/v1/audit": json({ items: [entry("maintenance", "renamed"), entry("maintenance_two", "retired")], next_cursor: null, order: "newest", actions: [], subject_kinds: [], actors: [] }),
      }),
    );
    // The actor's name comes from a second request after the rows are drawn, so it is waited for.
    await waitFor(() => {
      const rows = [...container.querySelectorAll("main tbody tr")].map((one) => one.textContent ?? "");
      expect(rows).toHaveLength(1);
      expect(rows[0]).toContain("Renamed");
      expect(rows[0]).toContain(sentinel("person"));
    });
  });

  /** The head's pace and coverage, as `brain.department_view_routes` sends them. */
  const PACE = {
    department: "maintenance",
    paces: [
      { period: "day", started_at: "2019-03-04T00:00:00Z", ends_at: "2019-03-05T00:00:00Z", spent_fraction: 0.9, elapsed_fraction: 0.5, ahead: true },
      { period: "month", started_at: "2019-03-01T00:00:00Z", ends_at: "2019-04-01T00:00:00Z", spent_fraction: 0.25, elapsed_fraction: 0.4, ahead: false },
    ],
    not_recorded: [],
  };

  const COVERAGE = {
    department: "maintenance",
    areas: [{ area: "maintenance", items: 713, by_freshness: { live: 401, ageing: 211, stale: 67, unstated: 34 } }],
    unread: "",
  };

  const HEAD = {
    [`/api/v1${DEPARTMENT_PACE_API_PATH}`]: json(PACE),
    [`/api/v1${DEPARTMENT_COVERAGE_API_PATH}`]: json(COVERAGE),
  };

  test("the head is shown each budget against time and what the department knows, as the API sent them", async () => {
    // What breaks if this is deleted: the two blocks can compute a figure of their own, drop a band,
    // or name the department by its short name, and nothing reading the page would notice.
    const container = await departmentPage("/department", everything(HEAD));
    const pace = block(container, PACE_HEADING)?.textContent ?? "";
    expect(pace).toContain("90% of the budget spent, 50% of the day gone");
    expect(pace).toContain("25% of the budget spent, 40% of the month gone");
    expect(pace.split(AHEAD_OF_PACE)).toHaveLength(2);
    const coverage = block(container, COVERAGE_HEADING)?.textContent ?? "";
    for (const figure of ["713", "401", "211", "67", "34"]) {
      expect(coverage).toContain(figure);
    }
    expect(coverage).not.toContain("maintenance");
  });

  test("a head's block the API refuses is left out, and the page's other blocks still draw", async () => {
    // What breaks if this is deleted: a department admin who leads nothing is shown an empty budget
    // block, which says the department has no budget when the API said the block is not theirs.
    const refused = json({ message: "I could not find that.", trace_id: "t-4" }, 404);
    const container = await departmentPage(
      "/department",
      everything({ [`/api/v1${DEPARTMENT_PACE_API_PATH}`]: refused, [`/api/v1${DEPARTMENT_COVERAGE_API_PATH}`]: refused }),
    );
    expect(block(container, PACE_HEADING)).toBeUndefined();
    expect(block(container, COVERAGE_HEADING)).toBeUndefined();
    expect(block(container, AGENTS_HEADING)).not.toBeUndefined();
  });

  test("the API's sentences stand in for a figure it could not send, and no fraction or band is drawn", async () => {
    // What breaks if this is deleted: an install that records no cost shows the department as having
    // spent nothing, and a coverage load that came back full is drawn as the figure.
    const container = await departmentPage(
      "/department",
      everything({
        [`/api/v1${DEPARTMENT_PACE_API_PATH}`]: json({ ...PACE, paces: [], not_recorded: [{ figure: "cost", why: sentinel("unpriced") }] }),
        [`/api/v1${DEPARTMENT_COVERAGE_API_PATH}`]: json({ ...COVERAGE, areas: [], unread: sentinel("full") }),
      }),
    );
    const pace = block(container, PACE_HEADING)?.textContent ?? "";
    expect(pace).toContain(sentinel("unpriced"));
    expect(pace).not.toContain("%");
    const coverage = block(container, COVERAGE_HEADING)?.textContent ?? "";
    expect(coverage).toContain(sentinel("full"));
    expect(coverage).not.toContain("713");

    const none = await departmentPage("/department", everything({ ...HEAD, [`/api/v1${DEPARTMENT_PACE_API_PATH}`]: json({ ...PACE, paces: [] }) }));
    expect(block(none, PACE_HEADING)?.textContent ?? "").toContain(NO_CEILING);
  });

  test("a company administrator who opens the address is sent to Departments", async () => {
    // What breaks if this is deleted: the company console drawing one department it chose itself, or
    // an empty page with nowhere to go.
    const container = await departmentPage("/department", { [NAVIGATION_ADDRESS]: json(COMPANY_CONSOLE) });
    expect(container.querySelector("main")?.textContent).toContain(NOT_A_DEPARTMENT_CONSOLE);
    expect([...container.querySelectorAll("main a")].map((one) => one.getAttribute("href"))).toContain("/departments");
  });
});
