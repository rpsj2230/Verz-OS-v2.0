/**
 * The Sessions screen: the list, the control, the confirmation and the four sentences.
 *
 * Mounted directly on a memory router at its own address, for the reason
 * `tests/audit-page.test.tsx` gives. The failures worth testing are the ones that look like the
 * screen working: a button on a row the API said may not be ended, an ending sent without the
 * confirmation, a confirmation that paraphrases what happens, and a department filter listing a
 * department nobody on the page is in.
 *
 * **What the control sends is read against the route's own request body**, so a key this console
 * invented is a failure here rather than a 422 in front of an administrator.
 *
 * Task ids: M27.7.10, M27.8.6
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  END_LABEL,
  END_SELECTED_LABEL,
  KEEP_ALL_LABEL,
  KEEP_LABEL,
  MORE_SESSIONS,
  NONE_MATCH,
  NO_SESSIONS,
  READING_SESSIONS,
  THE_BRAIN_COULD_NOT_BE_REACHED,
  YOUR_SESSION,
} from "../src/pages/Sessions";
import { LIST_PAGE_SIZE } from "../src/components/listing";
import {
  MOST_ENDED_AT_ONCE,
  readSessionsPage,
  type SessionRow,
} from "../src/pages/sessionsQuery";
import { SOMETHING_DID_NOT_WORK } from "../src/pages/Overview";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import {
  declaredParameterSchema,
  declaredQueryParameters,
  declaredRequestBodySchema,
} from "./support/openapi";

const SESSIONS_OPERATION = "/api/v1/govern/sessions";
const END_OPERATION = "/api/v1/govern/sessions/end";
const END_SEVERAL_OPERATION = "/api/v1/govern/sessions/end-several";
const CONSOLE_ORIGIN = "https://console.test";
const ENDING = "Ending a session refuses every request made with that sign-in from the next one on.";
const APPEARS = "A session appears here from the first request it makes to this system.";

beforeAll(async () => {
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
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
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
  const router = createMemoryRouter([{ path: "/sessions", element: <Sessions /> }], {
    initialEntries: ["/sessions"],
  });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (container.textContent?.includes(READING_SESSIONS)) {
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

function button(container: HTMLElement, name: string): HTMLButtonElement | null {
  return (
    ([...container.querySelectorAll("button")].find(
      (one) => one.textContent === name || one.getAttribute("aria-label")?.startsWith(name),
    ) as HTMLButtonElement | undefined) ?? null
  );
}

describe("what the sessions screen asks for", () => {
  test("the listing sends only what the route declares, at a size it answers", async () => {
    // What breaks if this is deleted: a parameter the API ignores, or a page size it refuses on
    // every load.
    const declared = new Set(declaredQueryParameters(SESSIONS_OPERATION, "get"));
    const limit = declaredParameterSchema(SESSIONS_OPERATION, "get", "limit");
    const { idp } = await mount((url) =>
      url.pathname === SESSIONS_OPERATION ? json(page([])) : null,
    );

    const sent = idp.urls
      .filter((url) => new URL(url, CONSOLE_ORIGIN).pathname === SESSIONS_OPERATION)
      .flatMap((url) => [...new URL(url, CONSOLE_ORIGIN).searchParams.keys()]);
    expect(sent.length).toBeGreaterThan(0);
    expect(sent.filter((name) => !declared.has(name))).toEqual([]);
    expect(LIST_PAGE_SIZE).toBeLessThanOrEqual(limit["maximum"] as number);
    // The bulk bound is the route's, read off its body, so the page never offers a request the
    // declaration refuses.
    const several = declaredRequestBodySchema(END_SEVERAL_OPERATION, "post");
    const ids = (several["properties"] as Record<string, Record<string, unknown>>)["session_ids"];
    expect(ids?.["maxItems"]).toBe(MOST_ENDED_AT_ONCE);
  });
});

describe("what the sessions screen shows and does", () => {
  test("a session reads as who, where, since when and whether a second factor was shown", async () => {
    // What breaks if this is deleted: every refusal below is satisfied by a page that shows
    // nothing. The positive case, with the API's own sentence about when a session appears.
    const { container } = await mount((url) =>
      url.pathname === SESSIONS_OPERATION ? json(page([session({ session_id: "kc-1" })])) : null,
    );

    const table = container.querySelector('[aria-label="Sessions signed in now"]')?.textContent ?? "";
    expect(table).toContain("Wei Ling Tan");
    expect(table).toContain("u_one");
    expect(table).toContain("web");
    expect(table).toContain("Yes");
    expect(container.textContent).toContain(APPEARS);
  });

  test("a control is drawn only where the API said the session may be ended, and never on your own", async () => {
    // What breaks if this is deleted: every reader of the screen is shown a button to sign
    // anybody out, or an administrator is offered the control that ends the session they are on.
    const { container } = await mount((url) =>
      url.pathname === SESSIONS_OPERATION
        ? json(
            page([
              session({ session_id: "kc-endable", display_name: "Aaron Lim", principal_id: "u_a" }),
              session({ session_id: "kc-watched", display_name: "Siti Rahman", principal_id: "u_s", endable: false }),
              session({ session_id: "kc-mine", display_name: "Me Myself", principal_id: "u_me", yours: true }),
            ]),
          )
        : null,
    );

    const labels = [...container.querySelectorAll("tbody button")].map((one) => one.getAttribute("aria-label"));
    expect(labels).toEqual([`${END_LABEL}: Aaron Lim`]);
    const boxes = [...container.querySelectorAll('tbody input[type="checkbox"]')].map((one) => one.getAttribute("aria-label"));
    expect(boxes).toEqual(["Tick to end: Aaron Lim"]);
    expect(container.textContent).toContain(YOUR_SESSION);
  });

  test("ending is confirmed with the person named and the API's sentence, and keeping it sends nothing", async () => {
    // What breaks if this is deleted: a press ends the session with no second step, or the
    // confirmation says what this console thinks happens rather than what the system does.
    const { container, idp } = await mount((url) =>
      url.pathname === SESSIONS_OPERATION ? json(page([session({ session_id: "kc-1" })])) : null,
    );

    fireEvent.click(button(container, END_LABEL) as HTMLButtonElement);
    const panel = container.querySelector(".confirm") as HTMLElement;
    expect(panel.textContent).toContain("Wei Ling Tan");
    expect(panel.textContent).toContain(ENDING);
    expect(document.activeElement?.textContent).toBe(KEEP_LABEL);

    fireEvent.click(button(container, KEEP_LABEL) as HTMLButtonElement);
    expect(container.querySelector(".confirm")).toBeNull();
    expect(posts(idp)).toEqual([]);

    fireEvent.click(button(container, END_LABEL) as HTMLButtonElement);
    fireEvent.keyDown(container.querySelector(".confirm") as HTMLElement, { key: "Escape" });
    expect(container.querySelector(".confirm")).toBeNull();
    expect(posts(idp)).toEqual([]);
  });

  test("confirming sends the one key the route declares, says what ended, and asks for the list again", async () => {
    // What breaks if this is deleted: a body key the route forbids, a success that says nothing,
    // or a list that still shows the session that was ended because it was patched locally.
    let ended = false;
    const { container, idp } = await mount((url) => {
      if (url.pathname === END_OPERATION) {
        ended = true;
        return json({ session_id: "kc-1", principal_id: "u_one", ended_at: "2019-03-04T10:00:00Z" });
      }
      if (url.pathname === SESSIONS_OPERATION) {
        return json(page(ended ? [] : [session({ session_id: "kc-1" })]));
      }
      return null;
    });
    const declared = declaredRequestBodySchema(END_OPERATION, "post");

    fireEvent.click(button(container, END_LABEL) as HTMLButtonElement);
    fireEvent.click(
      [...container.querySelectorAll(".confirm button")].find((one) => one.textContent === END_LABEL) as HTMLElement,
    );

    await waitFor(() => {
      expect(container.textContent).toContain("Wei Ling Tan's session was ended at");
    });
    await waitFor(() => {
      expect(container.textContent).toContain(NO_SESSIONS);
    });
    const [sent] = posts(idp);
    expect(Object.keys(sent?.body as object)).toEqual(Object.keys(declared["properties"] as object));
    expect(sent?.body).toEqual({ session_id: "kc-1" });
  });

  test("a refused ending shows the API's sentence and the session stays listed", async () => {
    // What breaks if this is deleted: a refusal reads as a success, or is explained in words that
    // tell the reader something about the session they were refused.
    const { container } = await mount((url) => {
      if (url.pathname === END_OPERATION) {
        return json({ message: "I could not find that.", trace_id: "t-2" }, 404);
      }
      return url.pathname === SESSIONS_OPERATION ? json(page([session({ session_id: "kc-1" })])) : null;
    });

    fireEvent.click(button(container, END_LABEL) as HTMLButtonElement);
    fireEvent.click(
      [...container.querySelectorAll(".confirm button")].find((one) => one.textContent === END_LABEL) as HTMLElement,
    );

    await waitFor(() => {
      expect(container.textContent).toContain("I could not find that.");
    });
    expect(container.textContent).toContain(SOMETHING_DID_NOT_WORK);
    expect(container.textContent).toContain("Wei Ling Tan");
    expect(container.textContent).not.toMatch(/was ended at/);
  });

  test("the filters offer only values on rows drawn, and every search, filter and order is a request", async () => {
    // What breaks if this is deleted: a department dropdown listing places nobody on the page is
    // in, or a filter that narrows the rows already drawn instead of asking the route, which reads
    // as a search of every session and is one of what arrived.
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
    const select = (name: string) =>
      [...container.querySelectorAll("select")].find((one) =>
        one.closest("label")?.textContent?.startsWith(name),
      ) as HTMLSelectElement;

    expect([...select("Department").querySelectorAll("option")].map((one) => one.value)).toEqual(["", "sales", "web"]);
    fireEvent.change(select("Department"), { target: { value: "sales" } });
    await waitFor(() => {
      const table = container.querySelector('[aria-label="Sessions signed in now"]')?.textContent ?? "";
      expect(table).toContain("Sales Person");
      expect(table).not.toContain("Web Person");
    });
    // The value that is no longer on a row stays offered: it was shown.
    expect([...select("Department").querySelectorAll("option")].map((one) => one.value)).toEqual(["", "sales", "web"]);
    fireEvent.change(select("Sort by"), { target: { value: "display_name" } });
    fireEvent.change(container.querySelector('input[type="search"]') as HTMLInputElement, { target: { value: "sales" } });

    await waitFor(() => {
      const asked = idp.urls
        .map((url) => new URL(url, CONSOLE_ORIGIN))
        .filter((url) => url.pathname === SESSIONS_OPERATION);
      const last = asked[asked.length - 1];
      expect(last?.searchParams.getAll("filter")).toEqual(["department:sales"]);
      expect(last?.searchParams.get("sort")).toBe("display_name");
      expect(last?.searchParams.get("q")).toBe("sales");
    });
  });

  test("show more asks for the page after the cursor and adds its rows under the first", async () => {
    // What breaks if this is deleted: a second page that replaces the first, so a session ticked
    // above disappears from view, or a cursor that is never sent back.
    const { container, idp } = await mount((url) => {
      if (url.pathname !== SESSIONS_OPERATION) {
        return null;
      }
      return url.searchParams.get("cursor") === "c-2"
        ? json(page([session({ session_id: "kc-2", display_name: "Second Page", principal_id: "u_2" })]))
        : json(page([session({ session_id: "kc-1", display_name: "First Page" })], false, "c-2"));
    });

    fireEvent.click(button(container, "Show more") as HTMLButtonElement);
    await waitFor(() => {
      expect(container.textContent).toContain("Second Page");
    });
    expect(container.textContent).toContain("First Page");
    expect(button(container, "Show more")).toBeNull();
    expect(idp.urls.some((url) => new URL(url, CONSOLE_ORIGIN).searchParams.get("cursor") === "c-2")).toBe(true);
  });

  test("ending the ticked sessions lists each one first, sends only their ids, and says what came of each", async () => {
    // What breaks if this is deleted: a bulk act with no confirmation, a confirmation that does not
    // say which sessions, a box on a session the API said may not be ended or on your own, or a
    // partial failure reported as a success.
    let asked: unknown = null;
    const rows = [
      session({ session_id: "kc-a", display_name: "Aaron Lim", principal_id: "u_a" }),
      session({ session_id: "kc-b", display_name: "Bea Tan", principal_id: "u_b" }),
      session({ session_id: "kc-watch", display_name: "Siti Rahman", principal_id: "u_s", endable: false }),
      session({ session_id: "kc-mine", display_name: "Me Myself", principal_id: "u_me", yours: true }),
    ];
    const { container, idp } = await mount((url) => {
      if (url.pathname === END_SEVERAL_OPERATION) {
        return json({
          outcomes: [
            { session_id: "kc-a", ended: true, principal_id: "u_a", ended_at: "2019-03-04T10:00:00Z" },
            { session_id: "kc-b", ended: false, principal_id: null, ended_at: null },
          ],
        });
      }
      return url.pathname === SESSIONS_OPERATION ? json(page(rows)) : null;
    });
    idp.calls.length = 0;

    const boxes = [...container.querySelectorAll('tbody input[type="checkbox"]')] as HTMLInputElement[];
    expect(boxes.map((one) => one.getAttribute("aria-label"))).toEqual(["Tick to end: Aaron Lim", "Tick to end: Bea Tan"]);
    expect((button(container, END_SELECTED_LABEL) as HTMLButtonElement).disabled).toBe(true);
    for (const box of boxes) {
      fireEvent.click(box);
    }
    fireEvent.click(button(container, END_SELECTED_LABEL) as HTMLButtonElement);
    const panel = container.querySelector(".confirm") as HTMLElement;
    expect([...panel.querySelectorAll("li")].map((one) => one.textContent)).toEqual([
      expect.stringContaining("Aaron Lim"),
      expect.stringContaining("Bea Tan"),
    ]);
    expect(panel.textContent).toContain(ENDING);
    fireEvent.click(button(container, KEEP_ALL_LABEL) as HTMLButtonElement);
    expect(posts(idp)).toEqual([]);

    fireEvent.click(button(container, END_SELECTED_LABEL) as HTMLButtonElement);
    fireEvent.click(
      [...container.querySelectorAll(".confirm button")].find((one) => one.textContent === END_SELECTED_LABEL) as HTMLElement,
    );
    await waitFor(() => {
      expect(container.textContent).toContain("Aaron Lim's session was ended.");
    });
    expect(container.textContent).toContain("Bea Tan's session was not ended.");
    const [sent] = posts(idp);
    expect(sent?.url.pathname).toBe(END_SEVERAL_OPERATION);
    asked = sent?.body;
    expect(asked).toEqual({ session_ids: ["kc-a", "kc-b"] });
    const declared = declaredRequestBodySchema(END_SEVERAL_OPERATION, "post");
    expect(Object.keys(asked as object)).toEqual(Object.keys(declared["properties"] as object));
  });

  test("an empty list, a filter matching nothing, a full load, unreachable and refused are different sentences", async () => {
    // What breaks if this is deleted: the states `docs/admin-console.md` requires to be different
    // read alike, and "nobody is signed in" is said when the Brain could not be reached.
    const empty = await mount((url) => (url.pathname === SESSIONS_OPERATION ? json(page([])) : null));
    expect(empty.container.textContent).toContain(NO_SESSIONS);
    fireEvent.change(empty.container.querySelector('input[type="search"]') as HTMLInputElement, {
      target: { value: "nobody" },
    });
    await waitFor(() => {
      expect(empty.container.textContent).toContain(NONE_MATCH);
    });
    expect(empty.container.textContent).not.toContain(NO_SESSIONS);

    const full = await mount((url) =>
      url.pathname === SESSIONS_OPERATION ? json(page([session({ session_id: "kc-1" })], true)) : null,
    );
    expect(full.container.textContent).toContain(MORE_SESSIONS);
    expect(full.container.textContent).not.toMatch(/\b\d+\s+(more|sessions|people)\b/i);

    const refused = await mount((url) =>
      url.pathname === SESSIONS_OPERATION ? json({ message: "I could not find that.", trace_id: "t" }, 404) : null,
    );
    expect(refused.container.textContent).toContain(SOMETHING_DID_NOT_WORK);

    const unreachable = await mount((url) => {
      if (url.pathname === SESSIONS_OPERATION) {
        throw new TypeError("offline");
      }
      return null;
    });
    expect(unreachable.container.textContent).toContain(THE_BRAIN_COULD_NOT_BE_REACHED);

    expect(new Set([NO_SESSIONS, NONE_MATCH, MORE_SESSIONS, SOMETHING_DID_NOT_WORK, THE_BRAIN_COULD_NOT_BE_REACHED]).size).toBe(5);
  });

  test("a body that is not a page is an empty one with no total on it", () => {
    // What breaks if this is deleted: an unreadable answer throws inside a render, or a `total`
    // has a path to a renderer.
    expect(readSessionsPage({ unexpected: true }).sessions).toEqual([]);
    expect(Object.keys(readSessionsPage({ ...(page([]) as object), total: 9 })).sort()).toEqual([
      "appears",
      "ending",
      "sessions",
      "truncated",
    ]);
  });
});
