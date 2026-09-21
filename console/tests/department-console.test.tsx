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
 * `brain.navigation_routes.NavigationView`, and the department menu the support file sends is
 * read off `brain.console.department_console.DEPARTMENT_NAVIGATION`, so the menu these tests
 * draw is the one the route serves.
 *
 * **The Department page asks three routes other screens already ask**, and each card is held to
 * drawing that route's answer, to failing on its own, and to saying in words what the design draws
 * that nothing serves.
 *
 * Task ids: M27.7.29
 */

import { MemoryRouter } from "react-router-dom";
import { render, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import {
  A_MENU_NOBODY_ANSWERED_OFFERS_ONLY_YOUR_OWN_WORK,
  menuFor,
  readNavigation,
  type NavGroup,
} from "../src/layout/navigationQuery";
import {
  AGENTS_CARD,
  DEPARTMENT_HEADING,
  GAPS_CARD,
  NOT_DRAWN_HERE,
  NOTHING_TO_SHOW,
  USAGE_CARD,
} from "../src/pages/Department";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import {
  COMPANY_CONSOLE,
  NAVIGATION_ADDRESS,
  answerNavigation,
  departmentConsole,
} from "./support/navigation";
import { backendModelFields } from "./support/python";
import { readRepoFile } from "./support/repo";

/** A value that appears nowhere else, so a dropped one cannot be covered by another. */
function sentinel(name: string): string {
  return `${name.toUpperCase()}-SENTINEL`;
}

/** The addresses of the screens about this server, none of which a department is offered. */
const ABOUT_THE_SERVER = [
  "/install",
  "/updates",
  "/recovery",
  "/limits",
  "/connections",
  "/features",
  "/storage",
  "/vault",
  "/requirement-checks",
];

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
    expect(drawn.headings).toEqual(["Operate", "Govern", "Report", "Use"]);
    expect(drawn.hrefs).toEqual([
      "/department",
      "/runs",
      "/connectors",
      "/people",
      "/agents",
      "/library",
      "/skills",
      "/learning",
      "/questions",
      "/usage",
      "/ask",
      "/me",
      "/approvals",
      "/records",
      "/access-requests",
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
    expect(drawn.headings).toEqual(["Operate", "Govern", "Report", "Use", "Install"]);
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
    const ownWork = ["/ask", "/me", "/approvals", "/records", "/access-requests"];

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
  test("the body's fields are the Python model's, and the department menu is the Python declaration", () => {
    // What breaks if this is deleted: the stand-in the shell tests answer with can drift from what
    // the route sends, and every test above passes against a menu the API never serves.
    expect(backendModelFields("src/brain/navigation_routes.py", "NavigationView")).toEqual([
      "console",
      "departments",
      "sections",
    ]);
    expect(backendModelFields("src/brain/navigation_routes.py", "SectionView")).toEqual([
      "heading",
      "entries",
    ]);
    expect(backendModelFields("src/brain/navigation_routes.py", "EntryView")).toEqual([
      "key",
      "label",
      "to",
    ]);

    const declared = readRepoFile("src/brain/console/department_console.py");
    const rows = [...declared.matchAll(/Entry\(label="([^"]+)", key="([^"]+)", to="([^"]+)"\)/g)].map(
      (one) => ({ key: one[2], label: one[1], to: one[3] }),
    );
    const sent = (departmentConsole().sections as { entries: unknown[] }[]).flatMap((one) => one.entries);
    expect(rows.length).toBeGreaterThan(0);
    expect(sent).toEqual(rows);
  });

  test("a body is read whole or not at all", () => {
    // What breaks if this is deleted: a menu with one group missing, drawn from a body the reader
    // half understood, which is a menu the API did not send.
    expect(readNavigation(departmentConsole())?.groups.map((one) => one.heading)).toEqual([
      "Operate",
      "Govern",
      "Report",
    ]);
    expect(readNavigation(COMPANY_CONSOLE)).toEqual({ console: "company", departments: [], groups: [] });

    const broken = departmentConsole();
    (broken.sections as unknown[]).push({ heading: "Install", entries: [{ label: "No address" }] });
    expect(readNavigation(broken)).toBeNull();
    expect(readNavigation({ ...departmentConsole(), departments: [7] })).toBeNull();
    expect(readNavigation({ ...departmentConsole(), sections: "all" })).toBeNull();
    expect(readNavigation(null)).toBeNull();
  });

  test("the menu for no answer is the reader's own work, and the company's is its own constant", () => {
    // What breaks if this is deleted: `menuFor` can hand back the company groups for a null answer,
    // which is the fallback the shell test above refuses, proved here without a render.
    const company: NavGroup[] = [{ heading: "Install", sections: [{ to: "/install", label: "This install" }] }];
    const own: NavGroup = { heading: "Use", sections: [{ to: "/ask", label: "Ask" }] };
    const department = readNavigation(departmentConsole());

    expect(menuFor(null, company, own)).toEqual([own]);
    expect(menuFor(readNavigation(COMPANY_CONSOLE), company, own)).toBe(company);
    expect(menuFor(department, company, own).map((one) => one.heading)).toEqual([
      "Operate",
      "Govern",
      "Report",
      "Use",
    ]);
  });
});

describe("the Department page", () => {
  async function departmentPage(answers: Record<string, () => Response>): Promise<HTMLElement> {
    const idp = fakeIdentityProvider({
      api(url) {
        const asked = new URL(url, "https://console.test").pathname;
        return answers[asked]?.() ?? null;
      },
    });
    await signIn(await loadConsole({ idp }));
    const { Department } = await import("../src/pages/Department");
    const { container } = render(
      <MemoryRouter initialEntries={["/department"]}>
        <Department />
      </MemoryRouter>,
    );
    // A loading sentence is a status paragraph; a failure notice is a status too, and is an answer.
    await waitFor(() => {
      if (container.querySelector('p[role="status"]')) {
        throw new Error("the page has not been answered yet");
      }
    });
    return container;
  }

  function json(body: unknown, status = 200): () => Response {
    return () =>
      new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
  }

  const USAGE = {
    start: "2019-02-26T09:00:00Z",
    end: "2019-03-05T09:00:00Z",
    departments: [{ department: "maintenance", questions: 926, people: 31 }],
    people: [
      { person: "u_one", questions: 900 },
      { person: "u_two", questions: 26 },
    ],
    questions: 926,
    machine_included: false,
    not_measured: [],
    tokens: [],
  };

  test("each card draws its own route's answer and links to the screen it came from", async () => {
    // What breaks if this is deleted: the page can draw a figure it computed, or a card with
    // nothing from the API on it, and SCREEN 2's overview is a picture again.
    const container = await departmentPage({
      [NAVIGATION_ADDRESS]: json(departmentConsole(sentinel("scope"))),
      "/api/v1/report/usage": json(USAGE),
      "/api/v1/agents": json({ items: [{ agent_id: "site-health", display_name: sentinel("agent") }] }),
      "/api/v1/report/questions": json({
        start: "2019-02-26T09:00:00Z",
        end: "2019-03-05T09:00:00Z",
        gaps: [],
        nothing_connected: true,
        answered_when_nothing_connected: sentinel("told"),
        answered_when_nothing_found: "not found",
        unanswered_are_recorded: false,
      }),
    });

    expect(container.querySelector("h1")?.textContent).toBe(DEPARTMENT_HEADING);
    const text = container.textContent ?? "";
    expect(text).toContain(sentinel("scope"));
    expect(text).toContain("926");
    expect(text).toContain(sentinel("agent"));
    expect(text).toContain(sentinel("told"));
    expect(text).toContain(NOT_DRAWN_HERE);

    const hrefs = [...container.querySelectorAll("a")].map((one) => one.getAttribute("href"));
    expect(hrefs).toEqual(expect.arrayContaining(["/usage", "/agents", "/agents/site-health", "/questions"]));
    const headings = [...container.querySelectorAll("h2")].map((one) => one.textContent);
    expect(headings).toEqual([USAGE_CARD, AGENTS_CARD, "Your queues", GAPS_CARD]);
  });

  test("a card whose route failed says so and the other cards still draw", async () => {
    // What breaks if this is deleted: one refused read blanks the whole overview, or a failure is
    // drawn as a department with no questions in it.
    const container = await departmentPage({
      [NAVIGATION_ADDRESS]: json(departmentConsole()),
      "/api/v1/report/usage": json({ message: sentinel("refused"), trace_id: "t-1" }, 503),
      "/api/v1/agents": json({ items: [{ agent_id: "site-health", display_name: sentinel("agent") }] }),
      "/api/v1/report/questions": json({
        start: "2019-02-26T09:00:00Z",
        end: "2019-03-05T09:00:00Z",
        gaps: [],
        nothing_connected: false,
        answered_when_nothing_connected: "unused",
        answered_when_nothing_found: "unused",
        unanswered_are_recorded: false,
      }),
    });

    const text = container.textContent ?? "";
    expect(text).toContain(sentinel("refused"));
    expect(text).not.toContain("926");
    expect(text).toContain(sentinel("agent"));
  });

  test("a usage answer with no axis offered is nothing to show, never a zero", async () => {
    // What breaks if this is deleted: a reader offered no usage table is shown "Questions 0", which
    // says their department asked nothing.
    const container = await departmentPage({
      [NAVIGATION_ADDRESS]: json(departmentConsole()),
      "/api/v1/report/usage": json({ ...USAGE, departments: null, people: null, questions: null }),
      "/api/v1/agents": json({ items: [] }),
      "/api/v1/report/questions": json({
        start: "2019-02-26T09:00:00Z",
        end: "2019-03-05T09:00:00Z",
        gaps: [],
        nothing_connected: false,
        answered_when_nothing_connected: "unused",
        answered_when_nothing_found: "unused",
        unanswered_are_recorded: false,
      }),
    });

    const usage = [...container.querySelectorAll("section")].find(
      (one) => one.querySelector("h2")?.textContent === USAGE_CARD,
    );
    expect(usage?.textContent).toContain(NOTHING_TO_SHOW);
    expect(usage?.querySelector("dl")).toBeNull();
  });
});
