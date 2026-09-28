/**
 * The Sessions page on the page kit: the list, ending one session, ending several, and the states.
 *
 * Mounted directly on a memory router at its own address, for the reason
 * `tests/audit-page.test.tsx` gives. The failures worth testing look like the page working: a
 * control on a row the API said may not be ended or on the reader's own, an ending sent without the
 * confirmation, a confirmation that paraphrases what happens, a bulk ending that sends a session
 * the reader could not end on its own, an identifier drawn where a name belongs, and a filter
 * offering a value nobody on the page has.
 *
 * **What the controls send is read against the route's own request bodies**, so a key this console
 * invented is a failure here rather than a 422 in front of an administrator.
 *
 * Task ids: M27.7.10, M27.8.6, M27.16.1
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { NOTHING_MATCHES } from "../src/components/ListControls";
import { LIST_PAGE_SIZE } from "../src/components/listing";
import {
  END_LABEL,
  END_SELECTED_LABEL,
  KEEP_ALL_LABEL,
  KEEP_LABEL,
  LEFT_AS_THEY_ARE,
  LOADING_SESSIONS,
  MORE_SESSIONS,
  NO_SESSIONS,
  YOUR_SESSION,
} from "../src/pages/sessions/SessionsPage";
import { MOST_ENDED_AT_ONCE, readSessionsPage, type SessionRow } from "../src/pages/sessionsQuery";
import { THAT_DID_NOT_WORK, THE_BRAIN_COULD_NOT_BE_REACHED } from "../src/ui/FailureNotice";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { declaredParameterSchema, declaredQueryParameters, declaredRequestBodySchema } from "./support/openapi";
import { installRadixStubs } from "./support/radix";

const SESSIONS_OPERATION = "/api/v1/govern/sessions";
const END_OPERATION = "/api/v1/govern/sessions/end";
const END_SEVERAL_OPERATION = "/api/v1/govern/sessions/end-several";
const CONSOLE_ORIGIN = "https://console.test";
const ENDING = "ENDING-SENTENCE-SENTINEL";
const APPEARS = "APPEARS-SENTENCE-SENTINEL";

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/Sessions");
}, 60_000);

function session(overrides: Partial<SessionRow> & { session_id: string }): SessionRow {
  return {
    principal_id: "u_one",
    display_name: "Wei Ling Tan",
    department: "web",
    second_factor: true,
    signed_in_at: "2019-03-04T09:14:00Z",
    lapses_at: "2019-03-04T19:14:00Z",
    yours: false,
    endable: true,
    ...overrides,
  };
}

function page(items: SessionRow[], truncated = false, next_cursor: string | null = null): unknown {
  return { items, next_cursor, truncated, ending: ENDING, appears: APPEARS };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

type Answer = (url: URL, init: RequestInit | undefined) => Response | null;

async function mount(answer: Answer): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      return answer(new URL(url, CONSOLE_ORIGIN), init);
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { Sessions } = await import("../src/pages/Sessions");
  const router = createMemoryRouter([{ path: "/sessions", element: <Sessions /> }], { initialEntries: ["/sessions"] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector("h1") || container.textContent?.includes(LOADING_SESSIONS)) {
      throw new Error("still loading");
    }
  });
  return { container, idp };
}

function posts(idp: FakeIdp): { path: string; body: unknown }[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST" && new URL(call.url, CONSOLE_ORIGIN).pathname.startsWith("/api/"))
    .map((call) => ({
      path: new URL(call.url, CONSOLE_ORIGIN).pathname,
      body: JSON.parse(String(call.init?.body ?? "null")) as unknown,
    }));
}

function asked(idp: FakeIdp): URL[] {
  return idp.urls.map((url) => new URL(url, CONSOLE_ORIGIN)).filter((url) => url.pathname === SESSIONS_OPERATION);
}

async function press(element: HTMLElement): Promise<void> {
  await act(async () => {
    fireEvent.click(element);
  });
}

const THREE = [
  session({ session_id: "kc-a", display_name: "Aaron Lim", principal_id: "u_a" }),
  session({ session_id: "kc-watch", display_name: "Siti Rahman", principal_id: "u_s", endable: false }),
  session({ session_id: "kc-mine", display_name: "Me Myself", principal_id: "u_me", yours: true }),
];

describe("what the sessions page asks for", () => {
  test("the listing sends only what the route declares, and the bulk bound is the route's", async () => {
    // What breaks if this is deleted: a parameter the API ignores, a page size it refuses on every
    // load, or a bulk ending the declaration refuses.
    const declared = new Set(declaredQueryParameters(SESSIONS_OPERATION, "get"));
    const limit = declaredParameterSchema(SESSIONS_OPERATION, "get", "limit");
    const { idp } = await mount((url) => (url.pathname === SESSIONS_OPERATION ? json(page([])) : null));

    const sent = asked(idp).flatMap((url) => [...url.searchParams.keys()]);
    expect(sent.length).toBeGreaterThan(0);
    expect(sent.filter((name) => !declared.has(name))).toEqual([]);
    expect(LIST_PAGE_SIZE).toBeLessThanOrEqual(limit["maximum"] as number);
    const several = declaredRequestBodySchema(END_SEVERAL_OPERATION, "post");
    const ids = (several["properties"] as Record<string, Record<string, unknown>>)["session_ids"];
    expect(ids?.["maxItems"]).toBe(MOST_ENDED_AT_ONCE);
  });
});

describe("what the sessions page shows and does", () => {
  test("a row names the person and never an identifier, and only a session you may end has a control", async () => {
    // What breaks if this is deleted: principal ids back beside every name, every reader offered a
    // button to sign anybody out, or an administrator offered the control that ends their own.
    const { container } = await mount((url) => (url.pathname === SESSIONS_OPERATION ? json(page(THREE)) : null));

    const table = container.querySelector("table")?.textContent ?? "";
    expect(table).toContain("Aaron Lim");
    expect(table).toContain("web");
    expect(table).toContain("Yes");
    expect(table).toContain(YOUR_SESSION);
    for (const id of ["u_a", "u_s", "u_me", "kc-a", "kc-mine"]) {
      expect(container.textContent).not.toContain(id);
    }
    const controls = [...container.querySelectorAll("tbody button")]
      .map((one) => one.getAttribute("aria-label"))
      .filter((one) => one?.startsWith(END_LABEL));
    expect(controls).toEqual([`${END_LABEL}: Aaron Lim`]);
  });

  test("ending one is confirmed in the API's words, keeping it sends nothing, and confirming sends the one declared key", async () => {
    // What breaks if this is deleted: a press that ends a session with no second step, a
    // confirmation in this console's words, a body key the route forbids, or a list that still
    // shows the ended session because it was patched locally instead of asked again.
    let ended = false;
    const { container, idp } = await mount((url) => {
      if (url.pathname === END_OPERATION) {
        ended = true;
        return json({ session_id: "kc-1", principal_id: "u_one", ended_at: "2019-03-04T10:00:00Z" });
      }
      return url.pathname === SESSIONS_OPERATION ? json(page(ended ? [] : [session({ session_id: "kc-1" })])) : null;
    });

    await press(screen.getByRole("button", { name: `${END_LABEL}: Wei Ling Tan` }));
    let dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("Wei Ling Tan");
    expect(dialog.textContent).toContain(ENDING);
    await press(within(dialog).getByRole("button", { name: KEEP_LABEL }));
    expect(posts(idp)).toEqual([]);

    await press(screen.getByRole("button", { name: `${END_LABEL}: Wei Ling Tan` }));
    dialog = await screen.findByRole("alertdialog");
    await press(within(dialog).getByRole("button", { name: END_LABEL }));
    await waitFor(() => {
      expect(container.textContent).toContain("Wei Ling Tan's session was ended at");
    });
    await waitFor(() => {
      expect(container.textContent).toContain(NO_SESSIONS);
    });
    const declared = declaredRequestBodySchema(END_OPERATION, "post");
    expect(posts(idp)).toEqual([{ path: END_OPERATION, body: { session_id: "kc-1" } }]);
    expect(Object.keys(declared["properties"] as object)).toEqual(["session_id"]);
  });

  test("a refused ending says the API's sentence in the confirmation and the session stays listed", async () => {
    // What breaks if this is deleted: a refusal read as a success, or drawn after the dialog closed.
    const { container } = await mount((url) => {
      if (url.pathname === END_OPERATION) {
        return json({ message: "I could not find that.", trace_id: "t-2" }, 404);
      }
      return url.pathname === SESSIONS_OPERATION ? json(page([session({ session_id: "kc-1" })])) : null;
    });

    await press(screen.getByRole("button", { name: `${END_LABEL}: Wei Ling Tan` }));
    const dialog = await screen.findByRole("alertdialog");
    await press(within(dialog).getByRole("button", { name: END_LABEL }));
    await waitFor(() => {
      expect(dialog.textContent).toContain("I could not find that.");
    });
    expect(container.querySelector("table")?.textContent).toContain("Wei Ling Tan");
    expect(container.textContent).not.toMatch(/was ended/);
  });

  test("ending several lists each one first, leaves out the ones it may not end, and says what came of each", async () => {
    // What breaks if this is deleted: a bulk act with no confirmation, one that names no session,
    // one that sends the reader's own session or one the API said may not be ended, or a partial
    // failure reported as a success.
    const rows = [session({ session_id: "kc-b", display_name: "Bea Tan", principal_id: "u_b" }), ...THREE];
    const { container, idp } = await mount((url) => {
      if (url.pathname === END_SEVERAL_OPERATION) {
        return json({
          outcomes: [
            { session_id: "kc-b", ended: true, principal_id: "u_b", ended_at: "2019-03-04T10:00:00Z" },
            { session_id: "kc-a", ended: false, principal_id: null, ended_at: null },
          ],
        });
      }
      return url.pathname === SESSIONS_OPERATION ? json(page(rows)) : null;
    });

    await press(screen.getByRole("checkbox", { name: "Select every row shown" }));
    const bar = screen.getByRole("region", { name: "Bulk actions" });
    await press(within(bar).getByRole("button", { name: END_SELECTED_LABEL }));
    let dialog = await screen.findByRole("alertdialog");
    expect([...dialog.querySelectorAll("li")].map((one) => one.textContent)).toEqual([
      expect.stringContaining("Bea Tan"),
      expect.stringContaining("Aaron Lim"),
    ]);
    expect(dialog.textContent).toContain(LEFT_AS_THEY_ARE);
    expect(dialog.textContent).toContain("Siti Rahman, Me Myself");
    expect(dialog.textContent).toContain(ENDING);
    await press(within(dialog).getByRole("button", { name: KEEP_ALL_LABEL }));
    expect(posts(idp)).toEqual([]);

    await press(within(screen.getByRole("region", { name: "Bulk actions" })).getByRole("button", { name: END_SELECTED_LABEL }));
    dialog = await screen.findByRole("alertdialog");
    await press(within(dialog).getByRole("button", { name: END_SELECTED_LABEL }));
    await waitFor(() => {
      expect(container.textContent).toContain("Bea Tan's session was ended.");
    });
    expect(container.textContent).toContain("Aaron Lim's session was not ended.");
    const declared = declaredRequestBodySchema(END_SEVERAL_OPERATION, "post");
    expect(posts(idp)).toEqual([{ path: END_SEVERAL_OPERATION, body: { session_ids: ["kc-b", "kc-a"] } }]);
    expect(Object.keys(declared["properties"] as object)).toEqual(["session_ids"]);
  });

  test("the filters offer only values on rows drawn, a person by name, and every search, filter and order is a request", async () => {
    // What breaks if this is deleted: a dropdown naming departments nobody on the page is in, a
    // person offered by their id, or a filter that narrows the rows already drawn instead of asking.
    const rows = [
      session({ session_id: "kc-web", department: "web", display_name: "Web Person", principal_id: "u_w" }),
      session({ session_id: "kc-sales", department: "sales", display_name: "Sales Person", principal_id: "u_s" }),
      session({ session_id: "kc-none", department: null, display_name: "No Department", principal_id: "u_n" }),
    ];
    const { container, idp } = await mount((url) => {
      if (url.pathname !== SESSIONS_OPERATION) {
        return null;
      }
      const filtered = url.searchParams.getAll("filter");
      return json(page(filtered.length === 0 ? rows : rows.filter((one) => filtered.includes(`department:${one.department ?? ""}`))));
    });
    const department = screen.getByLabelText("Department") as HTMLSelectElement;
    const person = screen.getByLabelText("Person") as HTMLSelectElement;

    expect([...department.options].map((one) => one.value).sort()).toEqual(["", "sales", "web"]);
    expect([...person.options].map((one) => one.textContent)).toEqual(expect.arrayContaining(["Web Person", "Sales Person"]));
    expect([...person.options].map((one) => one.textContent)).not.toContain("u_w");

    fireEvent.change(department, { target: { value: "sales" } });
    await waitFor(() => {
      const table = container.querySelector("table")?.textContent ?? "";
      expect(table).toContain("Sales Person");
      expect(table).not.toContain("Web Person");
    });
    fireEvent.change(screen.getByLabelText("Sort by"), { target: { value: "display_name" } });
    fireEvent.change(container.querySelector('input[type="search"]') as HTMLInputElement, { target: { value: "sales" } });
    await waitFor(() => {
      const last = asked(idp).at(-1);
      expect(last?.searchParams.getAll("filter")).toEqual(["department:sales"]);
      expect(last?.searchParams.get("sort")).toBe("display_name");
      expect(last?.searchParams.get("q")).toBe("sales");
    });
  });

  test("empty, narrowed to nothing, full, refused and unreachable say different things, and no figure", async () => {
    // What breaks if this is deleted: "nobody is signed in" said when the Brain could not be
    // reached, or a count of what the list left out.
    const empty = await mount((url) => (url.pathname === SESSIONS_OPERATION ? json(page([])) : null));
    expect(empty.container.textContent).toContain(NO_SESSIONS);
    expect(empty.container.textContent).toContain(APPEARS);
    fireEvent.change(empty.container.querySelector('input[type="search"]') as HTMLInputElement, { target: { value: "nobody" } });
    await waitFor(() => {
      expect(empty.container.textContent).toContain(NOTHING_MATCHES);
    });
    expect(empty.container.textContent).not.toContain(NO_SESSIONS);

    const full = await mount((url) => (url.pathname === SESSIONS_OPERATION ? json(page([session({ session_id: "kc-1" })], true)) : null));
    expect(full.container.textContent).toContain(MORE_SESSIONS);
    expect(full.container.textContent).not.toMatch(/\b\d+\s+(more|sessions|people)\b/i);

    const refused = await mount((url) =>
      url.pathname === SESSIONS_OPERATION ? json({ message: "I could not find that.", trace_id: "t" }, 404) : null,
    );
    expect(refused.container.textContent).toContain(THAT_DID_NOT_WORK);
    expect(refused.container.textContent).not.toContain(NO_SESSIONS);

    const unreachable = await mount((url) => {
      if (url.pathname === SESSIONS_OPERATION) {
        throw new TypeError("offline");
      }
      return null;
    });
    expect(unreachable.container.textContent).toContain(THE_BRAIN_COULD_NOT_BE_REACHED);
  });

  test("a body that is not a page is an empty one, a malformed row is dropped, and no total survives", () => {
    // What breaks if this is deleted: an unreadable answer throws inside a render, a row with no
    // name draws an empty cell, a missing `endable` draws a control, or a `total` reaches a renderer.
    expect(readSessionsPage({ unexpected: true }).sessions).toEqual([]);
    const read = readSessionsPage({
      ...(page([session({ session_id: "kc-1" })]) as object),
      items: [{ ...session({ session_id: "kc-1" }), endable: "yes" }, { session_id: "kc-2" }, session({ session_id: "kc-1" })],
      total: 9,
    });
    expect(read.sessions.map((one) => [one.session_id, one.endable])).toEqual([["kc-1", false]]);
    expect(Object.keys(read).sort()).toEqual(["appears", "ending", "sessions", "truncated"]);
  });
});
