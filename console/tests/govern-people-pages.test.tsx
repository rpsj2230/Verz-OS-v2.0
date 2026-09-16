/**
 * Departments and teams, Elevation, Access review and Subscribers: what each asks for, what each
 * shows, the one control and its confirmation, and the four states each says differently.
 *
 * Mounted directly on a memory router at each page's own address, for the reason
 * `tests/sessions-page.test.tsx` gives: the route table is shared, and these pages are wired into it
 * by the commit that adds their navigation rows. The failures worth testing are the ones that look
 * like a screen working: a decision sent without a confirmation, a confirmation that paraphrases
 * what happens, a body key the route forbids, a filter offering a department nobody on the page is
 * in, and a sentence about what the install does not record dropping off a page that then draws an
 * empty list as a fact.
 *
 * Task ids: M27.7.4, M27.7.8, M27.7.9, M27.7.12
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
  DISABLED,
  Departments,
  NOBODY_LISTED,
  NONE_MATCH as NO_DEPARTMENT_MATCHES,
  NO_DEPARTMENTS_HERE,
  READING_DEPARTMENTS,
  SEARCH_LABEL,
  UNPLACED_HEADING,
} from "../src/pages/Departments";
import { Elevation, NOT_A_LANDING, READING_ELEVATION, YOU_HOLD_THE_AUTHORITY } from "../src/pages/Elevation";
import {
  GOVERN_PEOPLE_PAGE_SIZE,
  departmentsApiPath,
  narrowedReview,
  readOrganisation,
  readReview,
  readSubscribers,
  reviewApiPath,
  reviewDepartments,
  searchedOrganisation,
  type DepartmentRow,
  type ReviewRow,
} from "../src/pages/governPeopleQuery";
import { SOMETHING_DID_NOT_WORK } from "../src/pages/Overview";
import {
  NEVER_DELIVERED,
  NO_SUBSCRIBERS,
  READING_SUBSCRIBERS,
  Subscribers,
} from "../src/pages/Subscribers";
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
const SUBSCRIBERS_OPERATION = "/api/v1/govern/subscribers";

const TEAMS = "Who is in each team is not recorded on this install.";
const LEADS = "Nothing on this install records who leads a department.";
const COUNTED = "No headcount is shown.";
const KEEPING = "Keeping a grant records that you reviewed it and it stands.";
const REMOVING = "Removing a grant takes it away from the next request the person makes.";
const SHOWS = "Only grants you could have written are listed.";
const STOPPING = "Switching a subscriber off is not on this screen yet.";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

type Answer = (url: URL, init: RequestInit | undefined) => Response | null;

const PAGES = {
  "/departments": { element: <Departments />, reading: READING_DEPARTMENTS },
  "/elevation": { element: <Elevation />, reading: READING_ELEVATION },
  "/access_review": { element: <AccessReview />, reading: READING_REVIEW },
  "/subscribers": { element: <Subscribers />, reading: READING_SUBSCRIBERS },
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

function organisation(departments: DepartmentRow[], truncated = false): unknown {
  return {
    departments,
    unplaced: [{ principal_id: "u_9", display_name: "Nowhere Person", disabled: false, department: null }],
    truncated,
    teams: TEAMS,
    leads: LEADS,
    counted: COUNTED,
  };
}

const WEB: DepartmentRow = {
  slug: "web",
  name: "Web",
  teams: [{ slug: "design", name: "Design" }],
  members: [
    { principal_id: "u_1", display_name: "Wei Ling Tan", disabled: false },
    { principal_id: "u_2", display_name: "Aaron Lim", disabled: true },
  ],
};
const FINANCE: DepartmentRow = { slug: "finance", name: "Finance", teams: [], members: [] };

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
    expect(GOVERN_PEOPLE_PAGE_SIZE).toBeLessThanOrEqual(limit["maximum"] as number);
    expect(departmentsApiPath()).toBe(`/govern/departments?limit=${String(GOVERN_PEOPLE_PAGE_SIZE)}`);
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
    for (const sentence of [TEAMS, LEADS, COUNTED]) {
      expect(container.textContent).toContain(sentence);
    }
    expect(container.textContent).not.toMatch(/\b\d+\s+(people|members|departments|teams)\b/i);
  });

  test("the search narrows the page it was given and asks the API nothing", async () => {
    // What breaks if this is deleted: a search that sends a query the route does not declare, or
    // one that hides a department whose person matched.
    const { container, idp } = await mount("/departments", (url) =>
      url.pathname === DEPARTMENTS_OPERATION ? json(organisation([FINANCE, WEB])) : null,
    );
    const box = [...container.querySelectorAll("input")].find((one) =>
      one.closest("label")?.textContent?.startsWith(SEARCH_LABEL),
    ) as HTMLInputElement;

    fireEvent.change(box, { target: { value: "aaron" } });
    expect(container.querySelector('[aria-label="People in Web"]')?.textContent).not.toContain("Wei Ling Tan");
    expect(container.textContent).not.toContain("Finance");
    fireEvent.change(box, { target: { value: "zzz" } });
    expect(container.textContent).toContain(NO_DEPARTMENT_MATCHES);
    expect(idp.urls.filter((url) => new URL(url, CONSOLE_ORIGIN).pathname === DEPARTMENTS_OPERATION)).toHaveLength(1);
    expect(searchedOrganisation([WEB], "web")).toEqual([WEB]);
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
    expect(Object.keys(readOrganisation({ departments: [], total: 4 })).sort()).toEqual([
      "counted",
      "departments",
      "leads",
      "teams",
      "truncated",
      "unplaced",
    ]);
  });
});

// ------------------------------------------------------------------ elevation

const LANDING = {
  prompt: "This account holds standing access of its own.",
  holds_nothing_standing: false,
  may_authorise: true,
  reasons: ["install", "incident_response"],
  longest_hours: 4,
  what: "An elevation is a break-glass session.",
  recorded: "Nothing on this install stores an elevation or opens one.",
  authorising: "Authorising an elevation takes the same authority the Access review screen asks for.",
};

describe("the elevation screen", () => {
  test("it shows the reader's standing, the rules, and in the API's words that nothing is recorded", async () => {
    // What breaks if this is deleted: the page draws an empty table of requests, which reads as
    // an install where nobody has elevated rather than one that records no elevation at all.
    const { container } = await mount("/elevation", (url) =>
      url.pathname === ELEVATION_OPERATION ? json(LANDING) : null,
    );

    expect(container.textContent).toContain(LANDING.prompt);
    expect(container.textContent).toContain(LANDING.recorded);
    expect(container.textContent).toContain("incident response");
    expect(container.textContent).toContain("4 hours");
    expect(container.textContent).toContain(YOU_HOLD_THE_AUTHORITY);
    expect(container.querySelector("table")).toBeNull();
    expect(container.querySelector("button")).toBeNull();
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
    expect(GOVERN_PEOPLE_PAGE_SIZE).toBeLessThanOrEqual(
      declaredParameterSchema(REVIEW_OPERATION, "get", "limit")["maximum"] as number,
    );
    expect(reviewApiPath()).toBe(`/govern/access-review?limit=${String(GOVERN_PEOPLE_PAGE_SIZE)}`);
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

  test("the filters offer what is on the page and narrow only the page", async () => {
    // What breaks if this is deleted: a department filter naming places nobody on the page is in,
    // or the never-reviewed filter keeping a row somebody reviewed.
    const rows = [
      row({ row_id: "r-web" }),
      row({ row_id: "r-sales", department: "sales", principal_id: "u_s", display_name: "Sales Person", last_decision: "keep", last_decided_by: "u_lead", last_decided_at: "2019-04-01T09:00:00Z" }),
    ];
    const { container } = await mount("/access_review", (url) =>
      url.pathname === REVIEW_OPERATION ? json(review(rows)) : null,
    );
    const department = [...container.querySelectorAll("select")].find((one) =>
      one.closest("label")?.textContent?.startsWith("Department"),
    ) as HTMLSelectElement;

    expect([...department.querySelectorAll("option")].map((one) => one.value)).toEqual(["", "sales", "web"]);
    fireEvent.change(department, { target: { value: "sales" } });
    expect(container.querySelector('[aria-label="Grants to review"]')?.textContent).not.toContain("Wei Ling Tan");
    const person = [...container.querySelectorAll("select")].find((one) =>
      one.closest("label")?.textContent?.startsWith("Person"),
    ) as HTMLSelectElement;
    fireEvent.change(person, { target: { value: "u_1" } });
    expect(container.textContent).toContain(NO_GRANT_MATCHES);

    const now = new Date("2019-04-02T00:00:00Z");
    expect(narrowedReview(rows, { department: "", person: "", decided: "never" }, now).map((one) => one.row_id)).toEqual(["r-web"]);
    expect(narrowedReview(rows, { department: "", person: "", decided: "stale" }, now).map((one) => one.row_id)).toEqual(["r-web"]);
    expect(
      narrowedReview(rows, { department: "", person: "", decided: "stale" }, new Date("2020-01-01T00:00:00Z")).map((one) => one.row_id),
    ).toEqual(["r-web", "r-sales"]);
    expect(reviewDepartments([])).toEqual([]);
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

// ------------------------------------------------------------------ subscribers

const SUBSCRIBERS = {
  items: [
    {
      subscriber_id: "hook_a",
      endpoint: "https://hooks.example.test/a",
      kinds: ["approval.requested"],
      active: true,
      created_by: "u_admin",
      last_delivered_at: null,
    },
    {
      subscriber_id: "hook_b",
      endpoint: "https://hooks.example.test/b",
      kinds: ["operation.settled"],
      active: false,
      created_by: "u_admin",
      last_delivered_at: "2019-03-04T09:00:00Z",
    },
  ],
  findings: ["nothing takes connector.health_changed"],
  kinds: ["approval.requested", "operation.settled", "connector.health_changed"],
  stopping: STOPPING,
  scope: "Only webhook subscribers are listed.",
  told: "A subscriber is told that something happened.",
};

describe("the subscribers screen", () => {
  test("who is told what, the findings, and how one stops, with no control drawn", async () => {
    // What breaks if this is deleted: the page draws a switch-off button the API has no audited
    // write behind, or the sentence saying why there is none drops off.
    const { container } = await mount("/subscribers", (url) =>
      url.pathname === SUBSCRIBERS_OPERATION ? json(SUBSCRIBERS) : null,
    );

    const table = container.querySelector('[aria-label="Subscribers"]')?.textContent ?? "";
    expect(table).toContain("hook_a");
    expect(table).toContain("https://hooks.example.test/a");
    expect(table).toContain(NEVER_DELIVERED);
    expect(container.textContent).toContain("nothing takes connector.health_changed");
    expect(container.textContent).toContain(STOPPING);
    expect(container.querySelector("button")).toBeNull();
  });

  test("the filters narrow the page by kind and by state", async () => {
    // What breaks if this is deleted: a state filter that keeps a switched-off subscriber under
    // "On", which is the quiet integration read as a live one.
    const { container } = await mount("/subscribers", (url) =>
      url.pathname === SUBSCRIBERS_OPERATION ? json(SUBSCRIBERS) : null,
    );
    const state = [...container.querySelectorAll("select")].find((one) =>
      one.closest("label")?.textContent?.startsWith("State"),
    ) as HTMLSelectElement;

    fireEvent.change(state, { target: { value: "active" } });
    const table = container.querySelector('[aria-label="Subscribers"]')?.textContent ?? "";
    expect(table).toContain("hook_a");
    expect(table).not.toContain("hook_b");
  });

  test("no subscribers is its own sentence and still says how one would stop", async () => {
    // What breaks if this is deleted: a reader who may not manage subscribers, who is sent the
    // empty install's answer, sees a blank card; and a body that is not a page throws.
    const { container } = await mount("/subscribers", (url) =>
      url.pathname === SUBSCRIBERS_OPERATION ? json({ ...SUBSCRIBERS, items: [], findings: [] }) : null,
    );

    expect(container.textContent).toContain(NO_SUBSCRIBERS);
    expect(container.textContent).toContain(STOPPING);
    expect(readSubscribers({ unexpected: true }).rows).toEqual([]);
  });
});
