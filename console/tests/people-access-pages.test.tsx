/**
 * The People and access modules on the shared page kit: People (every person, and one person's page
 * with six views), Departments and teams (a list and one department's page), and Roles and
 * permissions (Roles, Capabilities, Scopes and Packs).
 *
 * **Reachable means through the application's own route table.** Every page test mounts `routes`
 * from `src/App.tsx` on a memory router, signed in through the real session modules and answered by a
 * stand-in API keyed by method and path, so a test passes only if the address resolves and the
 * request is the one the route declares.
 *
 * **What is held, in the owner's words.** Every person is listed, not only grant holders; a person's
 * page answers a hidden person and a missing one alike because it draws only the API's refusal; no
 * figure counts anything hidden; names are drawn, never principal ids; every form says its format
 * before submit and a blank or malformed one sends nothing; every act that ends or replaces something
 * is confirmed and sent only from the confirmation; and every body sent carries only keys the route
 * declares.
 *
 * Task ids: M27.11.1, M27.11.2, M27.11.3, M27.15.18, M27.15.19, M27.15.20, M27.15.22, M27.15.24, M27.16.1
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { UNAVAILABLE_MARK } from "../src/components/kit";
import { CAPABILITY_PATTERN, SHORT_NAME_PATTERN, shortNameProblem } from "../src/pages/access/formParts";
import { phraseFor } from "../src/pages/auditQuery";
import { UNAVAILABLE } from "../src/pages/people/peopleActions";
import { readPeople } from "../src/pages/people/peopleQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { apiDocument, declaredPropertyNames, declaredRequestBodySchema } from "./support/openapi";
import { AGENT_FORMAT } from "../src/pages/people/PersonPreview";
import { installRadixStubs } from "./support/radix";
import { readRepoFile } from "./support/repo";

const CONSOLE_ORIGIN = "https://console.test";
const API = "/api/v1";

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/People");
}, 60_000);

/** An answer: a body, or a body with a status. Keyed `METHOD path` or `path` for a GET. */
type Answer = { readonly status?: number; readonly body: unknown } | ((body: unknown) => { readonly status?: number; readonly body: unknown });

interface Mounted {
  readonly container: HTMLElement;
  readonly idp: FakeIdp;
  readonly router: ReturnType<typeof createMemoryRouter>;
}

async function consoleAt(path: string, answers: Readonly<Record<string, Answer>>): Promise<Mounted> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      const method = (init?.method ?? "GET").toUpperCase();
      const pathname = new URL(url, CONSOLE_ORIGIN).pathname;
      const found = answers[`${method} ${pathname}`] ?? (method === "GET" ? answers[pathname] : undefined);
      if (found === undefined) {
        return null;
      }
      const sent: unknown = typeof init?.body === "string" && init.body !== "" ? JSON.parse(init.body) : null;
      const answer = typeof found === "function" ? found(sent) : found;
      return new Response(JSON.stringify(answer.body), {
        status: answer.status ?? 200,
        headers: { "content-type": "application/json", "x-trace-id": "trace-people" },
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
  await waitFor(
    () => {
      if (!container.querySelector('h1, [data-slot="failure-state"]')) {
        throw new Error("the page has not arrived");
      }
    },
    { timeout: 5000 },
  );
  await waitFor(() => {
    if (container.querySelector('[data-slot="loading-state"]')) {
      throw new Error("the page is still asking");
    }
  });
}

/** Every write sent, as `METHOD path` and its body. */
function writes(idp: FakeIdp): { readonly to: string; readonly body: unknown }[] {
  return idp.calls
    .filter((call) => (call.init?.method ?? "GET") !== "GET" && new URL(call.url, CONSOLE_ORIGIN).pathname.startsWith(API))
    .map((call) => ({
      to: `${String(call.init?.method)} ${new URL(call.url, CONSOLE_ORIGIN).pathname}`,
      body: JSON.parse(String(call.init?.body ?? "null")) as unknown,
    }));
}

/** Every GET the page asked, with its query string. */
function asked(idp: FakeIdp): URL[] {
  return idp.calls
    .filter((call) => (call.init?.method ?? "GET") === "GET")
    .map((call) => new URL(call.url, CONSOLE_ORIGIN))
    .filter((url) => url.pathname.startsWith(API));
}

function press(root: HTMLElement | Document, name: string | RegExp): void {
  const found = within(root instanceof Document ? root.body : root).getByRole("button", { name });
  fireEvent.click(found);
}

async function dialogNamed(name: string | RegExp): Promise<HTMLElement> {
  return screen.findByRole("dialog", { name });
}

async function confirmation(name: string | RegExp): Promise<HTMLElement> {
  return screen.findByRole("alertdialog", { name });
}

function type(field: HTMLElement, value: string): void {
  fireEvent.change(field, { target: { value } });
}

async function submitForm(dialog: HTMLElement): Promise<void> {
  const form = dialog.querySelector("form") ?? document.querySelector(`form#${dialog.querySelector("button[type=submit]")?.getAttribute("form") ?? ""}`);
  if (form === null) {
    throw new Error("the drawer holds no form");
  }
  await act(async () => {
    fireEvent.submit(form);
  });
}

async function openMenu(name: string): Promise<HTMLElement> {
  const trigger = screen.getByRole("button", { name });
  trigger.focus();
  await act(async () => {
    fireEvent.keyDown(trigger, { key: "Enter" });
  });
  return screen.findByRole("menu");
}

async function choose(menu: HTMLElement, item: string): Promise<void> {
  await act(async () => {
    fireEvent.click(within(menu).getByRole("menuitem", { name: item }));
  });
}

function textOf(element: Element | null): string {
  return element?.textContent ?? "";
}

// ------------------------------------------------------------------------------ fixtures

const ADA = {
  principal_id: "p_ada",
  display_name: "Ada Okafor",
  department: "web",
  department_name: "Web",
  employment: "staff",
  standing: "live",
  second_factor: true,
  last_signed_in_at: "2019-03-04T09:00:00Z",
  packs: ["helpdesk"],
};
const BEN = {
  principal_id: "p_ben",
  display_name: "Ben Lim",
  department: "sales",
  department_name: "Sales",
  employment: "contractor",
  standing: "disabled",
  second_factor: null,
  last_signed_in_at: null,
  packs: [],
};

function directory(items: unknown[], extra: Record<string, unknown> = {}): unknown {
  return { items, next_cursor: null, truncated: false, editable: true, may_disable: true, may_add: false, ...extra };
}

const GRANT = {
  kind: "grant",
  row_id: "11111111-1111-4111-8111-000000000001",
  capabilities: ["read:ticket.*"],
  pack: null,
  pack_label: null,
  pack_version: null,
  scope: { clauses: [{ field: "department", op: "eq", value: "web" }] },
  scope_slug: "web",
  scope_label: "Web",
  granted_by: "p_boss",
  granted_by_name: "Grace Teo",
  reason: "Answers tickets",
  granted_at: "2019-03-04T09:00:00Z",
  not_after: "2999-01-01T00:00:00Z",
};
const PACK = {
  kind: "pack",
  row_id: "11111111-1111-4111-8111-000000000002",
  capabilities: ["read:client.name", "read:client.email"],
  pack: "helpdesk",
  pack_label: "Helpdesk",
  pack_version: 2,
  scope: { clauses: [{ field: "department", op: "eq", value: "web" }] },
  scope_slug: null,
  scope_label: null,
  granted_by: "p_boss",
  granted_by_name: null,
  reason: "Joins the helpdesk",
  granted_at: "2019-03-04T09:00:00Z",
  not_after: null,
};
const ELEVATED = { ...GRANT, row_id: "11111111-1111-4111-8111-000000000003", capabilities: ["read:invoice.*"], reason: "elevation 7: incident" };

function detail(extra: Record<string, unknown> = {}): unknown {
  return {
    person: ADA,
    placements: {
      department: { slug: "web", name: "Web" },
      teams: [{ department: "web", slug: "design", name: "Design" }],
      leads: [],
    },
    held: [GRANT, PACK, ELEVATED],
    editable: true,
    may_disable: true,
    may_organise: true,
    disabling: "Their sessions end and nothing is deleted.",
    from_a_pack: "A capability that came with a pack is removed with the whole pack.",
    ...extra,
  };
}

const PERSON_API = `${API}/govern/directory/p_ada`;

// ------------------------------------------------------------------------------ people: the list

describe("the People list", () => {
  test("it lists every person the directory sent, grant or none, by name, in the order sent", async () => {
    // What breaks if this is deleted: the list goes back to grant holders only, and somebody with no
    // grant can never be opened and granted anything, which is the gap this page closes.
    const { container } = await consoleAt("/people", { [`${API}/govern/directory`]: { body: directory([BEN, ADA]) } });
    const links = [...container.querySelectorAll('[data-slot="entity-table"] tbody a')].map((one) => [one.textContent, one.getAttribute("href")]);
    expect(links).toEqual([
      ["Ben Lim", "/people/p_ben"],
      ["Ada Okafor", "/people/p_ada"],
    ]);
    expect(textOf(container)).not.toContain("p_ada");
  });

  test("a count sent beside the people reaches nothing on the page, and a withheld figure is an empty cell", async () => {
    // What breaks if this is deleted: a total drawn beside a list filtered per reader is the number of
    // people they were not shown, and a second factor drawn as "No" where none was sent claims a fact.
    const plain = await consoleAt("/people", { [`${API}/govern/directory`]: { body: directory([ADA, BEN]) } });
    const before = plain.container.querySelector('[data-slot="entity-table"]')?.innerHTML.replace(/«[^»]*»|:r[0-9a-z]+:/g, "ID");
    const counted = await consoleAt("/people", { [`${API}/govern/directory`]: { body: directory([ADA, BEN], { total: 47 }) } });
    const after = counted.container.querySelector('[data-slot="entity-table"]')?.innerHTML.replace(/«[^»]*»|:r[0-9a-z]+:/g, "ID");
    expect(after).toBe(before);
    expect(textOf(counted.container)).not.toContain("47");
    const benRow = [...counted.container.querySelectorAll("tbody tr")].find((row) => textOf(row).includes("Ben Lim"));
    expect(benRow?.querySelector('[data-slot="second-factor-pill"]')).toBeNull();
    expect(textOf(benRow ?? null)).toContain("Disabled");
  });

  test("a reader the API offers adding is given a form that says its format, sends nothing blank, and posts only declared keys", async () => {
    // What breaks if this is deleted: an install with no staff source has no way to put a person in the
    // directory (M27.15.19), or the form sends a blank person, or a key the route refuses.
    const mounted = await consoleAt("/people", {
      [`${API}/govern/directory`]: { body: directory([ADA], { may_add: true, adding: "Adds somebody by hand." }) },
      [`POST ${API}/govern/directory`]: { status: 201, body: { principal_id: "p_new", display_name: "Chen Wei", department: null, created_at: "2019-03-04T09:00:00Z" } },
      [`${API}/govern/directory/p_new`]: { body: detail({ person: { ...ADA, principal_id: "p_new", display_name: "Chen Wei" } }) },
    });
    press(mounted.container, /Add person/);
    const drawer = await dialogNamed("Add a person");
    await submitForm(drawer);
    expect(writes(mounted.idp)).toEqual([]);
    expect(textOf(drawer)).toContain("Give the person's full name");

    type(within(drawer).getByLabelText("Full name"), "Chen Wei");
    await submitForm(drawer);
    await waitFor(() => expect(writes(mounted.idp)).toHaveLength(1));
    const [sent] = writes(mounted.idp);
    expect(sent?.to).toBe(`POST ${API}/govern/directory`);
    const declared = declaredPropertyNames(declaredRequestBodySchema(`${API}/govern/directory`, "post"));
    expect(Object.keys(sent?.body as object).every((key) => declared.includes(key))).toBe(true);
    await waitFor(() => expect(mounted.router.state.location.pathname).toBe("/people/p_new"));
  });

  test("selecting people offers one grant to all of them, asked first with each named, and only the confirmation sends", async () => {
    // What breaks if this is deleted: a bulk grant written without the grantor seeing who it reaches,
    // or one that writes some people and not others (the route is all or nothing and says so).
    const mounted = await consoleAt("/people", {
      [`${API}/govern/directory`]: { body: directory([ADA, BEN]) },
      [`${API}/govern/scopes`]: { body: { items: [{ slug: "web", label: "Web", is_department: true, scope: {} }], next_cursor: null, truncated: false } },
      [`${API}/govern/capabilities`]: { body: { capabilities: [] } },
      [`POST ${API}/govern/grants/several`]: { status: 201, body: { grants: [] } },
    });
    fireEvent.click(screen.getByRole("checkbox", { name: "Select Ada Okafor" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select Ben Lim" }));
    press(mounted.container, "Grant to selected");
    const drawer = await dialogNamed("Grant to the people selected");
    await submitForm(drawer);
    expect(writes(mounted.idp)).toEqual([]);
    expect(textOf(drawer)).toContain("Name the capability to grant.");

    type(within(drawer).getByLabelText("Capability"), "read:ticket.*");
    await waitFor(() => expect(within(drawer).getByRole("option", { name: "Web" })).toBeTruthy());
    type(within(drawer).getByLabelText("Scope"), "web");
    type(within(drawer).getByLabelText("Reason"), "Covers the helpdesk");
    await submitForm(drawer);
    const asking = await confirmation("Grant read:ticket.* over web to each of these people?");
    expect(textOf(asking)).toContain("Ada Okafor");
    expect(textOf(asking)).toContain("Ben Lim");
    expect(writes(mounted.idp)).toEqual([]);
    press(asking, "Write these grants");
    await waitFor(() => expect(writes(mounted.idp)).toHaveLength(1));
    expect(writes(mounted.idp)[0]).toEqual({
      to: `POST ${API}/govern/grants/several`,
      body: { principal_ids: ["p_ada", "p_ben"], capability: "read:ticket.*", scope_slug: "web", reason: "Covers the helpdesk" },
    });
  });
});

// ------------------------------------------------------------------------------ people: one person

describe("one person's page", () => {
  test("it has six views at addresses of their own, an unknown view opens the Overview, and an old address still opens the person", async () => {
    // What breaks if this is deleted: a view that loses its place on reload, a probing address that
    // lands somewhere different from a bare one, and links saved from the old screen going dead.
    const answers = { [PERSON_API]: { body: detail() }, [`${API}/agents`]: { body: { items: [] } }, [`${API}/govern/staff_sources/transfers`]: { body: { transfers: [] } } };
    const { container } = await consoleAt("/people/p_ada/nonsense", answers);
    const views = [...container.querySelectorAll('[data-slot="view-switch"] a')].map((one) => [one.textContent, one.getAttribute("href")]);
    expect(views).toEqual([
      ["Overview", "/people/p_ada"],
      ["Access", "/people/p_ada/access"],
      ["Grants", "/people/p_ada/grants"],
      ["Sign-ins", "/people/p_ada/sessions"],
      ["Placements", "/people/p_ada/placements"],
      ["History", "/people/p_ada/history"],
    ]);
    expect(container.querySelector('[data-slot="view-switch"] [aria-current="page"]')?.textContent).toBe("Overview");
    expect(container.querySelector('[data-slot="detail-header"] h1')?.textContent).toBe("Ada Okafor");

    const old = await consoleAt(`/people/${encodeURIComponent("principal:p_ada")}`, answers);
    expect(old.container.querySelector('[data-slot="detail-header"] h1')?.textContent).toBe("Ada Okafor");
  });

  test("a person the API refuses is its sentence and reference and nothing else, whatever the reason", async () => {
    // What breaks if this is deleted: a page that words a hidden person differently from a missing one,
    // which is the oracle a per-person address must not be.
    const { container } = await consoleAt("/people/p_gone", {
      [`${API}/govern/directory/p_gone`]: { status: 404, body: { message: "I could not find that.", trace_id: "trace-people" } },
    });
    expect(textOf(container)).toContain("I could not find that.");
    expect(container.querySelector('[data-slot="detail-header"]')).toBeNull();
    expect(container.querySelector('[data-slot="view-switch"]')).toBeNull();
  });

  test("the Grants view lists each holding with its scope and lapse, and a pack's capability has no removal of its own", async () => {
    // What breaks if this is deleted: grants drawn without scope or lapse, which is what the old list
    // did, or a Remove beside a capability that only the pack can take away (M27.15.20).
    const { container } = await consoleAt("/people/p_ada/grants", { [PERSON_API]: { body: detail() } });
    const rows = [...container.querySelectorAll("tbody tr")];
    expect(rows).toHaveLength(3);
    expect(textOf(rows[0] ?? null)).toContain("read:ticket.*");
    expect(textOf(rows[0] ?? null)).toContain("Web");
    expect(textOf(rows[1] ?? null)).toContain("Pack: Helpdesk, version 2");
    expect(textOf(rows[2] ?? null)).toContain("Elevation");
    expect(within(rows[1] as HTMLElement).queryByRole("button", { name: /^Remove read:client/ })).toBeNull();
    expect(within(rows[1] as HTMLElement).getByRole("button", { name: "Remove the Helpdesk pack" })).toBeTruthy();
    expect(textOf(container)).toContain("A capability that came with a pack is removed with the whole pack.");
  });

  test("removing a grant and removing a pack are each asked first and send their declared bodies", async () => {
    // What breaks if this is deleted: one press taking a grant away, or a pack removed by a body the
    // route does not take.
    const mounted = await consoleAt("/people/p_ada/grants", {
      [PERSON_API]: { body: detail() },
      [`POST ${API}/govern/grants/removal`]: { body: { principal_id: "p_ada", capability: "read:ticket.*", removed_at: "2019-03-04T09:00:00Z" } },
      [`POST ${API}/govern/access-review/decision`]: { body: { kind: "pack", row_id: PACK.row_id, principal_id: "p_ada", decision: "remove", decided_at: "2019-03-04T09:00:00Z" } },
    });
    press(mounted.container, "Remove read:ticket.*");
    const first = await confirmation("Remove read:ticket.* from Ada Okafor?");
    expect(writes(mounted.idp)).toEqual([]);
    press(first, "Remove the grant");
    await waitFor(() => expect(writes(mounted.idp)).toHaveLength(1));
    expect(writes(mounted.idp)[0]).toEqual({ to: `POST ${API}/govern/grants/removal`, body: { principal_id: "p_ada", capability: "read:ticket.*" } });

    await settled(mounted.container);
    press(mounted.container, "Remove the Helpdesk pack");
    const second = await confirmation("Take the Helpdesk pack away from Ada Okafor?");
    press(second, "Remove the pack");
    await waitFor(() => expect(writes(mounted.idp)).toHaveLength(2));
    expect(writes(mounted.idp)[1]).toEqual({ to: `POST ${API}/govern/access-review/decision`, body: { kind: "pack", row_id: PACK.row_id, decision: "remove" } });
  });

  test("the grant form says each field's format, refuses a blank or malformed capability before sending, and sends declared keys", async () => {
    // What breaks if this is deleted: a grant form that sends a capability the grammar refuses and
    // learns why only from the API's generic sentence, or sends a key the route forbids.
    const mounted = await consoleAt("/people/p_ada/grants", {
      [PERSON_API]: { body: detail() },
      [`${API}/govern/scopes`]: { body: { items: [{ slug: "web", label: "Web", is_department: true, scope: {} }] } },
      [`${API}/govern/capabilities`]: { body: { capabilities: [{ capability: "read:ticket.*", description: "Tickets" }] } },
      [`POST ${API}/govern/grants`]: { status: 201, body: {} },
    });
    press(mounted.container, /Grant a capability/);
    const drawer = await dialogNamed("Grant a capability");
    expect(textOf(drawer)).toContain("A verb (read, write, invoke, approve or admin), a colon");
    await submitForm(drawer);
    expect(writes(mounted.idp)).toEqual([]);
    expect(textOf(drawer)).toContain("Name the capability to grant.");

    type(within(drawer).getByLabelText("Capability"), "Read Client");
    await submitForm(drawer);
    expect(writes(mounted.idp)).toEqual([]);
    expect(textOf(drawer)).toContain("Write it as a verb, a colon and what it reaches");

    type(within(drawer).getByLabelText("Capability"), "read:invoice.total");
    await waitFor(() => expect(within(drawer).getByRole("option", { name: "Web" })).toBeTruthy());
    type(within(drawer).getByLabelText("Scope"), "web");
    type(within(drawer).getByLabelText("Reason"), "Month end");
    await submitForm(drawer);
    await waitFor(() => expect(writes(mounted.idp)).toHaveLength(1));
    const [sent] = writes(mounted.idp);
    expect(sent).toEqual({
      to: `POST ${API}/govern/grants`,
      body: { principal_id: "p_ada", capability: "read:invoice.total", scope_slug: "web", reason: "Month end" },
    });
    const declared = declaredPropertyNames(declaredRequestBodySchema(`${API}/govern/grants`, "post"));
    expect(Object.keys(sent?.body as object).every((key) => declared.includes(key))).toBe(true);
  });

  test("disabling is asked first in the API's words and posts only the person", async () => {
    // What breaks if this is deleted: a leaver disabled by one press, or a body carrying more than the
    // route's one key.
    const mounted = await consoleAt("/people/p_ada", {
      [PERSON_API]: { body: detail() },
      [`${API}/agents`]: { body: { items: [] } },
      [`${API}/govern/staff_sources/transfers`]: { body: { transfers: [] } },
      [`POST ${API}/govern/people/disable`]: { body: { principal_id: "p_ada", disabled: true } },
    });
    press(mounted.container, /Disable sign-in/);
    const asking = await confirmation("Disable Ada Okafor's sign-in?");
    expect(textOf(asking)).toContain("Their sessions end and nothing is deleted.");
    press(asking, "Disable sign-in");
    await waitFor(() => expect(writes(mounted.idp)).toEqual([{ to: `POST ${API}/govern/people/disable`, body: { principal_id: "p_ada" } }]));
  });

  test("the Access view groups holdings by origin, names roles apart from grants, and offers a preview the gate computes", async () => {
    // What breaks if this is deleted: the three questions of Part 4.4 merged into one list, a role drawn
    // beside a capability as though it implied one, or a preview computed in the browser. Since
    // 2026-09-29 the preview is `POST /agents/{agent_id}/preview`, asked for an agent the reader chooses.
    const { container } = await consoleAt("/people/p_ada/access", {
      [PERSON_API]: { body: detail() },
      [`${API}/govern/roles/holders`]: {
        body: {
          items: [
            { id: "g-1", principal_id: "p_ada", display_name: "Ada Okafor", role: "approver", scope: { clauses: [{ field: "department", op: "eq", value: "web" }] }, deputy_of: null, not_after: null },
            { id: "g-2", principal_id: "p_other", display_name: "Somebody", role: "auditor", scope: null, deputy_of: null, not_after: null },
          ],
          editable: false,
        },
      },
    });
    const groups = [...container.querySelectorAll("section[aria-label]")].map((one) => one.getAttribute("aria-label"));
    expect(groups).toEqual(expect.arrayContaining(["Given by a person", "From a pack", "From an approved elevation"]));
    expect(textOf(container)).toContain("Approver");
    expect(textOf(container)).not.toContain("Auditor");
    expect(container.querySelector(`[${UNAVAILABLE_MARK}]`)).toBeNull();
    const preview = container.querySelector('[data-slot="person-preview"]');
    expect(preview?.querySelector("select")).not.toBeNull();
    expect(preview?.textContent).toContain(AGENT_FORMAT);
  });

  test("the Sign-ins view asks the sessions and sign-in routes about this person and ends every session in one confirmed act", async () => {
    // What breaks if this is deleted: another person's sessions drawn here, or a leaver's sessions
    // ended one by one with no single act (M27.15.25).
    const mounted = await consoleAt("/people/p_ada/sessions", {
      [PERSON_API]: { body: detail() },
      [`${API}/govern/sign-ins`]: { body: { items: [{ principal_id: "p_ada", display_name: "Ada Okafor", department: "web", linked_at: "2019-03-04T09:00:00Z", last_administrator: false, yours: false }] } },
      [`${API}/govern/sessions`]: {
        body: {
          items: [
            { session_id: "s-1", principal_id: "p_ada", display_name: "Ada Okafor", department: "web", second_factor: true, signed_in_at: "2019-03-04T09:00:00Z", lapses_at: "2019-03-04T19:00:00Z", yours: false, endable: true },
            { session_id: "s-2", principal_id: "p_ada", display_name: "Ada Okafor", department: "web", second_factor: false, signed_in_at: "2019-03-04T10:00:00Z", lapses_at: "2019-03-04T20:00:00Z", yours: false, endable: true },
          ],
          truncated: false,
        },
      },
      [`POST ${API}/govern/sessions/end-several`]: { body: { outcomes: [] } },
    });
    const filters = asked(mounted.idp)
      .filter((url) => url.pathname === `${API}/govern/sessions` || url.pathname === `${API}/govern/sign-ins`)
      .map((url) => url.searchParams.getAll("filter"));
    expect(filters).toEqual([["principal_id:p_ada"], ["principal_id:p_ada"]]);
    press(mounted.container, "End every session");
    const asking = await confirmation(/End every session/);
    press(asking, "End every session");
    await waitFor(() => expect(writes(mounted.idp)).toEqual([{ to: `POST ${API}/govern/sessions/end-several`, body: { session_ids: ["s-1", "s-2"] } }]));
  });

  test("the History view says each change by what it was, and names people rather than printing ids", async () => {
    // What breaks if this is deleted: every organisation change read as "placed in a team" again, a
    // department created included, and principal ids printed as the actor.
    const { container } = await consoleAt("/people/p_ada/history", {
      [PERSON_API]: { body: detail() },
      [`${API}/audit/history`]: {
        body: {
          subject_kind: "principal",
          subject_id: "p_ada",
          events: [
            { at: "2019-03-04T09:00:00Z", action: "principal_state", actor_id: "p_boss", details: { change: "created" } },
            { at: "2019-03-04T10:00:00Z", action: "organisation", actor_id: "p_boss", details: { change: "joined", team: "web.design" } },
            { at: "2019-03-04T11:00:00Z", action: "grant", actor_id: "p_unknown", details: {} },
          ],
          full: false,
        },
      },
      [`${API}/govern/directory`]: { body: directory([{ ...ADA, principal_id: "p_boss", display_name: "Grace Teo" }]) },
    });
    await waitFor(() => expect(textOf(container)).toContain("Grace Teo added to the directory: Ada Okafor"));
    expect(textOf(container)).toContain("Grace Teo added a team member: Ada Okafor");
    expect(textOf(container)).toContain("another account granted a capability to Ada Okafor");
    expect(textOf(container)).not.toContain("p_boss");
  });
});

// ------------------------------------------------------------------------------ departments

const WEB = {
  slug: "web",
  name: "Web",
  teams: [{ slug: "design", name: "Design", members: [{ principal_id: "p_ada", display_name: "Ada Okafor", disabled: false }] }],
  members: [{ principal_id: "p_ada", display_name: "Ada Okafor", disabled: false }, { principal_id: "p_ben", display_name: "Ben Lim", disabled: false }],
  lead: { principal_id: "p_ada", display_name: "Ada Okafor", disabled: false },
  shapeable: true,
};

function organisation(items: unknown[], extra: Record<string, unknown> = {}): unknown {
  return {
    items,
    next_cursor: null,
    unplaced: [],
    truncated: false,
    may_organise: true,
    may_found: true,
    may_draw_scopes: true,
    counted: "No headcount is shown.",
    retiring_department: "Retiring a department retires its teams and every live scope naming it.",
    retiring_team: "Nobody's access changes.",
    retiring_scope: "Grants over it stay.",
    ...extra,
  };
}

describe("Departments and teams", () => {
  test("the list names each department's lead and teams and draws no headcount", async () => {
    // What breaks if this is deleted: a number of people beside a department, which is how many the
    // reader was not shown.
    const { container } = await consoleAt("/departments", { [`${API}/govern/departments`]: { body: organisation([WEB]) } });
    const row = container.querySelector("tbody tr");
    expect(textOf(row)).toContain("Web");
    expect(textOf(row)).toContain("Ada Okafor");
    expect(textOf(row)).toContain("Design");
    expect(textOf(row)).not.toMatch(/\d/);
  });

  test("a short name says its form before submit, and acceptance-test is told to use an underscore without anything sent", async () => {
    // What breaks if this is deleted: the owner's case, a short name refused only after submit with
    // "not in the form this address expects".
    const mounted = await consoleAt("/departments", {
      [`${API}/govern/departments`]: { body: organisation([WEB]) },
      [`POST ${API}/govern/departments`]: { status: 201, body: { kind: "department", department: null, slug: "acceptance_test", change: "created", at: "2019-03-04T09:00:00Z" } },
    });
    press(mounted.container, /New department/);
    const drawer = await dialogNamed("New department");
    expect(textOf(drawer)).toContain("Lower-case letters and digits, starting with a letter");
    type(within(drawer).getByLabelText("Name"), "Acceptance test");
    type(within(drawer).getByLabelText("Short name"), "acceptance-test");
    await submitForm(drawer);
    expect(writes(mounted.idp)).toEqual([]);
    expect(textOf(drawer)).toContain("Use an underscore between words");

    type(within(drawer).getByLabelText("Short name"), "acceptance_test");
    await submitForm(drawer);
    await waitFor(() =>
      expect(writes(mounted.idp)).toEqual([{ to: `POST ${API}/govern/departments`, body: { slug: "acceptance_test", name: "Acceptance test" } }]),
    );
    await waitFor(() => expect(mounted.router.state.location.pathname).toBe("/departments/acceptance_test"));
  });

  test("one department's page is the list's row for its short name, and a team is renamed through a confirmation", async () => {
    // What breaks if this is deleted: a second route answering a department by key, or a rename sent
    // without the name the page showed, which is how two people overwrite each other.
    const mounted = await consoleAt("/departments/web/teams", {
      [`${API}/govern/departments`]: { body: organisation([WEB]) },
      [`POST ${API}/govern/departments/team/rename`]: { body: { kind: "team", department: "web", slug: "design", change: "renamed", at: "2019-03-04T09:00:00Z" } },
    });
    const filter = asked(mounted.idp).find((url) => url.pathname === `${API}/govern/departments`)?.searchParams.getAll("filter");
    expect(filter).toEqual(["slug:web"]);
    expect(mounted.container.querySelector('[data-slot="detail-header"] h1')?.textContent).toBe("Web");
    const team = [...mounted.container.querySelectorAll("li")].find((one) => one.querySelector("span")?.textContent === "Design") as HTMLElement;
    press(team, "Rename");
    const drawer = await dialogNamed("Rename the team Design");
    type(within(drawer).getByLabelText("New name"), "Product design");
    await submitForm(drawer);
    const asking = await confirmation("Rename the team Design to Product design?");
    expect(writes(mounted.idp)).toEqual([]);
    press(asking, "Rename");
    await waitFor(() =>
      expect(writes(mounted.idp)).toEqual([
        { to: `POST ${API}/govern/departments/team/rename`, body: { department: "web", slug: "design", expected_name: "Design", name: "Product design" } },
      ]),
    );
  });

  test("a department under live grants is refused in the API's one sentence and still drawn", async () => {
    // What breaks if this is deleted: a retirement refusal hidden, or one that names the grants holding
    // it back (M27.15.22).
    const mounted = await consoleAt("/departments/web", {
      [`${API}/govern/departments`]: { body: organisation([WEB]) },
      [`POST ${API}/govern/departments/retirement`]: {
        status: 404,
        body: { message: "Nothing was changed: a department is not retired while a live grant is still written over it.", trace_id: "trace-people" },
      },
    });
    press(mounted.container, "Retire the department Web");
    const asking = await confirmation("Retire the department Web?");
    press(asking, "Retire the department");
    await waitFor(() => expect(textOf(asking)).toContain("a department is not retired while a live grant is still written over it"));
    expect(writes(mounted.idp)).toEqual([{ to: `POST ${API}/govern/departments/retirement`, body: { slug: "web", expected_name: "Web" } }]);
  });
});

// ------------------------------------------------------------------------------ roles and permissions

describe("Roles and permissions", () => {
  test("the Roles tab draws no capability, names holders, and removes a role only from a confirmation", async () => {
    // What breaks if this is deleted: a role drawn beside a capability as if it implied one, holders
    // printed as principal ids, or a role removed by one press.
    const mounted = await consoleAt("/roles", {
      [`${API}/govern/roles`]: { body: { roles: [{ role: "approver", exists_to: "Decides approvals", typical_count: "a few", scope_required: true }] } },
      [`${API}/govern/roles/holders`]: {
        body: { items: [{ id: "g-1", principal_id: "p_ada", display_name: "Ada Okafor", role: "approver", scope: null, deputy_of: null, not_after: null }], editable: true },
      },
      [`${API}/govern/roles/group-rules`]: { body: { rules: [], synced: [], editable: true } },
      [`${API}/govern/roles/misconfigurations`]: { body: { items: [] } },
      [`POST ${API}/govern/roles/removal`]: { body: { id: "g-1", change: "removed", at: "2019-03-04T09:00:00Z" } },
    });
    expect(textOf(mounted.container)).not.toMatch(/[a-z]+:[a-z]/);
    expect(textOf(mounted.container)).toContain("Ada Okafor");
    expect(textOf(mounted.container)).not.toContain("p_ada");
    press(mounted.container, "Remove Approver from Ada Okafor");
    const asking = await confirmation("Remove Approver from Ada Okafor?");
    press(asking, "Remove the role");
    await waitFor(() => expect(writes(mounted.idp)).toEqual([{ to: `POST ${API}/govern/roles/removal`, body: { grant_id: "g-1" } }]));
  });

  test("a scope is renamed on the Scopes tab through a confirmation, sending the label the page showed", async () => {
    // What breaks if this is deleted: M27.11.1's missing act, a scope's name that could not be changed
    // from the console at all.
    const mounted = await consoleAt("/scopes", {
      [`${API}/govern/scopes`]: {
        body: { items: [{ slug: "web_team", label: "Web team", is_department: false, scope: { clauses: [{ field: "department", op: "eq", value: "web" }] } }], next_cursor: null, truncated: false },
      },
      [`${API}/govern/departments`]: { body: organisation([WEB]) },
      [`POST ${API}/govern/departments/scopes/rename`]: { body: { kind: "scope", department: null, slug: "web_team", change: "renamed", at: "2019-03-04T09:00:00Z" } },
    });
    const menu = await openMenu("Actions for Web team");
    await choose(menu, "Rename");
    const drawer = await dialogNamed("Rename the scope Web team");
    type(within(drawer).getByLabelText("New name"), "Web and design");
    await submitForm(drawer);
    const asking = await confirmation("Rename the scope Web team to Web and design?");
    press(asking, "Rename");
    await waitFor(() =>
      expect(writes(mounted.idp)).toEqual([
        { to: `POST ${API}/govern/departments/scopes/rename`, body: { slug: "web_team", expected_label: "Web team", label: "Web and design" } },
      ]),
    );
    const declared = declaredPropertyNames(declaredRequestBodySchema(`${API}/govern/departments/scopes/rename`, "post"));
    expect(declared).toEqual(["expected_label", "label", "slug"]);
  });

  test("a pack is created with each capability judged before sending, versioned through a confirmation, and retired through one", async () => {
    // What breaks if this is deleted: M27.15.24's writes, a version that changes every holder's reach
    // with one press, or a pack sent with a capability the grammar refuses.
    const mounted = await consoleAt("/packs", {
      [`${API}/govern/packs`]: {
        body: { packs: [{ slug: "helpdesk", label: "Helpdesk", capabilities: ["read:ticket.*"], version: 2 }], may_write: true, versioning: "Every holder moves with it.", retiring: "A pack somebody holds is not retired." },
      },
      [`POST ${API}/govern/packs`]: { status: 201, body: { slug: "sales_desk", version: 1, change: "created", at: "2019-03-04T09:00:00Z" } },
      [`POST ${API}/govern/packs/version`]: { body: { slug: "helpdesk", version: 3, change: "versioned", at: "2019-03-04T09:00:00Z" } },
      [`POST ${API}/govern/packs/retirement`]: { body: { slug: "helpdesk", version: 2, change: "retired", at: "2019-03-04T09:00:00Z" } },
    });
    press(mounted.container, /New pack/);
    const drawer = await dialogNamed("New pack");
    type(within(drawer).getByLabelText("Name"), "Sales desk");
    type(within(drawer).getByLabelText("Capabilities"), "read:client.name\nRead everything");
    await submitForm(drawer);
    expect(writes(mounted.idp)).toEqual([]);
    expect(textOf(drawer)).toContain("Read everything is not written as a capability");
    type(within(drawer).getByLabelText("Capabilities"), "read:client.name\nread:client.email");
    await submitForm(drawer);
    await waitFor(() =>
      expect(writes(mounted.idp)[0]).toEqual({
        to: `POST ${API}/govern/packs`,
        body: { slug: "sales_desk", label: "Sales desk", capabilities: ["read:client.name", "read:client.email"] },
      }),
    );

    await settled(mounted.container);
    const menu = await openMenu("Actions for Helpdesk");
    await choose(menu, "New version");
    const versioning = await dialogNamed("New version of Helpdesk");
    type(within(versioning).getByLabelText("Capabilities"), "read:ticket.*\nread:client.name");
    await submitForm(versioning);
    const asking = await confirmation("Make version 3 of Helpdesk?");
    expect(textOf(asking)).toContain("Every holder moves with it.");
    expect(writes(mounted.idp)).toHaveLength(1);
    press(asking, "Make the new version");
    await waitFor(() =>
      expect(writes(mounted.idp)[1]).toEqual({
        to: `POST ${API}/govern/packs/version`,
        body: { slug: "helpdesk", expected_version: 2, label: "Helpdesk", capabilities: ["read:ticket.*", "read:client.name"] },
      }),
    );

    await settled(mounted.container);
    const again = await openMenu("Actions for Helpdesk");
    await choose(again, "Retire");
    const retiring = await confirmation("Retire the pack Helpdesk?");
    press(retiring, "Retire the pack");
    await waitFor(() => expect(writes(mounted.idp)[2]).toEqual({ to: `POST ${API}/govern/packs/retirement`, body: { slug: "helpdesk", expected_version: 2 } }));
  });
});

// ------------------------------------------------------------------------------ every drawer, blank

const SCOPES_ANSWER = { body: { items: [{ slug: "web", label: "Web", is_department: true, scope: {} }], next_cursor: null, truncated: false } };
const PERSON_ANSWERS: Readonly<Record<string, Answer>> = {
  [PERSON_API]: { body: detail() },
  [`${API}/govern/scopes`]: SCOPES_ANSWER,
  [`${API}/govern/capabilities`]: { body: { capabilities: [] } },
  [`${API}/govern/packs`]: { body: { packs: [{ slug: "helpdesk", label: "Helpdesk", capabilities: ["read:ticket.*"], version: 1 }] } },
  [`${API}/govern/departments`]: { body: organisation([WEB]) },
  [`${API}/govern/sign-ins`]: { body: { items: [] } },
  [`${API}/govern/sessions`]: { body: { items: [], truncated: false } },
};
const ROLES_ANSWERS: Readonly<Record<string, Answer>> = {
  [`${API}/govern/roles`]: { body: { roles: [] } },
  [`${API}/govern/roles/holders`]: {
    body: { items: [{ id: "g-1", principal_id: "p_ada", display_name: "Ada Okafor", role: "approver", scope: null, deputy_of: null, not_after: null }], editable: true },
  },
  [`${API}/govern/roles/group-rules`]: { body: { rules: [], synced: [], editable: true } },
  [`${API}/govern/roles/misconfigurations`]: { body: { items: [] } },
  [`${API}/govern/scopes`]: SCOPES_ANSWER,
};

/** Each drawer form: where it is, how it is opened, its title, and a sentence a blank submit says. */
const DRAWERS: readonly {
  readonly at: string;
  readonly answers: Readonly<Record<string, Answer>>;
  readonly opener: string | RegExp;
  readonly title: string;
  readonly says: string;
}[] = [
  { at: "/people/p_ada/grants", answers: PERSON_ANSWERS, opener: /Assign a pack/, title: "Assign a pack", says: "Choose the pack to assign." },
  { at: "/people/p_ada/placements", answers: PERSON_ANSWERS, opener: "Add to a team", title: "Add Ada Okafor to a team", says: "Choose the team to place them in" },
  { at: "/people/p_ada/sessions", answers: PERSON_ANSWERS, opener: "Link an account", title: "Link an account to Ada Okafor", says: "Enter the identity provider account ID." },
  { at: "/departments", answers: { [`${API}/govern/departments`]: { body: organisation([WEB]) } }, opener: /New department/, title: "New department", says: "Give the department a name people will read." },
  { at: "/departments/web/teams", answers: { [`${API}/govern/departments`]: { body: organisation([WEB]) } }, opener: "New team", title: "New team in Web", says: "Give the team a name people will read." },
  { at: "/departments/web/teams", answers: { [`${API}/govern/departments`]: { body: organisation([WEB]) } }, opener: "Add", title: "Add to Design", says: "Choose who to place in the team" },
  { at: "/departments/web", answers: { [`${API}/govern/departments`]: { body: organisation([WEB]) } }, opener: "Rename", title: "Rename the department Web", says: "Type the new name first" },
  {
    at: "/scopes",
    answers: { [`${API}/govern/scopes`]: SCOPES_ANSWER, [`${API}/govern/departments`]: { body: organisation([WEB]) } },
    opener: /New scope/,
    title: "New scope",
    says: "Choose at least one department for the scope to reach.",
  },
  { at: "/roles", answers: ROLES_ANSWERS, opener: /^Appoint$/, title: "Appoint to a role", says: "Choose who to appoint." },
  { at: "/roles", answers: ROLES_ANSWERS, opener: "Appoint a deputy", title: "Appoint a deputy", says: "Give a whole number of days from 1 to 30." },
  { at: "/roles", answers: ROLES_ANSWERS, opener: "Map a group", title: "Map a directory group", says: "Type the group exactly as the identity provider spells it." },
  {
    at: "/packs",
    answers: { [`${API}/govern/packs`]: { body: { packs: [], may_write: true } } },
    opener: /New pack/,
    title: "New pack",
    says: "Give at least one capability, one per line.",
  },
];

describe("every drawer form, submitted blank", () => {
  test.each(DRAWERS.map((one) => [`${one.title} on ${one.at}`, one] as const))("%s sends nothing and says what to fill in", async (_, one) => {
    // What breaks if this is deleted: the reason validated-before-write excuses these files. A drawer
    // renders outside the page's main landmark, so that harness cannot open it and this is its test.
    const mounted = await consoleAt(one.at, one.answers);
    const opener = within(mounted.container).getAllByRole("button", { name: one.opener })[0] as HTMLElement;
    fireEvent.click(opener);
    const drawer = await dialogNamed(one.title);
    for (const field of drawer.querySelectorAll<HTMLInputElement>("input:not([type=checkbox]), textarea, select")) {
      fireEvent.change(field, { target: { value: "" } });
    }
    await submitForm(drawer);
    expect(writes(mounted.idp)).toEqual([]);
    expect(textOf(drawer)).toContain(one.says);
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });
});

// ------------------------------------------------------------------------------ the rules the pages copy

describe("what the pages hold against the API", () => {
  test("the short name and capability rules are the Python ones, and the owner's refused value is told what to change", () => {
    // What breaks if this is deleted: a hint promising a form the API refuses, the drift that made
    // "acceptance-test" fail only after submit.
    const department = readRepoFile("src/brain/core/department.py");
    const entitlement = readRepoFile("src/brain/core/entitlement.py");
    expect(department).toContain(`SLUG_PATTERN = r"${SHORT_NAME_PATTERN.source}"`);
    expect(entitlement).toContain(`CAPABILITY_RE = re.compile(r"${CAPABILITY_PATTERN.source}")`);
    expect(shortNameProblem("acceptance-test")).toContain("underscore");
    expect(shortNameProblem("acceptance_test")).toBeNull();
  });

  test("every act the People pages call coming soon has no route in the API document yet", () => {
    // What breaks if this is deleted: a control drawn inert after its route has landed, telling a
    // person they cannot do what they can.
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    for (const [act, { retiredBy }] of Object.entries(UNAVAILABLE)) {
      expect(paths.filter((path) => retiredBy.test(path)), act).toEqual([]);
    }
    // The preview this table held retired with its route, which the page now calls.
    expect(paths).toContain("/api/v1/agents/{agent_id}/preview");
  });

  test("each write body the new pages send carries only keys its route declares", () => {
    // What breaks if this is deleted: a body key the route forbids, which is a 422 on the install.
    const sent: readonly [string, readonly string[]][] = [
      [`${API}/govern/directory`, ["display_name", "department", "employment", "not_after"]],
      [`${API}/govern/packs`, ["slug", "label", "capabilities"]],
      [`${API}/govern/packs/version`, ["slug", "expected_version", "label", "capabilities"]],
      [`${API}/govern/packs/copy`, ["slug", "new_slug", "label"]],
      [`${API}/govern/packs/retirement`, ["slug", "expected_version"]],
      [`${API}/govern/departments/scopes/rename`, ["slug", "expected_label", "label"]],
      [`${API}/govern/grants/several`, ["principal_ids", "capability", "scope_slug", "reason", "not_after"]],
      [`${API}/govern/access-review/decision`, ["kind", "row_id", "decision"]],
    ];
    for (const [path, keys] of sent) {
      const declared = declaredPropertyNames(declaredRequestBodySchema(path, "post"));
      expect(keys.filter((key) => !declared.includes(key)), path).toEqual([]);
    }
  });

  test("an organisation entry is said by the change it records, and an unknown change falls back to the action", () => {
    // What breaks if this is deleted: the Audit screen's label bug, every organisation change read as
    // "placed in a team or made a lead", a department created included.
    expect(phraseFor("organisation", { change: "created" })).toBe("created");
    expect(phraseFor("organisation", { change: "renamed" })).toBe("renamed");
    expect(phraseFor("organisation", { change: "joined", team: "web.design" })).toBe("added a team member:");
    expect(phraseFor("pack", { change: "versioned" })).toBe("made a new version of the pack");
    expect(phraseFor("organisation", { change: "something new" })).toBe("changed the organisation, about");
    expect(phraseFor("organisation")).toBe("changed the organisation, about");
  });

  test("a directory row without an id or a name is not drawn, and a person is drawn once", () => {
    // What breaks if this is deleted: a row the page cannot link to, or one person listed twice.
    expect(readPeople({ items: [ADA, { display_name: "No id" }, { principal_id: "p_x" }, ADA] }).map((one) => one.principalId)).toEqual(["p_ada"]);
  });
});
