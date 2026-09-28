/**
 * Departments and teams, Elevation and Access review: what each asks for, what each shows, the one
 * control and its confirmation, and the four states each says differently. Subscribers is held in
 * `tests/notifications-page.test.tsx` since it was rebuilt on the page kit.
 *
 * Mounted directly on a memory router at each page's own address, for the reason
 * `tests/sessions-page.test.tsx` gives: the route table is shared, and these pages are wired into it
 * by the commit that adds their navigation rows. The failures worth testing are the ones that look
 * like a screen working: a decision sent without a confirmation, a confirmation that paraphrases
 * what happens, a body key the route forbids, a filter offering a department nobody on the page is
 * in, and a sentence about what the install does not record dropping off a page that then draws an
 * empty list as a fact.
 *
 * Task ids: M27.7.4, M27.7.8, M27.7.9, M27.7.12, M27.11.1, M27.15.22
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import {
  AccessReview,
  CANCEL_LABEL,
  DECISION_LABELS,
  MORE_GRANTS,
  NEVER_DECIDED,
  NONE_MATCH as NO_GRANT_MATCHES,
  NOTHING_TO_REVIEW,
  READING_REVIEW,
  THE_BRAIN_COULD_NOT_BE_REACHED,
} from "../src/pages/AccessReview";
import {
  ADD_LABEL,
  APPOINT_LABEL,
  CANCEL_LABEL as KEEP_ORGANISATION,
  CHOOSE_SOMEBODY_FIRST,
  CREATE_TEAM_LABEL,
  DISABLED,
  DISABLE_LABEL,
  DRAW_SCOPE_LABEL,
  Departments,
  ENABLE_LABEL,
  FOUND_HEADING,
  RENAME_DEPARTMENT_LABEL,
  RENAME_LABEL,
  RENAME_TEAM_LABEL,
  RETIRE_DEPARTMENT_LABEL,
  RETIRE_SCOPE_LABEL,
  RETIRE_TEAM_LABEL,
  SCOPES_HEADING,
  NOBODY_IN_TEAM,
  NOBODY_LISTED,
  NONE_MATCH as NO_DEPARTMENT_MATCHES,
  NO_DEPARTMENTS_HERE,
  NO_LEAD,
  READING_DEPARTMENTS,
  REMOVE_LABEL,
  SEARCH_LABEL,
  STAND_DOWN_LABEL,
  UNPLACED_HEADING,
} from "../src/pages/Departments";
import {
  ASK_LABEL,
  DECISION_LABELS as ELEVATION_LABELS,
  Elevation,
  NOT_A_LANDING,
  NO_REQUESTS,
  READING_ELEVATION,
  YOU_HOLD_THE_AUTHORITY,
} from "../src/pages/Elevation";
import { LIST_PAGE_SIZE } from "../src/components/listing";
import {
  ASK_BLANKS,
  FOUNDING_DOES,
  MOST_DECIDED_AT_ONCE,
  STRUCTURE_BLANKS,
  readOrganisation,
  readReview,
  type DepartmentRow,
  type ElevationRequestRow,
  type ReviewRow,
} from "../src/pages/governPeopleQuery";
import { SOMETHING_DID_NOT_WORK } from "../src/pages/Overview";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import {
  declaredParameterSchema,
  declaredQueryParameters,
  declaredRequestBodySchema,
} from "./support/openapi";

const CONSOLE_ORIGIN = "https://console.test";
const DEPARTMENTS_OPERATION = "/api/v1/govern/departments";
const ELEVATION_OPERATION = "/api/v1/govern/elevation";
const REVIEW_OPERATION = "/api/v1/govern/access-review";
const DECISION_OPERATION = "/api/v1/govern/access-review/decision";
const DECISIONS_OPERATION = "/api/v1/govern/access-review/decisions";

const TEAMS = "A team lists the people in it you may see.";
const LEADS = "A department's lead is who leads it, recorded with who appointed them.";
const ORGANISING = "Placing somebody or appointing a lead takes the authority the Access review screen asks for.";
const MEMBERSHIP_OPERATION = "/api/v1/govern/departments/membership";
const RENAME_OPERATION = "/api/v1/govern/departments/rename";
const RETIREMENT_OPERATION = "/api/v1/govern/departments/retirement";
const TEAM_OPERATION = "/api/v1/govern/departments/team";
const TEAM_RENAME_OPERATION = "/api/v1/govern/departments/team/rename";
const TEAM_RETIREMENT_OPERATION = "/api/v1/govern/departments/team/retirement";
const SCOPE_OPERATION = "/api/v1/govern/departments/scopes";
const SCOPE_RETIREMENT_OPERATION = "/api/v1/govern/departments/scopes/retirement";
const SCOPES_READ = "/api/v1/govern/scopes";
const RETIRING_DEPARTMENT =
  "Retiring a department retires its teams and every live scope naming it. A department is not retired while a live grant is still written over it.";
const RETIRING_TEAM = "Retiring a team takes it off this page. Nobody's access changes.";
const RETIRING_SCOPE = "Retiring a scope stops any new grant being written over it.";
const UNDER_LIVE_GRANTS =
  "Nothing was changed: A department is not retired while a live grant is still written over it.";
const LEAD_OPERATION = "/api/v1/govern/departments/lead";
const DISABLE_OPERATION = "/api/v1/govern/people/disable";
const ENABLE_OPERATION = "/api/v1/govern/people/enable";
const DISABLING = "Disabling somebody stops their sign-in, ends every session they have.";
const REQUESTS_OPERATION = "/api/v1/govern/elevation/requests";
const COUNTED = "No headcount is shown.";
const KEEPING = "Keeping a grant records that you reviewed it and it stands.";
const REMOVING = "Removing a grant takes it away from the next request the person makes.";
const SHOWS = "Only grants you could have written are listed.";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

type Answer = (url: URL, init: RequestInit | undefined) => Response | null;

const PAGES = {
  "/departments": { element: <Departments />, reading: READING_DEPARTMENTS },
  "/elevation": { element: <Elevation />, reading: READING_ELEVATION },
  "/access_review": { element: <AccessReview />, reading: READING_REVIEW },
} as const;

async function mount(
  address: keyof typeof PAGES,
  answer: Answer,
): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      return answer(new URL(url, CONSOLE_ORIGIN), init);
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const page = PAGES[address];
  const router = createMemoryRouter([{ path: address, element: page.element }], {
    initialEntries: [address],
  });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (container.textContent?.includes(page.reading)) {
      throw new Error("still reading");
    }
  });
  return { container, idp };
}

function posts(idp: FakeIdp): { url: URL; body: unknown }[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST" && new URL(call.url, CONSOLE_ORIGIN).pathname.startsWith("/api/"))
    .map((call) => ({
      url: new URL(call.url, CONSOLE_ORIGIN),
      body: JSON.parse(String(call.init?.body ?? "null")) as unknown,
    }));
}

function sentQuery(idp: FakeIdp, operation: string): string[] {
  return idp.urls
    .filter((url) => new URL(url, CONSOLE_ORIGIN).pathname === operation)
    .flatMap((url) => [...new URL(url, CONSOLE_ORIGIN).searchParams.keys()]);
}

// ------------------------------------------------------------------ departments

function organisation(departments: DepartmentRow[], truncated = false, mayOrganise = false): unknown {
  return {
    items: departments,
    unplaced: [{ principal_id: "u_9", display_name: "Nowhere Person", disabled: false, department: null }],
    truncated,
    may_organise: mayOrganise,
    teams: TEAMS,
    leads: LEADS,
    counted: COUNTED,
    organising: ORGANISING,
  };
}

const WEI = { principal_id: "u_1", display_name: "Wei Ling Tan", disabled: false };
const SITI = { principal_id: "u_3", display_name: "Siti Rahman", disabled: false };
const WEB: DepartmentRow = {
  slug: "web",
  name: "Web",
  teams: [{ slug: "design", name: "Design", members: [WEI] }],
  members: [WEI, { principal_id: "u_2", display_name: "Aaron Lim", disabled: true }, SITI],
  lead: WEI,
};
const FINANCE: DepartmentRow = { slug: "finance", name: "Finance", teams: [], members: [], lead: null };

describe("the departments and teams screen", () => {
  test("it asks only what the route declares, at a size the route answers", async () => {
    // What breaks if this is deleted: a parameter the API ignores, or a page size it refuses on
    // every load.
    const declared = new Set(declaredQueryParameters(DEPARTMENTS_OPERATION, "get"));
    const limit = declaredParameterSchema(DEPARTMENTS_OPERATION, "get", "limit");
    const { idp } = await mount("/departments", (url) =>
      url.pathname === DEPARTMENTS_OPERATION ? json(organisation([])) : null,
    );

    const sent = sentQuery(idp, DEPARTMENTS_OPERATION);
    expect(sent.length).toBeGreaterThan(0);
    expect(sent.filter((name) => !declared.has(name))).toEqual([]);
    expect(LIST_PAGE_SIZE).toBeLessThanOrEqual(limit["maximum"] as number);
  });

  test("a department shows its teams and its people, each person leads to what they hold, and the three sentences are said", async () => {
    // What breaks if this is deleted: the page draws a team with nobody in it as a fact about the
    // team, or drops the link from the tree to the entitlement the design puts beside it.
    const { container } = await mount("/departments", (url) =>
      url.pathname === DEPARTMENTS_OPERATION ? json(organisation([FINANCE, WEB])) : null,
    );

    const people = container.querySelector('[aria-label="People in Web"]') as HTMLElement;
    expect(people.textContent).toContain("Wei Ling Tan");
    expect(people.textContent).toContain(DISABLED);
    expect(people.querySelector("a")?.getAttribute("href")).toBe("/people/principal%3Au_1");
    expect(container.querySelector('[aria-label="Teams in Web"]')?.textContent).toContain("web.design");
    expect(container.textContent).toContain(NOBODY_LISTED);
    expect(container.textContent).toContain(UNPLACED_HEADING);
    expect(container.querySelector('[aria-label="Members of Design"]')?.textContent).toContain("Wei Ling Tan");
    expect(container.querySelector('[aria-label="Lead of Web"]')?.textContent).toContain("Wei Ling Tan");
    expect(container.textContent).toContain(NO_LEAD);
    for (const sentence of [TEAMS, LEADS, COUNTED]) {
      expect(container.textContent).toContain(sentence);
    }
    // A reader who may not organise is offered no control and not told who may.
    expect(container.querySelector("button")).toBeNull();
    expect(container.textContent).not.toContain(ORGANISING);
    expect(container.textContent).not.toMatch(/\b\d+\s+(people|members|departments|teams)\b/i);
  });

  test("an organiser adds and removes a member, appoints and stands down a lead, each confirmed in the API's words", async () => {
    // What breaks if this is deleted: a placement is sent without a confirmation, the confirmation
    // paraphrases what happens, a body key the route forbids is sent, or somebody already in the
    // team, or disabled, is offered.
    const sent: { path: string; body: unknown }[] = [];
    const { container, idp } = await mount("/departments", (url, init) => {
      if (url.pathname === DEPARTMENTS_OPERATION) {
        return json(organisation([WEB], false, true));
      }
      if (init?.method === "POST" && (url.pathname === MEMBERSHIP_OPERATION || url.pathname === LEAD_OPERATION)) {
        sent.push({ path: url.pathname, body: JSON.parse(String(init.body)) });
        return json({ department: "web", team: null, principal_id: null, change: "join", at: "2019-03-04T09:00:00Z" });
      }
      return null;
    });
    const buttonNamed = (label: string) =>
      [...container.querySelectorAll("button")].find((one) => one.textContent === label) as HTMLButtonElement;
    const choose = (label: string, value: string) => {
      const select = [...container.querySelectorAll("select")].find((one) =>
        one.closest("label")?.textContent?.startsWith(label),
      ) as HTMLSelectElement;
      expect([...select.options].map((one) => one.value)).not.toContain("u_2");
      fireEvent.change(select, { target: { value } });
    };

    expect(container.textContent).toContain(ORGANISING);
    fireEvent.click(buttonNamed(ADD_LABEL));
    expect(container.textContent).toContain(CHOOSE_SOMEBODY_FIRST);
    expect(container.querySelector(".confirm")).toBeNull();
    choose("Add to Design", "u_3");
    expect([...container.querySelectorAll("select")][1]?.textContent).not.toContain("Wei Ling Tan");
    fireEvent.click(buttonNamed(ADD_LABEL));
    expect(container.textContent).toContain("Add Siti Rahman to Design?");
    expect(container.textContent).toContain(TEAMS);
    expect(posts(idp)).toEqual([]);
    fireEvent.click(buttonNamed(KEEP_ORGANISATION));
    fireEvent.click(buttonNamed(ADD_LABEL));
    fireEvent.click([...container.querySelectorAll(".confirm button")][1] as HTMLButtonElement);
    await waitFor(() => {
      expect(sent).toHaveLength(1);
    });
    expect(sent[0]).toEqual({
      path: MEMBERSHIP_OPERATION,
      body: { department: "web", team: "design", principal_id: "u_3", change: "join" },
    });
    expect(Object.keys(sent[0]?.body as object).sort()).toEqual(
      Object.keys(declaredRequestBodySchema(MEMBERSHIP_OPERATION, "post")["properties"] as object).sort(),
    );

    await waitFor(() => {
      expect(buttonNamed(REMOVE_LABEL)).toBeDefined();
    });
    fireEvent.click(buttonNamed(REMOVE_LABEL));
    expect(container.textContent).toContain("Take Wei Ling Tan out of Design?");
    fireEvent.click([...container.querySelectorAll(".confirm button")][1] as HTMLButtonElement);
    await waitFor(() => {
      expect(sent).toHaveLength(2);
    });
    expect(sent[1]?.body).toEqual({ department: "web", team: "design", principal_id: "u_1", change: "leave" });

    await waitFor(() => {
      expect(buttonNamed(STAND_DOWN_LABEL)).toBeDefined();
    });
    fireEvent.click(buttonNamed(STAND_DOWN_LABEL));
    expect(container.textContent).toContain("Stand Wei Ling Tan down as lead of Web?");
    expect(container.textContent).toContain(LEADS);
    fireEvent.click([...container.querySelectorAll(".confirm button")][1] as HTMLButtonElement);
    await waitFor(() => {
      expect(sent).toHaveLength(3);
    });
    expect(sent[2]).toEqual({ path: LEAD_OPERATION, body: { department: "web", change: "stand_down" } });

    await waitFor(() => {
      expect(buttonNamed(APPOINT_LABEL)).toBeDefined();
    });
    choose("Lead of Web", "u_3");
    fireEvent.click(buttonNamed(APPOINT_LABEL));
    fireEvent.click([...container.querySelectorAll(".confirm button")][1] as HTMLButtonElement);
    await waitFor(() => {
      expect(sent).toHaveLength(4);
    });
    expect(sent[3]?.body).toEqual({ department: "web", change: "appoint", principal_id: "u_3" });
  });

  test("a reader holding the grant decision disables and enables a person, confirmed in the API's words", async () => {
    // What breaks if this is deleted: the control is drawn for a reader who may not use it, a
    // disable is sent without a confirmation naming the person, the confirmation paraphrases what
    // disabling does, or a body key the route forbids is sent.
    const sent: { path: string; body: unknown }[] = [];
    const { container } = await mount("/departments", (url, init) => {
      if (url.pathname === DEPARTMENTS_OPERATION) {
        return json({ ...(organisation([WEB]) as object), may_disable: true, disabling: DISABLING });
      }
      if (init?.method === "POST" && (url.pathname === DISABLE_OPERATION || url.pathname === ENABLE_OPERATION)) {
        sent.push({ path: url.pathname, body: JSON.parse(String(init.body)) });
        return json({ principal_id: "u_3", disabled: true, disabled_at: null, outcome: "changed", at: "2019-03-04T09:00:00Z" });
      }
      return null;
    });
    const people = container.querySelector('[aria-label="People in Web"]') as HTMLElement;
    const named = (label: string) =>
      [...people.querySelectorAll("button")].find((one) => one.getAttribute("aria-label") === label) as HTMLButtonElement;

    expect(named(`${ENABLE_LABEL}: Aaron Lim`)).toBeDefined();
    fireEvent.click(named(`${DISABLE_LABEL}: Siti Rahman`));
    expect(container.textContent).toContain("Disable Siti Rahman's sign-in?");
    expect(container.textContent).toContain(DISABLING);
    expect(sent).toEqual([]);
    fireEvent.click([...container.querySelectorAll(".confirm button")][1] as HTMLButtonElement);
    await waitFor(() => {
      expect(sent).toHaveLength(1);
    });
    expect(sent[0]).toEqual({ path: DISABLE_OPERATION, body: { principal_id: "u_3" } });
    expect(Object.keys(sent[0]?.body as object).sort()).toEqual(
      Object.keys(declaredRequestBodySchema(DISABLE_OPERATION, "post")["properties"] as object).sort(),
    );

    await waitFor(() => {
      expect(named(`${ENABLE_LABEL}: Aaron Lim`)).toBeDefined();
    });
    fireEvent.click(named(`${ENABLE_LABEL}: Aaron Lim`));
    expect(container.textContent).toContain("Enable Aaron Lim's sign-in again?");
    fireEvent.click([...container.querySelectorAll(".confirm button")][1] as HTMLButtonElement);
    await waitFor(() => {
      expect(sent).toHaveLength(2);
    });
    expect(sent[1]).toEqual({ path: ENABLE_OPERATION, body: { principal_id: "u_2" } });
  });

  test("a refused placement is the API's sentence and the team still reads as the API sent it", async () => {
    // What breaks if this is deleted: a refusal is swallowed and the page says the person was added,
    // or an empty team is drawn as a fact about the team rather than about this reader.
    const { container } = await mount("/departments", (url, init) => {
      if (url.pathname === DEPARTMENTS_OPERATION) {
        return json(organisation([{ ...WEB, teams: [{ slug: "design", name: "Design", members: [] }] }], false, true));
      }
      if (init?.method === "POST") {
        return json({ message: "that change to the organisation is not writable by this caller", trace_id: "t" }, 404);
      }
      return null;
    });
    expect(container.textContent).toContain(NOBODY_IN_TEAM);
    const select = [...container.querySelectorAll("select")].find((one) =>
      one.closest("label")?.textContent?.startsWith("Add to Design"),
    ) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "u_1" } });
    fireEvent.click([...container.querySelectorAll("button")].find((one) => one.textContent === ADD_LABEL) as HTMLButtonElement);
    fireEvent.click([...container.querySelectorAll(".confirm button")][1] as HTMLButtonElement);
    await waitFor(() => {
      expect(container.textContent).toContain("that change to the organisation is not writable by this caller");
    });
  });

  test("the search and the team filter are requests, and the team filter offers only teams drawn", async () => {
    // What breaks if this is deleted: a search that narrows the departments already drawn, which
    // reads as a search of the organisation and is one of what arrived, or a team dropdown naming
    // a team on no department this reader was shown.
    const { container, idp } = await mount("/departments", (url) =>
      url.pathname === DEPARTMENTS_OPERATION
        ? json(organisation(url.searchParams.get("q") === "zzz" ? [] : [FINANCE, WEB]))
        : null,
    );
    const box = container.querySelector('input[type="search"]') as HTMLInputElement;
    const team = [...container.querySelectorAll("select")].find((one) =>
      one.closest("label")?.firstChild?.textContent?.trim() === "Team",
    ) as HTMLSelectElement;
    const drawn = [FINANCE, WEB].flatMap((one) => one.teams.map((each) => each.name));

    expect([...team.querySelectorAll("option")].map((one) => one.value).filter((one) => one !== "")).toEqual(
      [...new Set(drawn)].sort((a, b) => a.localeCompare(b)),
    );
    fireEvent.change(box, { target: { value: "zzz" } });
    await waitFor(() => {
      expect(container.textContent).toContain(NO_DEPARTMENT_MATCHES);
    });
    const asked = idp.urls
      .map((url) => new URL(url, CONSOLE_ORIGIN))
      .filter((url) => url.pathname === DEPARTMENTS_OPERATION);
    expect(asked[asked.length - 1]?.searchParams.get("q")).toBe("zzz");
  });

  test("empty, unreachable and refused are three different sentences", async () => {
    // What breaks if this is deleted: "there are no departments" is said when the Brain could not
    // be reached, which is the one confusion `docs/admin-console.md` names.
    const empty = await mount("/departments", (url) =>
      url.pathname === DEPARTMENTS_OPERATION ? json(organisation([])) : null,
    );
    expect(empty.container.textContent).toContain(NO_DEPARTMENTS_HERE);

    const refused = await mount("/departments", (url) =>
      url.pathname === DEPARTMENTS_OPERATION ? json({ message: "I could not find that.", trace_id: "t" }, 404) : null,
    );
    expect(refused.container.textContent).toContain(SOMETHING_DID_NOT_WORK);

    const unreachable = await mount("/departments", (url) => {
      if (url.pathname === DEPARTMENTS_OPERATION) {
        throw new TypeError("offline");
      }
      return null;
    });
    expect(unreachable.container.textContent).toContain(THE_BRAIN_COULD_NOT_BE_REACHED);
    expect(Object.keys(readOrganisation({ items: [], total: 4 })).sort()).toEqual([
      "counted",
      "departments",
      "disabling",
      "leads",
      "mayDisable",
      "mayDrawScopes",
      "mayFound",
      "mayOrganise",
      "organising",
      "retiringDepartment",
      "retiringScope",
      "retiringTeam",
      "shaping",
      "teams",
      "truncated",
      "unplaced",
    ]);
  });

  // ---------------------------------------------------------------- the structure (M27.11.1)

  function structured(overrides: Record<string, unknown>, departments: DepartmentRow[] = [{ ...WEB, shapeable: true }]): unknown {
    return {
      ...(organisation(departments) as object),
      retiring_department: RETIRING_DEPARTMENT,
      retiring_team: RETIRING_TEAM,
      retiring_scope: RETIRING_SCOPE,
      ...overrides,
    };
  }

  type Sent = { path: string; body: unknown };

  /** A page answering the organisation and recording each write, which it answers with `reply`. */
  async function structurePage(
    body: unknown,
    reply: (path: string) => Response = () => json({ kind: "department", department: null, slug: "x", change: "created", at: "2019-03-04T09:00:00Z" }),
    scopes: unknown = { items: [], truncated: false, departments: [] },
  ) {
    const sent: Sent[] = [];
    const mounted = await mount("/departments", (url, init) => {
      if (init?.method === "POST") {
        sent.push({ path: url.pathname, body: JSON.parse(String(init.body)) });
        return reply(url.pathname);
      }
      if (url.pathname === DEPARTMENTS_OPERATION) {
        return json(body);
      }
      return url.pathname === SCOPES_READ ? json(scopes) : null;
    });
    const { container } = mounted;
    const labelled = (label: string) =>
      [...container.querySelectorAll("button")].find(
        (one) => one.getAttribute("aria-label") === label || (one.textContent === label && one.getAttribute("aria-label") === null),
      ) as HTMLButtonElement | undefined;
    const confirm = () => {
      fireEvent.click([...container.querySelectorAll(".confirm button")][1] as HTMLButtonElement);
    };
    const fill = (form: HTMLFormElement, label: string, value: string) => {
      const field = [...form.querySelectorAll("label")].find((one) => one.textContent?.startsWith(label))?.querySelector("input, select");
      fireEvent.change(field as HTMLInputElement, { target: { value } });
    };
    const form = (label: string) => container.querySelector(`form[aria-label="${label}"]`) as HTMLFormElement;
    const declared = (path: string) =>
      Object.keys(declaredRequestBodySchema(path, "post")["properties"] as object).sort();
    return { ...mounted, sent, labelled, confirm, fill, form, declared };
  }

  test("an administrator creates, renames and retires a department, each confirmed and sending only the declared keys", async () => {
    // What breaks if this is deleted: a department is created or retired without a confirmation, a
    // rename sends the short name or omits the name the page showed, a blank or unchanged name is
    // sent, or the retirement's confirmation paraphrases what happens to scopes and grants.
    const page = await structurePage(structured({ may_found: true }));
    const { container, sent, labelled, confirm, fill, form, declared } = page;

    const founding = form(FOUND_HEADING);
    fireEvent.submit(founding);
    expect(container.textContent).toContain(STRUCTURE_BLANKS.slug);
    expect(container.querySelector(".confirm")).toBeNull();
    fill(founding, "Short name", "sales");
    fill(founding, "Name", "Sales");
    fireEvent.submit(founding);
    expect(container.textContent).toContain("Create the department Sales, short name sales?");
    expect(container.textContent).toContain(FOUNDING_DOES);
    expect(sent).toEqual([]);
    confirm();
    await waitFor(() => {
      expect(sent).toHaveLength(1);
    });
    expect(sent[0]).toEqual({ path: DEPARTMENTS_OPERATION, body: { slug: "sales", name: "Sales" } });
    expect(Object.keys(sent[0]?.body as object).sort()).toEqual(declared(DEPARTMENTS_OPERATION));
    await waitFor(() => {
      expect(container.textContent).toContain("Done: Create the department Sales, short name sales, recorded at");
    });

    fireEvent.click(labelled(`${RENAME_DEPARTMENT_LABEL}: Web`) as HTMLButtonElement);
    const renaming = form(`${RENAME_DEPARTMENT_LABEL}: Web`);
    expect((renaming.querySelector("input") as HTMLInputElement).value).toBe("Web");
    fireEvent.submit(renaming);
    expect(container.textContent).toContain(STRUCTURE_BLANKS.same);
    expect(container.querySelector(".confirm")).toBeNull();
    fill(renaming, "New name", "Web and design");
    fireEvent.submit(renaming);
    expect(container.textContent).toContain("Rename the department Web to Web and design?");
    confirm();
    await waitFor(() => {
      expect(sent).toHaveLength(2);
    });
    expect(sent[1]).toEqual({ path: RENAME_OPERATION, body: { slug: "web", expected_name: "Web", name: "Web and design" } });
    expect(Object.keys(sent[1]?.body as object).sort()).toEqual(declared(RENAME_OPERATION));

    await waitFor(() => {
      expect(labelled(`${RETIRE_DEPARTMENT_LABEL}: Web`)).toBeDefined();
    });
    fireEvent.click(labelled(`${RETIRE_DEPARTMENT_LABEL}: Web`) as HTMLButtonElement);
    expect(container.textContent).toContain("Retire the department Web?");
    expect(container.textContent).toContain(RETIRING_DEPARTMENT);
    confirm();
    await waitFor(() => {
      expect(sent).toHaveLength(3);
    });
    expect(sent[2]).toEqual({ path: RETIREMENT_OPERATION, body: { slug: "web", expected_name: "Web" } });
    expect(Object.keys(sent[2]?.body as object).sort()).toEqual(declared(RETIREMENT_OPERATION));
  });

  test("a department under a live grant is refused in the API's one sentence and still drawn", async () => {
    // What breaks if this is deleted: M27.15.22's refusal is swallowed and the page says the
    // department was retired, or the page stops drawing the department the API kept.
    const { container, labelled, confirm } = await structurePage(structured({ may_found: true }), () =>
      json({ message: UNDER_LIVE_GRANTS, trace_id: "t" }, 404),
    );
    fireEvent.click(labelled(`${RETIRE_DEPARTMENT_LABEL}: Web`) as HTMLButtonElement);
    confirm();
    await waitFor(() => {
      expect(container.textContent).toContain(UNDER_LIVE_GRANTS);
    });
    expect(container.textContent).not.toContain("Done:");
    expect(container.querySelector('[aria-label="People in Web"]')).not.toBeNull();
  });

  test("a department administrator creates, renames and retires a team, and is offered nothing over departments", async () => {
    // What breaks if this is deleted: a team is written without a confirmation or with a key the
    // route forbids, a team's retirement paraphrases what it does, or a reader who may shape one
    // department is offered to create or retire departments, which every press would refuse.
    const { container, sent, labelled, confirm, fill, form, declared } = await structurePage(structured({}));

    expect(container.querySelector(`form[aria-label="${FOUND_HEADING}"]`)).toBeNull();
    expect(labelled(`${RETIRE_DEPARTMENT_LABEL}: Web`)).toBeUndefined();
    expect(container.textContent).not.toContain(SCOPES_HEADING);

    const adding = form(`${CREATE_TEAM_LABEL} in Web`);
    fireEvent.submit(adding);
    expect(container.textContent).toContain(STRUCTURE_BLANKS.name);
    fill(adding, "Short name", "hosting");
    fill(adding, "Name", "Hosting");
    fireEvent.submit(adding);
    expect(container.textContent).toContain("Create the team Hosting, short name hosting, in Web?");
    confirm();
    await waitFor(() => {
      expect(sent).toHaveLength(1);
    });
    expect(sent[0]).toEqual({ path: TEAM_OPERATION, body: { department: "web", slug: "hosting", name: "Hosting" } });
    expect(Object.keys(sent[0]?.body as object).sort()).toEqual(declared(TEAM_OPERATION));

    await waitFor(() => {
      expect(labelled(`${RENAME_TEAM_LABEL}: Design`)).toBeDefined();
    });
    fireEvent.click(labelled(`${RENAME_TEAM_LABEL}: Design`) as HTMLButtonElement);
    const renaming = form(`${RENAME_TEAM_LABEL}: Design`);
    fill(renaming, "New name", "   ");
    fireEvent.submit(renaming);
    expect(container.textContent).toContain(STRUCTURE_BLANKS.rename);
    fill(renaming, "New name", "Visual design");
    fireEvent.submit(renaming);
    confirm();
    await waitFor(() => {
      expect(sent).toHaveLength(2);
    });
    expect(sent[1]).toEqual({
      path: TEAM_RENAME_OPERATION,
      body: { department: "web", slug: "design", expected_name: "Design", name: "Visual design" },
    });
    expect(Object.keys(sent[1]?.body as object).sort()).toEqual(declared(TEAM_RENAME_OPERATION));

    await waitFor(() => {
      expect(labelled(`${RETIRE_TEAM_LABEL}: Design`)).toBeDefined();
    });
    fireEvent.click(labelled(`${RETIRE_TEAM_LABEL}: Design`) as HTMLButtonElement);
    expect(container.textContent).toContain("Retire the team Design?");
    expect(container.textContent).toContain(RETIRING_TEAM);
    confirm();
    await waitFor(() => {
      expect(sent).toHaveLength(3);
    });
    expect(sent[2]).toEqual({
      path: TEAM_RETIREMENT_OPERATION,
      body: { department: "web", slug: "design", expected_name: "Design" },
    });
    expect(Object.keys(sent[2]?.body as object).sort()).toEqual(declared(TEAM_RETIREMENT_OPERATION));
    expect(RENAME_LABEL).toBe("Rename");
  });

  test("a scope is drawn over departments on the page and retired in the API's words, and the two never retired offer nothing", async () => {
    // What breaks if this is deleted: the scope form offers a department nobody on the page is in,
    // sends a team with two departments, sends a key the route forbids, retires a scope against a
    // predicate other than the one drawn, or offers to retire a department's own scope or the
    // company-wide one, which the route refuses every time.
    const WEB_ALL = { slug: "web_all", label: "All of web", is_department: false, scope: { clauses: [{ field: "department", op: "eq", value: "web" }] } };
    const scopes = {
      items: [
        { slug: "company", label: "The company", is_department: false, scope: { clauses: [] } },
        { slug: "web", label: "Web", is_department: true, scope: { clauses: [{ field: "department", op: "eq", value: "web" }] } },
        WEB_ALL,
      ],
      truncated: false,
      departments: ["web"],
    };
    const { container, sent, labelled, confirm, fill, form, declared } = await structurePage(
      structured({ may_draw_scopes: true }, [{ ...WEB, shapeable: true }, FINANCE]),
      undefined,
      scopes,
    );
    await waitFor(() => {
      expect(container.querySelector(`[aria-label="${SCOPES_HEADING}"]`)?.textContent).toContain("All of web");
    });
    expect([...container.querySelectorAll("button")].filter((one) => one.textContent === RETIRE_SCOPE_LABEL)).toHaveLength(1);

    const drawing = form(DRAW_SCOPE_LABEL);
    fireEvent.submit(drawing);
    expect(container.textContent).toContain(STRUCTURE_BLANKS.departments);
    expect(container.querySelector(".confirm")).toBeNull();
    const boxes = [...drawing.querySelectorAll('input[type="checkbox"]')] as HTMLInputElement[];
    expect(boxes.map((one) => one.closest("label")?.textContent?.trim())).toEqual(["Web web", "Finance finance"]);
    fireEvent.click(boxes[1] as HTMLInputElement);
    fireEvent.click(boxes[0] as HTMLInputElement);
    expect(drawing.querySelector("select")).toBeNull();
    fireEvent.click(boxes[1] as HTMLInputElement);
    fill(drawing, "Only this team", "design");
    fill(drawing, "Short name", "web_design");
    fill(drawing, "Name", "Web design");
    fireEvent.submit(drawing);
    expect(container.textContent).toContain("Draw the scope Web design, short name web_design?");
    confirm();
    await waitFor(() => {
      expect(sent).toHaveLength(1);
    });
    expect(sent[0]).toEqual({
      path: SCOPE_OPERATION,
      body: { slug: "web_design", label: "Web design", departments: ["web"], team: "design" },
    });
    expect(Object.keys(sent[0]?.body as object).sort()).toEqual(declared(SCOPE_OPERATION));

    await waitFor(() => {
      expect(labelled(`${RETIRE_SCOPE_LABEL}: All of web`)).toBeDefined();
    });
    fireEvent.click(labelled(`${RETIRE_SCOPE_LABEL}: All of web`) as HTMLButtonElement);
    expect(container.textContent).toContain("Retire the scope All of web?");
    expect(container.textContent).toContain(RETIRING_SCOPE);
    confirm();
    await waitFor(() => {
      expect(sent).toHaveLength(2);
    });
    expect(sent[1]).toEqual({ path: SCOPE_RETIREMENT_OPERATION, body: { slug: "web_all", expected_scope: WEB_ALL.scope } });
    expect(Object.keys(sent[1]?.body as object).sort()).toEqual(declared(SCOPE_RETIREMENT_OPERATION));
  });
});

// ------------------------------------------------------------------ elevation

function aRequest(overrides: Partial<ElevationRequestRow> & { request_id: string }): ElevationRequestRow {
  return {
    principal_id: "u_1",
    display_name: "Wei Ling Tan",
    department: "web",
    capability: "read:client.name",
    scope_slug: "web_all",
    reason: "incident_response",
    explanation: "the portal is down",
    hours: 2,
    requested_at: "2019-03-04T09:00:00Z",
    state: "pending",
    decided_by: null,
    decided_at: null,
    lapses_at: null,
    decidable: false,
    ...overrides,
  };
}

const LANDING = {
  prompt: "This account holds standing access of its own.",
  holds_nothing_standing: false,
  may_authorise: true,
  reasons: ["install", "incident_response"],
  longest_hours: 4,
  items: [] as ElevationRequestRow[],
  truncated: false,
  what: "An elevation is one capability, at a named scope, for one person.",
  recorded: "Every request is kept with who asked, for what and why.",
  notified: "Nobody is sent a notice when somebody asks or is approved.",
  authorising: "Approving or denying an elevation takes the same authority the Access review screen asks for.",
};

describe("the elevation screen", () => {
  test("it shows the reader's standing, the rules, what is recorded and who is not told, and an empty list says so", async () => {
    // What breaks if this is deleted: the page draws an empty table of requests, the sentence
    // saying nobody is notified drops off, or the rules a request is held to disappear.
    const { container } = await mount("/elevation", (url) =>
      url.pathname === ELEVATION_OPERATION ? json(LANDING) : null,
    );

    expect(container.textContent).toContain(LANDING.prompt);
    expect(container.textContent).toContain(LANDING.recorded);
    expect(container.textContent).toContain(LANDING.notified);
    expect(container.textContent).toContain("incident response");
    expect(container.textContent).toContain("4 hours");
    expect(container.textContent).toContain(YOU_HOLD_THE_AUTHORITY);
    expect(container.textContent).toContain(NO_REQUESTS);
    expect(container.querySelector("table")).toBeNull();
  });

  test("a request is asked for through a confirmation, and a blank one is answered before anything is sent", async () => {
    // What breaks if this is deleted: an empty request reaches the API, a request is sent without a
    // confirmation naming the capability, the scope and the hours, or a body key the route forbids
    // is sent.
    const sent: unknown[] = [];
    const { container } = await mount("/elevation", (url, init) => {
      if (url.pathname === ELEVATION_OPERATION) {
        return json(LANDING);
      }
      if (url.pathname === REQUESTS_OPERATION && init?.method === "POST") {
        sent.push(JSON.parse(String(init.body)));
        return json({ request_id: "r_1", requested_at: "2019-03-04T09:00:00Z" }, 201);
      }
      return null;
    });
    const form = container.querySelector('form[aria-label="Ask for an elevation"]') as HTMLFormElement;
    fireEvent.submit(form);
    expect(container.textContent).toContain(ASK_BLANKS.capability);
    expect(container.textContent).toContain(ASK_BLANKS.explanation);
    expect(sent).toEqual([]);

    const inputs = form.querySelectorAll("input");
    fireEvent.change(inputs[0] as HTMLInputElement, { target: { value: " read:client.name " } });
    fireEvent.change(inputs[1] as HTMLInputElement, { target: { value: "web_all" } });
    const [reason, hours] = [...form.querySelectorAll("select")];
    fireEvent.change(reason as HTMLSelectElement, { target: { value: "incident_response" } });
    fireEvent.change(hours as HTMLSelectElement, { target: { value: "2" } });
    fireEvent.change(form.querySelector("textarea") as HTMLTextAreaElement, { target: { value: "the portal is down" } });
    fireEvent.submit(form);
    expect(container.textContent).toContain("Ask for read:client.name over web_all for 2 hours?");
    expect(container.textContent).toContain(LANDING.what);
    expect(sent).toEqual([]);
    fireEvent.click([...container.querySelectorAll(".confirm button")][1] as HTMLButtonElement);
    await waitFor(() => {
      expect(sent).toHaveLength(1);
    });
    expect(sent[0]).toEqual({
      capability: "read:client.name",
      scope_slug: "web_all",
      reason: "incident_response",
      explanation: "the portal is down",
      hours: 2,
    });
    expect(Object.keys(sent[0] as object).sort()).toEqual(
      Object.keys(declaredRequestBodySchema(REQUESTS_OPERATION, "post")["properties"] as object).sort(),
    );
    expect(ASK_LABEL).toBe("Ask for this");
  });

  test("a decidable request is approved or denied through a confirmation, and one that is not offers nothing", async () => {
    // What breaks if this is deleted: a decision is sent without a confirmation, a request the API
    // said this reader may not decide is offered buttons, or the decision word is not the route's.
    const decisions: { path: string; body: unknown }[] = [];
    const rows = [
      aRequest({ request_id: "r_open", decidable: true }),
      aRequest({ request_id: "r_live", state: "live", lapses_at: "2019-03-04T11:00:00Z", decided_by: "u_9" }),
    ];
    const { container } = await mount("/elevation", (url, init) => {
      if (url.pathname === ELEVATION_OPERATION) {
        return json({ ...LANDING, items: rows });
      }
      if (init?.method === "POST" && url.pathname.startsWith(REQUESTS_OPERATION)) {
        decisions.push({ path: url.pathname, body: JSON.parse(String(init.body)) });
        return json({ request_id: "r_open", principal_id: "u_1", decision: "denied", decided_at: "2019-03-04T09:00:00Z", lapses_at: null });
      }
      return null;
    });
    const table = container.querySelector('table[aria-label="Elevation requests"]') as HTMLTableElement;
    expect(table.querySelectorAll("tbody tr")).toHaveLength(2);
    expect(table.querySelectorAll("tbody tr")[1]?.querySelector("button")).toBeNull();
    expect(table.textContent).toContain("Given, until it lapses");

    fireEvent.click(table.querySelector(`button[aria-label^="${ELEVATION_LABELS.denied}"]`) as HTMLButtonElement);
    expect(container.textContent).toContain("Refuse Wei Ling Tan read:client.name over web_all for 2 hours?");
    expect(container.textContent).toContain(LANDING.recorded);
    expect(decisions).toEqual([]);
    fireEvent.click([...container.querySelectorAll(".confirm button")][1] as HTMLButtonElement);
    await waitFor(() => {
      expect(decisions).toHaveLength(1);
    });
    expect(decisions[0]).toEqual({ path: `${REQUESTS_OPERATION}/r_open/decision`, body: { decision: "denied" } });
  });

  test("a reader without the authority is told nothing about it, and an unreadable body is its own sentence", async () => {
    // What breaks if this is deleted: this console composes a sentence about a refusal the API
    // never made, or a body that is not a landing renders as a blank card.
    const without = await mount("/elevation", (url) =>
      url.pathname === ELEVATION_OPERATION ? json({ ...LANDING, may_authorise: false }) : null,
    );
    expect(without.container.textContent).not.toContain(YOU_HOLD_THE_AUTHORITY);

    const odd = await mount("/elevation", (url) => (url.pathname === ELEVATION_OPERATION ? json({}) : null));
    expect(odd.container.textContent).toContain(NOT_A_LANDING);
  });
});

// ------------------------------------------------------------------ access review

function row(overrides: Partial<ReviewRow> & { row_id: string }): ReviewRow {
  return {
    kind: "grant",
    principal_id: "u_1",
    display_name: "Wei Ling Tan",
    department: "web",
    capabilities: ["read:client.name"],
    pack: null,
    scope: { clauses: [{ field: "department", op: "eq", value: "web" }] },
    granted_by: "u_seed",
    reason: "covering the rota",
    granted_at: "2019-03-04T09:00:00Z",
    lapses_at: null,
    last_decision: null,
    last_decided_by: null,
    last_decided_at: null,
    ...overrides,
  };
}

function review(items: ReviewRow[], truncated = false): unknown {
  return { items, truncated, shows: SHOWS, keeping: KEEPING, removing: REMOVING };
}

function buttonNamed(container: HTMLElement, text: string, within = ""): HTMLButtonElement {
  const scope = within === "" ? container : (container.querySelector(within) as HTMLElement);
  return [...scope.querySelectorAll("button")].find((one) => one.textContent === text) as HTMLButtonElement;
}

describe("the access review screen", () => {
  test("it asks only what the route declares, at a size the route answers", async () => {
    // What breaks if this is deleted: a page size the route refuses on every load.
    const declared = new Set(declaredQueryParameters(REVIEW_OPERATION, "get"));
    const { idp } = await mount("/access_review", (url) =>
      url.pathname === REVIEW_OPERATION ? json(review([])) : null,
    );

    expect(sentQuery(idp, REVIEW_OPERATION).filter((name) => !declared.has(name))).toEqual([]);
    expect(LIST_PAGE_SIZE).toBeLessThanOrEqual(
      declaredParameterSchema(REVIEW_OPERATION, "get", "limit")["maximum"] as number,
    );
    const several = declaredRequestBodySchema(DECISIONS_OPERATION, "post");
    const holdings = (several["properties"] as Record<string, Record<string, unknown>>)["holdings"];
    expect(holdings?.["maxItems"]).toBe(MOST_DECIDED_AT_ONCE);
  });

  test("a row reads as the design's entitlement row, with who, the pack, and the last decision", async () => {
    // What breaks if this is deleted: every control test below is satisfied by a page that lists
    // nothing, and a pack's row can hide the capabilities a removal takes away with it.
    const { container } = await mount("/access_review", (url) =>
      url.pathname === REVIEW_OPERATION
        ? json(
            review([
              row({ row_id: "r-1", last_decision: "keep", last_decided_by: "u_lead", last_decided_at: "2019-04-01T09:00:00Z" }),
              row({
                row_id: "r-2",
                kind: "pack",
                pack: "pricing",
                capabilities: ["read:client.name", "read:invoice.total"],
              }),
            ]),
          )
        : null,
    );

    const table = container.querySelector('[aria-label="Grants to review"]')?.textContent ?? "";
    for (const text of ["Wei Ling Tan", "read:client.name", "department eq web", "u_seed", "u_lead", "Pack pricing", "read:invoice.total", NEVER_DECIDED]) {
      expect(table).toContain(text);
    }
    expect(container.textContent).toContain(SHOWS);
  });

  test("a decision is confirmed with the person, the grant and the API's sentence, and deciding later sends nothing", async () => {
    // What breaks if this is deleted: a press removes a grant with no second step, or the
    // confirmation says what this console believes happens rather than what the system does.
    const { container, idp } = await mount("/access_review", (url) =>
      url.pathname === REVIEW_OPERATION ? json(review([row({ row_id: "r-1" })])) : null,
    );

    fireEvent.click(buttonNamed(container, DECISION_LABELS.remove));
    const panel = container.querySelector(".confirm") as HTMLElement;
    expect(panel.textContent).toContain("Remove read:client.name from Wei Ling Tan?");
    expect(panel.textContent).toContain(REMOVING);
    expect(document.activeElement?.textContent).toBe(CANCEL_LABEL);
    fireEvent.click(buttonNamed(container, CANCEL_LABEL));
    expect(posts(idp)).toEqual([]);

    fireEvent.click(buttonNamed(container, DECISION_LABELS.keep));
    expect((container.querySelector(".confirm") as HTMLElement).textContent).toContain(KEEPING);
    fireEvent.keyDown(container.querySelector(".confirm") as HTMLElement, { key: "Escape" });
    expect(container.querySelector(".confirm")).toBeNull();
    expect(posts(idp)).toEqual([]);
  });

  test("confirming sends the three keys the route declares, says what was decided, and asks for the list again", async () => {
    // What breaks if this is deleted: a body key the route forbids, a success that says nothing,
    // or a row patched locally rather than read back from the database.
    let decided = false;
    const { container, idp } = await mount("/access_review", (url) => {
      if (url.pathname === DECISION_OPERATION) {
        decided = true;
        return json({ kind: "grant", row_id: "r-1", principal_id: "u_1", decision: "remove", decided_at: "2019-05-01T10:00:00Z" });
      }
      if (url.pathname === REVIEW_OPERATION) {
        return json(review(decided ? [] : [row({ row_id: "r-1" })]));
      }
      return null;
    });
    const declared = declaredRequestBodySchema(DECISION_OPERATION, "post");

    fireEvent.click(buttonNamed(container, DECISION_LABELS.remove));
    fireEvent.click(buttonNamed(container, DECISION_LABELS.remove, ".confirm"));

    await waitFor(() => {
      expect(container.textContent).toContain("read:client.name for Wei Ling Tan was removed at");
    });
    await waitFor(() => {
      expect(container.textContent).toContain(NOTHING_TO_REVIEW);
    });
    const [sent] = posts(idp);
    expect(Object.keys(sent?.body as object).sort()).toEqual(Object.keys(declared["properties"] as object).sort());
    expect(sent?.body).toEqual({ kind: "grant", row_id: "r-1", decision: "remove" });
  });

  test("a refused decision shows the API's sentence and the row stays", async () => {
    // What breaks if this is deleted: a refusal reads as a success.
    const { container } = await mount("/access_review", (url) => {
      if (url.pathname === DECISION_OPERATION) {
        return json({ message: "I could not find that.", trace_id: "t-9" }, 404);
      }
      return url.pathname === REVIEW_OPERATION ? json(review([row({ row_id: "r-1" })])) : null;
    });

    fireEvent.click(buttonNamed(container, DECISION_LABELS.keep));
    fireEvent.click(buttonNamed(container, DECISION_LABELS.keep, ".confirm"));

    await waitFor(() => {
      expect(container.textContent).toContain("I could not find that.");
    });
    expect(container.textContent).toContain("Wei Ling Tan");
    expect(container.textContent).not.toMatch(/was kept at/);
  });

  test("the filters offer only values on rows drawn, and each is a request to the route", async () => {
    // What breaks if this is deleted: a department filter naming places nobody drawn is in, or a
    // filter that narrows the rows already drawn instead of asking the route.
    const rows = [
      row({ row_id: "r-web" }),
      row({ row_id: "r-sales", department: "sales", principal_id: "u_s", display_name: "Sales Person", last_decision: "keep", last_decided_by: "u_lead", last_decided_at: "2019-04-01T09:00:00Z" }),
    ];
    const { container, idp } = await mount("/access_review", (url) => {
      if (url.pathname !== REVIEW_OPERATION) {
        return null;
      }
      const filters = url.searchParams.getAll("filter");
      return json(review(rows.filter((one) => filters.every((term) => term === `department:${one.department ?? ""}`))));
    });
    const select = (name: string) =>
      [...container.querySelectorAll("select")].find((one) =>
        one.closest("label")?.firstChild?.textContent?.trim() === name,
      ) as HTMLSelectElement;

    expect([...select("Department").querySelectorAll("option")].map((one) => one.value)).toEqual(["", "sales", "web"]);
    expect([...select("Reviewed").querySelectorAll("option")].map((one) => one.value)).toEqual(["", "keep", "undecided"]);
    fireEvent.change(select("Department"), { target: { value: "sales" } });
    await waitFor(() => {
      expect(container.querySelector('[aria-label="Grants to review"]')?.textContent).not.toContain("Wei Ling Tan");
    });
    fireEvent.change(select("Person"), { target: { value: "u_1" } });
    await waitFor(() => {
      expect(container.textContent).toContain(NO_GRANT_MATCHES);
    });
    const asked = idp.urls.map((url) => new URL(url, CONSOLE_ORIGIN)).filter((url) => url.pathname === REVIEW_OPERATION);
    expect(asked[asked.length - 1]?.searchParams.getAll("filter")).toEqual(["department:sales", "principal_id:u_1"]);
  });

  test("keeping the ticked grants lists each one first, sends their holdings, and says what came of each", async () => {
    // What breaks if this is deleted: a bulk decision with no confirmation, a confirmation that does
    // not say which grants, a body naming rows by id alone so a pack and a grant are confused, or a
    // refused grant reported as decided.
    const rows = [
      row({ row_id: "r-1" }),
      row({ row_id: "r-2", principal_id: "u_s", display_name: "Sales Person", department: "sales" }),
    ];
    const { container, idp } = await mount("/access_review", (url) => {
      if (url.pathname === DECISIONS_OPERATION) {
        return json({
          decision: "keep",
          outcomes: [
            { kind: "grant", row_id: "r-1", decided: true, principal_id: "u_1", decided_at: "2019-04-02T09:00:00Z" },
            { kind: "grant", row_id: "r-2", decided: false, principal_id: null, decided_at: null },
          ],
        });
      }
      return url.pathname === REVIEW_OPERATION ? json(review(rows)) : null;
    });
    const button = (name: string) =>
      [...container.querySelectorAll("button")].find((one) => one.textContent === name) as HTMLButtonElement;

    const boxes = [...container.querySelectorAll('tbody input[type="checkbox"]')] as HTMLInputElement[];
    expect(boxes).toHaveLength(2);
    expect(button("Keep the ticked grants").disabled).toBe(true);
    boxes.forEach((box) => fireEvent.click(box));
    fireEvent.click(button("Keep the ticked grants"));
    const panel = container.querySelector(".confirm") as HTMLElement;
    expect([...panel.querySelectorAll("li")].map((one) => one.textContent)).toEqual([
      expect.stringContaining("Wei Ling Tan"),
      expect.stringContaining("Sales Person"),
    ]);
    fireEvent.click([...panel.querySelectorAll("button")].find((one) => one.textContent === "Keep the ticked grants") as HTMLElement);

    await waitFor(() => {
      expect(container.textContent).toContain("was kept.");
    });
    expect(container.textContent).toContain("Sales Person was not decided.");
    const sent = idp.calls
      .filter((call) => call.init?.method === "POST" && new URL(call.url, CONSOLE_ORIGIN).pathname === DECISIONS_OPERATION)
      .map((call) => JSON.parse(String(call.init?.body)) as unknown);
    expect(sent).toEqual([{ decision: "keep", holdings: [{ kind: "grant", row_id: "r-1" }, { kind: "grant", row_id: "r-2" }] }]);
    const declared = declaredRequestBodySchema(DECISIONS_OPERATION, "post");
    expect(Object.keys(sent[0] as object).sort()).toEqual(Object.keys(declared["properties"] as object).sort());
  });

  test("empty, a full load, unreachable and refused are different sentences, and nothing counts the rows", async () => {
    // What breaks if this is deleted: "nothing to review" is said when the Brain could not be
    // reached, or a number of grants is drawn from rows narrowed to the reviewer.
    const empty = await mount("/access_review", (url) => (url.pathname === REVIEW_OPERATION ? json(review([])) : null));
    expect(empty.container.textContent).toContain(NOTHING_TO_REVIEW);

    const full = await mount("/access_review", (url) =>
      url.pathname === REVIEW_OPERATION ? json(review([row({ row_id: "r-1" })], true)) : null,
    );
    expect(full.container.textContent).toContain(MORE_GRANTS);
    expect(full.container.textContent).not.toMatch(/\b\d+\s+(more|grants|rows)\b/i);

    const unreachable = await mount("/access_review", (url) => {
      if (url.pathname === REVIEW_OPERATION) {
        throw new TypeError("offline");
      }
      return null;
    });
    expect(unreachable.container.textContent).toContain(THE_BRAIN_COULD_NOT_BE_REACHED);
    expect(new Set([NOTHING_TO_REVIEW, NO_GRANT_MATCHES, MORE_GRANTS, SOMETHING_DID_NOT_WORK, THE_BRAIN_COULD_NOT_BE_REACHED]).size).toBe(5);
    expect(Object.keys(readReview({ items: [], total: 3 })).sort()).toEqual(["keeping", "removing", "rows", "shows", "truncated"]);
  });
});
