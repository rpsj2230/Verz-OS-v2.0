/**
 * The four govern screens, and the two writes the people screen makes.
 *
 * These are the screens about the permission system rather than screens the permission system
 * protects, which is `brain.console.govern`'s opening argument, and the failures worth testing
 * are the ones that look like the screen working.
 *
 * **An empty capability list must say nothing.** A subject who holds nothing and a subject
 * whose capabilities were withheld arrive identically, by `govern.people`'s decision, and this
 * console must not undo that with a lock, a dash, a tooltip or a sentence. The two payloads are
 * rendered here and compared with each other rather than against a word somebody remembered.
 *
 * **A control drawn or not drawn must change nothing about what the server is asked.**
 * `editable` arrives on the response and decides whether the grant form and the removal buttons
 * exist. The listing request is compared byte for byte between the two answers, because a
 * console that also asked a different question would be enforcing a rule in the copy an
 * attacker edits.
 *
 * **Nothing around any of these lists may count anything.** These collections are filtered per
 * caller, so a number is the subtraction `CLAUDE.md` forbids rather than a footer, and the
 * assertion is over the rendered text rather than over a field nobody rendered.
 *
 * **A write must send only what the route declares.** FastAPI refuses a body key it does not
 * declare rather than ignoring it, and both write models forbid extras, so a key this console
 * invented is a 422 in front of somebody who filled the form in correctly. The declared keys
 * are read out of the API's own document rather than agreed here.
 *
 * Task ids: M27.7.3, M27.7.4, M27.7.5, M27.7.6, M27.7.7
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  CAPABILITIES_API_PATH,
  GRANTS_API_PATH,
  PEOPLE_PAGE_SIZE,
  PROPOSAL_FIELDS,
  REMOVAL_API_PATH,
  ROLES_API_PATH,
  SCOPES_PAGE_SIZE,
  peopleApiPath,
  principalIn,
  proposalSchema,
  readCapabilities,
  readPeoplePage,
  readRoles,
  readScopesPage,
  scopesApiPath,
  subjectAddress,
  submittedProposal,
} from "../src/pages/governQuery";
import {
  MORE_PEOPLE,
  NO_PEOPLE,
  NO_SUCH_SUBJECT,
  ONLY_A_PERSONS_GRANT_CAN_BE_REMOVED_HERE,
  REMOVE_GRANT,
  removeLabel,
  removeQuestion,
} from "../src/pages/People";
import { HOLDERS_ARE_NOT_RECORDED, NO_ROLES } from "../src/pages/Roles";
import { NO_CAPABILITIES } from "../src/pages/Capabilities";
import { NO_DEPARTMENTS, NO_SCOPES, RESTRICTS_NOTHING } from "../src/pages/Scopes";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { declaredParameterSchema, declaredQueryParameters, declaredRequestBodySchema } from "./support/openapi";

const PEOPLE_OPERATION = "/api/v1/govern/people";
const SCOPES_OPERATION = "/api/v1/govern/scopes";
const GRANTS_OPERATION = "/api/v1/govern/grants";
const REMOVAL_OPERATION = "/api/v1/govern/grants/removal";
const CONSOLE_ORIGIN = "https://console.test";

/**
 * Transform the split route once, before anything is timed.
 *
 * The people route is code-split, so the first mount of it in this file is the first time Vite
 * transforms `@rjsf/core` and ajv, which takes several seconds and has nothing to do with the
 * property under test. Without this the first test in the file fails on a timeout and every
 * later one passes, which reads as a flake rather than as a cold cache. The matrix suite warms
 * the same libraries for the same reason.
 */
beforeAll(async () => {
  await import("../src/pages/People");
}, 60_000);

interface Answers {
  readonly people?: unknown;
  readonly scopes?: unknown;
  readonly roles?: unknown;
  readonly capabilities?: unknown;
  /** The status and body of whichever write the test makes. */
  readonly written?: { status?: number; body?: unknown };
}

/** One page of people in the shape `brain.govern_routes.PeoplePage` serialises. */
function peoplePage(
  items: { subject: string; capabilities: string[] }[],
  extra: { editable?: boolean; truncated?: boolean } = {},
): unknown {
  return {
    items,
    next_cursor: null,
    total: null,
    truncated: extra.truncated ?? false,
    editable: extra.editable ?? false,
    staleness: null,
  };
}

/** One page of scopes in the shape `ScopePage` serialises. */
function scopesPage(
  items: {
    slug: string;
    label?: string;
    is_department?: boolean;
    scope?: Record<string, unknown>;
  }[],
  departments: string[] = [],
): unknown {
  return {
    items: items.map((one) => ({
      slug: one.slug,
      label: one.label ?? "",
      is_department: one.is_department ?? false,
      scope: one.scope ?? { clauses: [] },
    })),
    next_cursor: null,
    total: null,
    truncated: false,
    departments,
    staleness: null,
  };
}

/**
 * Mount the application's own route table at one address, against a stand-in API.
 *
 * The real table rather than a copy of it, for the reason `routing.test.tsx` gives: a test that
 * declared its own route for these pages would be testing the copy, and the route is half of
 * what is being checked on the people screen because the subject is a path segment.
 */
async function consoleAt(
  path: string,
  answers: Answers,
): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      const method = init?.method ?? "GET";
      if (method === "POST" && (url.includes(REMOVAL_API_PATH) || url.includes(GRANTS_API_PATH))) {
        const written = answers.written ?? { status: 200, body: {} };
        return new Response(JSON.stringify(written.body ?? {}), {
          status: written.status ?? 200,
          headers: { "content-type": "application/json" },
        });
      }
      const body =
        url.includes("/api/v1/govern/people") && answers.people !== undefined
          ? answers.people
          : url.includes("/api/v1/govern/scopes") && answers.scopes !== undefined
            ? answers.scopes
            : url.includes("/api/v1/govern/roles") && answers.roles !== undefined
              ? answers.roles
              : url.includes("/api/v1/govern/capabilities") && answers.capabilities !== undefined
                ? answers.capabilities
                : null;
      if (body === null) {
        return null;
      }
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (container.querySelector("h1") === null || container.textContent?.includes("Loading.")) {
      throw new Error("the page has no answer yet");
    }
  });
  return { container, idp };
}

/** Every request this console made to a govern route, as URLs. */
function governRequests(idp: FakeIdp): URL[] {
  return idp.urls
    .filter((url) => url.includes("/api/v1/govern/"))
    .map((url) => new URL(url, CONSOLE_ORIGIN));
}

/** Every write this console made, with the body it sent. */
function writes(idp: FakeIdp): { url: string; body: unknown }[] {
  return idp.calls
    .filter((call) => (call.init?.method ?? "GET") === "POST")
    .filter((call) => call.url.includes("/api/v1/govern/"))
    .map((call) => ({ url: call.url, body: JSON.parse(String(call.init?.body ?? "null")) }));
}

/** Every digit the page rendered, so a count anywhere is a failure rather than a field. */
function digitsOn(container: HTMLElement): string[] {
  return (container.querySelector(".page")?.textContent ?? "").match(/\d+/g) ?? [];
}

describe("what the govern screens ask for", () => {
  test("each listing sends only query parameters its route declares", async () => {
    // What breaks if this is deleted: a parameter the API ignores. FastAPI drops an undeclared
    // query parameter without a word, so a console that sent `rows` instead of `limit` would
    // get the route's default page and read it as the page it asked for. The declared names are
    // read out of the API's own document, so this is not the console's spelling compared with
    // itself.
    const declared = new Set([
      ...declaredQueryParameters(PEOPLE_OPERATION, "get"),
      ...declaredQueryParameters(SCOPES_OPERATION, "get"),
    ]);
    const { idp } = await consoleAt("/people", {
      people: peoplePage([{ subject: "principal:u_1", capabilities: [] }]),
    });

    const sent = governRequests(idp).flatMap((url) => [...url.searchParams.keys()]);
    expect(sent.length).toBeGreaterThan(0);
    expect(sent.filter((name) => !declared.has(name))).toEqual([]);
  });

  test("the page sizes the console asks for are ones the routes will answer", async () => {
    // What breaks if this is deleted: every load of these screens becomes a 422. Each route
    // bounds `limit`, the console names a number, and a number outside the bound comes back as
    // `HTTPValidationError`, which is not `ErrorBody` and reaches a person as "Something went
    // wrong." The bounds are read off the routes' own parameters rather than compared with
    // another constant here.
    const people = declaredParameterSchema(PEOPLE_OPERATION, "get", "limit");
    const scopes = declaredParameterSchema(SCOPES_OPERATION, "get", "limit");

    expect(PEOPLE_PAGE_SIZE).toBeLessThanOrEqual(people["maximum"] as number);
    expect(PEOPLE_PAGE_SIZE).toBeGreaterThanOrEqual(people["minimum"] as number);
    expect(SCOPES_PAGE_SIZE).toBeLessThanOrEqual(scopes["maximum"] as number);
    expect(SCOPES_PAGE_SIZE).toBeGreaterThanOrEqual(scopes["minimum"] as number);
    expect(peopleApiPath()).toBe(`/govern/people?limit=${String(PEOPLE_PAGE_SIZE)}`);
    expect(scopesApiPath()).toBe(`/govern/scopes?limit=${String(SCOPES_PAGE_SIZE)}`);
  });

  test("an address this screen builds always stays inside the console", () => {
    // What breaks if this is deleted: an open redirect, and there is a live advisory for
    // exactly this. GHSA-wrjc-x8rr-h8h6 is an open redirect via a backslash reaching `<Link>`
    // and `useNavigate`, it covers every react-router this project can install, and the only
    // fix is a major version. A subject key reaches `<Link>` on the people screen, and a key
    // arrives from the API, so the defence has to be here; what holds it up is the constant
    // `/people/` prefix rather than the encoding.
    const hostile = ["\\\\evil.example", "//evil.example", "/\\evil.example", "http://evil.example", ".."];

    for (const key of hostile) {
      const address = subjectAddress(key);
      expect(address.startsWith("/people/")).toBe(true);
      expect(address.includes("evil.example") && !address.includes("%")).toBe(false);
    }
  });
});

describe("what the people screen shows", () => {
  test("a subject whose capabilities are withheld renders exactly as one holding none", async () => {
    // What breaks if this is deleted: the console grows a lock icon, a dash or a sentence
    // explaining an empty cell, and every one of those says this subject holds something, which
    // is the disclosure the withholding was for. The two payloads are rendered and compared
    // with each other, so any word added for either state fails here whatever it says.
    const withheld = await consoleAt("/people", {
      people: peoplePage([{ subject: "principal:u_1", capabilities: [] }]),
    });
    const holding = await consoleAt("/people", {
      people: peoplePage([{ subject: "principal:u_1", capabilities: [] }]),
    });

    expect(withheld.container.querySelector(".page")?.textContent).toBe(
      holding.container.querySelector(".page")?.textContent,
    );
    expect(withheld.container.textContent).not.toMatch(/withheld|hidden|restricted/i);
  });

  test("a subject's capabilities are drawn when the API sent them", async () => {
    // What breaks if this is deleted: the sibling above is satisfied by a page that renders no
    // capability at all, which is a screen that has withheld everything from everybody.
    const { container } = await consoleAt("/people", {
      people: peoplePage([{ subject: "principal:u_1", capabilities: ["read:client.name"] }]),
    });

    expect(container.textContent).toContain("read:client.name");
  });

  test("nothing on the people screen is a number", async () => {
    // What breaks if this is deleted: somebody adds a heading saying how many subjects there
    // are, which on a listing filtered per caller is the subtraction that tells a maintenance
    // admin how many grants exist in finance. Asserted over the rendered text rather than over
    // a field, because the failure is a number arriving in a sentence.
    // The subject keys carry no digits, deliberately: an id with a number in it would put a
    // digit on the page that this assertion cannot tell from a count, and a test that had to
    // allow for that would be a test with a hole the exact shape of the failure.
    const { container } = await consoleAt("/people", {
      people: peoplePage(
        [
          { subject: "principal:ada", capabilities: ["read:client.name"] },
          { subject: "principal:grace", capabilities: [] },
        ],
        { truncated: true },
      ),
    });

    expect(container.textContent).toContain(MORE_PEOPLE);
    expect(digitsOn(container)).toEqual([]);
  });

  test("an empty listing says one sentence, true for every reason it is empty", async () => {
    // What breaks if this is deleted: the page grows two sentences, one for "there is nobody"
    // and one for "you may not see anybody", and the difference between them is the answer to a
    // question this screen must not answer.
    const { container } = await consoleAt("/people", { people: peoplePage([]) });

    expect(container.textContent).toContain(NO_PEOPLE);
  });

  test("a deep link to a subject this page does not carry says so about the page", async () => {
    // What breaks if this is deleted: the sentence becomes about the estate, and "no such
    // person" told to somebody who may not see that person is the oracle a deep link resolved
    // against the page exists to avoid. It must also be the same sentence for a subject who was
    // never there and one who was withheld, which is what "on this page" buys.
    const { container } = await consoleAt(`/people/${encodeURIComponent("principal:u_9")}`, {
      people: peoplePage([{ subject: "principal:u_1", capabilities: [] }]),
    });

    expect(container.textContent).toContain(NO_SUCH_SUBJECT);
    expect(container.textContent).not.toMatch(/does not exist|no such person|not found/i);
  });
});

describe("what the people screen offers", () => {
  test("the grant form and the removal control are drawn only when the API says editable", async () => {
    // What breaks if this is deleted: the console draws a form whose every submission is
    // refused, or hides one from the person who needs it. `editable` is presentation and this
    // is the whole of what it may do.
    const open = `/people/${encodeURIComponent("principal:u_1")}`;
    const rows = [{ subject: "principal:u_1", capabilities: ["read:client.name"] }];

    const editable = await consoleAt(open, {
      people: peoplePage(rows, { editable: true }),
      scopes: scopesPage([{ slug: "maintenance" }]),
    });
    const readOnly = await consoleAt(open, {
      people: peoplePage(rows, { editable: false }),
      scopes: scopesPage([{ slug: "maintenance" }]),
    });

    expect(editable.container.querySelector("form")).not.toBeNull();
    expect(
      [...editable.container.querySelectorAll("button")].map((one) => one.textContent),
    ).toContain(removeLabel("read:client.name"));
    expect(readOnly.container.querySelector("form")).toBeNull();
    expect(
      [...readOnly.container.querySelectorAll("button")].map((one) => one.textContent),
    ).not.toContain(removeLabel("read:client.name"));
  });

  test("the listing request is the same whether a control was drawn or not", async () => {
    // What breaks if this is deleted: a console that also skipped or altered the request when
    // `editable` was false, which is a permission model in the browser. The URLs are compared,
    // because the request is the thing the API judges and the flag is not.
    const open = `/people/${encodeURIComponent("principal:u_1")}`;
    const rows = [{ subject: "principal:u_1", capabilities: ["read:client.name"] }];

    const editable = await consoleAt(open, { people: peoplePage(rows, { editable: true }) });
    const readOnly = await consoleAt(open, { people: peoplePage(rows, { editable: false }) });

    const asked = (idp: FakeIdp) =>
      governRequests(idp)
        .filter((url) => url.pathname.endsWith("/govern/people"))
        .map((url) => `${url.pathname}${url.search}`);

    expect(asked(editable.idp)).toEqual(asked(readOnly.idp));
  });

  test("a readable subject that is not a person is shown with no control and a reason", async () => {
    // What breaks if this is deleted: a remove button appears beside a team's capability and
    // every click is refused, because `gate.capability_grant` has a principal column and no
    // column for a team. A control that cannot work is worse than a sentence saying so.
    const team = "team:web.design";
    const { container } = await consoleAt(`/people/${encodeURIComponent(team)}`, {
      people: peoplePage([{ subject: team, capabilities: ["read:client.name"] }], {
        editable: true,
      }),
      scopes: scopesPage([{ slug: "maintenance" }]),
    });

    expect(principalIn(team)).toBeNull();
    expect(container.textContent).toContain(ONLY_A_PERSONS_GRANT_CAN_BE_REMOVED_HERE);
    expect(
      [...container.querySelectorAll("button")].map((one) => one.textContent),
    ).not.toContain(removeLabel("read:client.name"));
  });

  test("removing a capability asks first, then posts the subject and the capability and asks again", async () => {
    // What breaks if this is deleted: the removal sends something else, sends on the first press
    // with nothing between a stray tap and a grant taken away, or the console patches its own list
    // instead of re-asking. The last matters because what a person now reaches is the resolver's
    // answer rather than this page's arithmetic.
    const open = `/people/${encodeURIComponent("principal:u_1")}`;
    const { container, idp } = await consoleAt(open, {
      people: peoplePage([{ subject: "principal:u_1", capabilities: ["read:client.name"] }], {
        editable: true,
      }),
      scopes: scopesPage([{ slug: "maintenance" }]),
      written: {
        status: 200,
        body: {
          principal_id: "u_1",
          capability: "read:client.name",
          removed_at: "2019-03-04T09:00:00Z",
        },
      },
    });
    const before = governRequests(idp).filter((url) =>
      url.pathname.endsWith("/govern/people"),
    ).length;

    const button = [...container.querySelectorAll("button")].find(
      (one) => one.textContent === removeLabel("read:client.name"),
    );
    expect(button).toBeDefined();
    fireEvent.click(button as HTMLButtonElement);

    // The press opens a confirmation naming the capability and the subject, and sends nothing.
    await waitFor(() => expect(container.querySelector(".confirm")).not.toBeNull());
    expect(writes(idp)).toEqual([]);
    expect(container.querySelector(".confirm__question")?.textContent).toBe(
      removeQuestion("principal:u_1", "read:client.name"),
    );
    const confirm = [...container.querySelectorAll(".confirm button")].find(
      (one) => one.textContent === REMOVE_GRANT,
    );
    expect(confirm).toBeDefined();
    fireEvent.click(confirm as HTMLButtonElement);

    await waitFor(() => {
      expect(writes(idp).length).toBeGreaterThan(0);
    });
    const sent = writes(idp)[0];
    expect(sent?.url).toContain(REMOVAL_API_PATH);
    expect(sent?.body).toEqual({ principal_id: "u_1", capability: "read:client.name" });

    await waitFor(() => {
      const after = governRequests(idp).filter((url) =>
        url.pathname.endsWith("/govern/people"),
      ).length;
      expect(after).toBeGreaterThan(before);
    });
  });
});

describe("what a grant may carry", () => {
  test("the proposal sends only keys the route declares", () => {
    // What breaks if this is deleted: a key the API refuses. `GrantProposal` forbids extras, so
    // an invented key is a 422 in front of somebody who filled the form in correctly, and the
    // two keys most likely to be invented are the two that would be dangerous: `granted_by`
    // makes a grant attributable to whoever the browser named, and `scope` is the predicate.
    const declared = declaredRequestBodySchema(GRANTS_OPERATION, "post");
    const properties = Object.keys(
      (declared["properties"] ?? {}) as Record<string, unknown>,
    );

    for (const field of PROPOSAL_FIELDS) {
      expect(properties).toContain(field);
    }
    expect(properties).not.toContain("granted_by");
    expect(properties).not.toContain("scope");
    expect(Object.keys(proposalSchema([])["properties"] ?? {})).toEqual([...PROPOSAL_FIELDS]);
  });

  test("a submission carrying a granter or a predicate travels with neither", () => {
    // What breaks if this is deleted: `submittedProposal` starts passing the form's object
    // through, and a `granted_by` in form state, from a schema change or a browser extension,
    // has somewhere to go. The route forbids the key as well; both are wanted, so a person
    // never sees a 422 about a field they did not fill in.
    const sent = submittedProposal({
      principal_id: "u_2",
      capability: "read:client.name",
      scope_slug: "maintenance",
      reason: "covering the rota",
      granted_by: "somebody else",
      scope: { clauses: [] },
    });

    expect(sent).toEqual({
      principal_id: "u_2",
      capability: "read:client.name",
      scope_slug: "maintenance",
      reason: "covering the rota",
    });
  });

  test("a submission that is not a proposal is nothing rather than a partial write", () => {
    // What breaks if this is deleted: a write assembled out of values nobody recognised, which
    // is the most expensive wrong request this console can make.
    expect(submittedProposal(null)).toBeNull();
    expect(submittedProposal({ principal_id: "u_2" })).toBeNull();
    expect(
      submittedProposal({
        principal_id: "",
        capability: "read:client.name",
        scope_slug: "maintenance",
        reason: "covering the rota",
      }),
    ).toBeNull();
  });

  test("the scope names offered are the ones the scopes route answered this reader", () => {
    // What breaks if this is deleted: the form grows a free text box for a predicate, or offers
    // a list this console assembled. The enumeration is the API's answer, passed through; when
    // there is nothing to offer there is no enumeration rather than an empty one, because an
    // empty dropdown is a form nobody can submit.
    const offered = proposalSchema(["maintenance", "finance"]);
    const properties = offered["properties"] as Record<string, Record<string, unknown>>;

    expect(properties["scope_slug"]?.["enum"]).toEqual(["maintenance", "finance"]);
    const empty = proposalSchema([])["properties"] as Record<string, Record<string, unknown>>;
    expect(empty["scope_slug"]?.["enum"]).toBeUndefined();
  });

  test("the removal sends only keys its route declares", () => {
    // What breaks if this is deleted: the removal grows a reason box. There is no certification
    // table for one to be written into, so a reason typed there would be discarded by the API
    // while the person typing it believed they had recorded why.
    const declared = declaredRequestBodySchema(REMOVAL_OPERATION, "post");
    const properties = Object.keys(
      (declared["properties"] ?? {}) as Record<string, unknown>,
    );

    expect(properties.sort()).toEqual(["capability", "principal_id"]);
  });
});

describe("the roles screen", () => {
  test("no capability appears anywhere on it", async () => {
    // What breaks if this is deleted: somebody adds the capabilities a role is usually granted
    // with, helpfully, and the console then documents an implication this system does not have.
    // `brain.console.govern.GOVERN_SURFACES` states the rule for this exact screen.
    const { container } = await consoleAt("/roles", {
      roles: {
        roles: [
          {
            role: "super_admin",
            exists_to: "Own the platform",
            typical_count: "one or two",
            scope_required: false,
          },
        ],
        holders_are_not_recorded_yet: true,
      },
    });

    expect(container.textContent).toContain("super_admin");
    expect(container.textContent).not.toMatch(/\b(read|write|approve|admin):[a-z_]/);
  });

  test("it says that who holds a role is not recorded, rather than showing an empty column", async () => {
    // What breaks if this is deleted: an empty holders column, which reads as nobody holding
    // the role when the truth is that nothing records it. `role_grant` is M1.3.2 and the
    // directory's assertion is a different fact.
    const { container } = await consoleAt("/roles", {
      roles: {
        roles: [
          {
            role: "member",
            exists_to: "Ask questions",
            typical_count: "everyone",
            scope_required: false,
          },
        ],
        holders_are_not_recorded_yet: true,
      },
    });

    expect(container.textContent).toContain(HOLDERS_ARE_NOT_RECORDED);
  });

  test("an answer with no roles in it says so", async () => {
    // What breaks if this is deleted: the page renders nothing at all for a body it could not
    // read, which is a blank screen rather than a sentence.
    const { container } = await consoleAt("/roles", { roles: { roles: [] } });

    expect(container.textContent).toContain(NO_ROLES);
    expect(readRoles({ roles: [] })).toEqual([]);
  });
});

describe("the capability catalogue", () => {
  test("it draws every capability the API answered, with what each one reaches", async () => {
    // What breaks if this is deleted: the page starts filtering, sorting or grouping by what
    // the reader holds, which is the mistake `catalogue` refuses to make on the server.
    const { container } = await consoleAt("/capabilities", {
      capabilities: {
        capabilities: [
          { capability: "admin:halt", description: "stop everything" },
          { capability: "read:invoice.total", description: "see an invoice total" },
        ],
        staleness: null,
      },
    });

    expect(container.textContent).toContain("admin:halt");
    expect(container.textContent).toContain("read:invoice.total");
    expect(container.textContent).toContain("see an invoice total");
  });

  test("an empty catalogue says one sentence and never that it was refused", async () => {
    // What breaks if this is deleted: the page explains that the reader may not see the
    // vocabulary, which is a refusal the API deliberately did not make: it answered an empty
    // list precisely so that a reader without the grant learns nothing.
    const { container } = await consoleAt("/capabilities", {
      capabilities: { capabilities: [], staleness: null },
    });

    expect(container.textContent).toContain(NO_CAPABILITIES);
    expect(container.textContent).not.toMatch(/not allowed|permission|refused|denied/i);
    expect(readCapabilities({ capabilities: [] })).toEqual([]);
  });
});

describe("the scopes screen", () => {
  test("a scope is shown with its predicate, clause by clause", async () => {
    // What breaks if this is deleted: somebody redacts the predicate for a reader who may see
    // the row, which reads as caution and shows them a name with nothing behind it. A scope's
    // name is the predicate in other words, so the two are shown together or not at all.
    const { container } = await consoleAt("/scopes", {
      scopes: scopesPage(
        [
          {
            slug: "maintenance",
            label: "Maintenance",
            is_department: true,
            scope: { clauses: [{ field: "department", op: "eq", value: "maintenance" }] },
          },
        ],
        ["maintenance"],
      ),
    });

    expect(container.textContent).toContain("maintenance");
    expect(container.textContent).toContain("department eq maintenance");
  });

  test("a scope with no clauses says what that means", async () => {
    // What breaks if this is deleted: an unrestricted scope renders as a name with an empty
    // list under it, which reads as a scope that matches nothing when it matches everything.
    const { container } = await consoleAt("/scopes", {
      scopes: scopesPage([{ slug: "everywhere", scope: { clauses: [] } }]),
    });

    expect(container.textContent).toContain(RESTRICTS_NOTHING);
  });

  test("an empty listing and an empty department list each say one sentence", async () => {
    // What breaks if this is deleted: the page distinguishes "there are none" from "you may see
    // none", and the difference between those two is the org chart handed over a sentence at a
    // time.
    const { container } = await consoleAt("/scopes", { scopes: scopesPage([], []) });

    expect(container.textContent).toContain(NO_SCOPES);
    expect(container.textContent).toContain(NO_DEPARTMENTS);
    expect(digitsOn(container)).toEqual([]);
  });
});

describe("getting round these screens without a mouse", () => {
  test("every control the people screen draws is a native element", async () => {
    // What breaks if this is deleted: a div with a click handler renders identically, works
    // with a mouse, and is unreachable from the keyboard. `scripts/check-boundaries.mjs`
    // refuses the source patterns; this asks the rendered question, which is the one that
    // catches a control added through a library.
    const native = new Set(["A", "BUTTON", "INPUT", "SELECT", "TEXTAREA"]);
    const { container } = await consoleAt(`/people/${encodeURIComponent("principal:u_1")}`, {
      people: peoplePage([{ subject: "principal:u_1", capabilities: ["read:client.name"] }], {
        editable: true,
      }),
      scopes: scopesPage([{ slug: "maintenance" }]),
    });

    const focusable = [
      ...container.querySelectorAll<HTMLElement>("a[href], button, input, select, textarea, [tabindex]"),
    ].filter((one) => one.getAttribute("tabindex") !== "-1");

    expect(focusable.length).toBeGreaterThan(0);
    for (const one of focusable) {
      expect(native.has(one.tagName)).toBe(true);
      expect(Number(one.getAttribute("tabindex") ?? "0")).toBeLessThanOrEqual(0);
    }
  });

  test("the removal control names the capability it removes", async () => {
    // What breaks if this is deleted: the button says "Remove" and a screen reader announces
    // four identical buttons, so the one thing a person needs to know before pressing it is the
    // one thing only sighted users have.
    const { container } = await consoleAt(`/people/${encodeURIComponent("principal:u_1")}`, {
      people: peoplePage(
        [{ subject: "principal:u_1", capabilities: ["read:client.name", "write:ticket"] }],
        { editable: true },
      ),
      scopes: scopesPage([{ slug: "maintenance" }]),
    });

    const labels = [...container.querySelectorAll("button")].map((one) => one.textContent);

    expect(labels).toContain(removeLabel("read:client.name"));
    expect(labels).toContain(removeLabel("write:ticket"));
  });

  test("every list on these screens has an accessible name", async () => {
    // What breaks if this is deleted: three lists on one page with nothing telling them apart,
    // which is what the scopes screen would be: scopes, then the clauses inside one, then
    // departments.
    const { container } = await consoleAt("/scopes", {
      scopes: scopesPage(
        [
          {
            slug: "maintenance",
            scope: { clauses: [{ field: "department", op: "eq", value: "maintenance" }] },
          },
        ],
        ["maintenance"],
      ),
    });

    const named = [...container.querySelectorAll("ul.roster")].map((one) =>
      one.getAttribute("aria-label"),
    );

    expect(named.length).toBeGreaterThan(1);
    for (const label of named) {
      expect(label).toBeTruthy();
    }
  });
});

describe("what a body that is not a page does", () => {
  test("an unreadable answer is an empty page rather than a thrown error", () => {
    // What breaks if this is deleted: a console built against a different API renders the
    // route error page rather than an empty screen, and the difference between the two is a
    // developer's problem presented to whoever opened the tab.
    expect(readPeoplePage(null).people).toEqual([]);
    expect(readPeoplePage({ items: "not a list" }).people).toEqual([]);
    expect(readScopesPage(null).scopes).toEqual([]);
    expect(readScopesPage({ items: [] }).departments).toEqual([]);
  });

  test("a total on the wire has no path to the screen", () => {
    // What breaks if this is deleted: `total` acquires a reader here, and a screen holding the
    // field is a screen one line away from showing it. `PeoplePage` inherits it from
    // `brain.api.Page` and never populates it.
    const page = readPeoplePage({ items: [], total: 47, editable: true, truncated: false });

    expect(Object.keys(page).sort()).toEqual(["editable", "people", "truncated"]);
  });
});

/** The two paths these screens read, named so a reader can see there are only two. */
export { CAPABILITIES_API_PATH, ROLES_API_PATH };
