/**
 * The Audit screen: what it asks for, what its filters may offer, and the four sentences.
 *
 * The page is mounted directly on a memory router at its own address, because the route table in
 * `src/App.tsx` is being restructured by another change and this screen's wiring into it is
 * handed over separately. What is under test is the page and its query module; the address it
 * reads its filters from is a real router's.
 *
 * **What a filter offers is asserted over the rendered options**, because the failure is a
 * dropdown listing somebody the reader was never shown, and that is a property of the DOM rather
 * than of a function this file agrees with itself about.
 *
 * **Every parameter the page sends is one the route declares, and every action has a phrase**,
 * both read out of the API's own document rather than out of a constant here.
 *
 * Task ids: M27.7.13
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  ACTION_PHRASES,
  AUDIT_PAGE_SIZE,
  auditApiPath,
  DEFAULT_FILTERS,
  filtersFrom,
  historyAddress,
  offeredActors,
  periodSince,
  readLedgerPage,
  subjectFrom,
} from "../src/pages/auditQuery";
import {
  HISTORY_FILLED_A_PAGE,
  NO_ENTRIES,
  NO_PERMISSION_CHANGES,
  READING_THE_LEDGER,
  THE_BRAIN_COULD_NOT_BE_REACHED,
  WITHHELD_ENTRIES_ARE_NOT_LISTED,
} from "../src/pages/Audit";
import { SOMETHING_DID_NOT_WORK } from "../src/pages/Overview";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { apiDocument, declaredParameterSchema, declaredQueryParameters } from "./support/openapi";

const AUDIT_OPERATION = "/api/v1/audit";
const HISTORY_OPERATION = "/api/v1/audit/history";
const CONSOLE_ORIGIN = "https://console.test";

beforeAll(async () => {
  await import("../src/pages/Audit");
}, 60_000);

interface Row {
  at?: string;
  action: string;
  actor_id: string;
  subject_kind: string;
  subject_id: string;
  details?: Record<string, string>;
}

function ledgerPage(rows: Row[], extra: { next?: string | null; actors?: string[] } = {}): unknown {
  return {
    items: rows.map((one) => ({
      at: one.at ?? "2019-03-04T09:00:00Z",
      details: one.details ?? {},
      ...one,
    })),
    next_cursor: extra.next ?? null,
    order: "newest",
    actions: Object.keys(ACTION_PHRASES),
    subject_kinds: ["agent", "principal"],
    actors: extra.actors ?? [...new Set(rows.map((one) => one.actor_id))],
  };
}

type Answer = (url: URL, init: RequestInit | undefined) => Response | null;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

async function mount(
  path: string,
  answer: Answer,
): Promise<{ container: HTMLElement; idp: FakeIdp; router: ReturnType<typeof createMemoryRouter> }> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      return answer(new URL(url, CONSOLE_ORIGIN), init);
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { Audit } = await import("../src/pages/Audit");
  const router = createMemoryRouter([{ path: "/audit", element: <Audit /> }], {
    initialEntries: [path],
  });
  const { container } = render(<RouterProvider router={router} />);
  return { container, idp, router };
}

async function settled(container: HTMLElement): Promise<void> {
  await waitFor(() => {
    if (container.textContent?.includes(READING_THE_LEDGER)) {
      throw new Error("still reading");
    }
  });
}

function asked(idp: FakeIdp, operation: string): URL[] {
  return idp.urls
    .filter((url) => new URL(url, CONSOLE_ORIGIN).pathname === operation)
    .map((url) => new URL(url, CONSOLE_ORIGIN));
}

const ROWS: Row[] = [
  {
    action: "grant",
    actor_id: "u_admin",
    subject_kind: "principal",
    subject_id: "u_wide",
    details: { capability: "read:client.name" },
  },
  { action: "leash_change", actor_id: "u_steward", subject_kind: "agent", subject_id: "helper" },
];

describe("what the audit screen asks for", () => {
  test("every parameter a page sends is one the route declares", async () => {
    // What breaks if this is deleted: a filter the API ignores. FastAPI drops an undeclared query
    // parameter without a word, so a console sending `kind` rather than `subject_kind` would be
    // shown the whole ledger under a heading that says it was narrowed.
    const declared = new Set(declaredQueryParameters(AUDIT_OPERATION, "get"));
    const { container, idp } = await mount(
      "/audit?action=grant&kind=principal&actor=u_admin&period=day&order=oldest",
      (url) => (url.pathname === AUDIT_OPERATION ? json(ledgerPage(ROWS, { next: "c1" })) : null),
    );
    await settled(container);
    fireEvent.click(container.querySelector("button.button") as HTMLElement);
    await waitFor(() => {
      expect(asked(idp, AUDIT_OPERATION)).toHaveLength(2);
    });

    const sent = asked(idp, AUDIT_OPERATION).flatMap((url) => [...url.searchParams.keys()]);
    expect(sent.filter((name) => !declared.has(name))).toEqual([]);
    const [first] = asked(idp, AUDIT_OPERATION);
    expect(first?.searchParams.get("subject_kind")).toBe("principal");
    expect(first?.searchParams.get("action")).toBe("grant");
    expect(first?.searchParams.get("actor")).toBe("u_admin");
    expect(first?.searchParams.get("order")).toBe("oldest");
    expect(asked(idp, AUDIT_OPERATION)[1]?.searchParams.get("cursor")).toBe("c1");
  });

  test("the page size is one the route answers and a period is sent as an instant with its offset", () => {
    // What breaks if this is deleted: every load is a 422, which a person reads as "That did not
    // work"; or `since` goes without an offset and the route refuses the naive instant.
    const limit = declaredParameterSchema(AUDIT_OPERATION, "get", "limit");
    const now = new Date("2019-03-04T09:00:00Z");
    const path = auditApiPath({ ...DEFAULT_FILTERS, period: "day" }, now, null);
    const since = new URL(path, CONSOLE_ORIGIN).searchParams.get("since") ?? "";

    expect(AUDIT_PAGE_SIZE).toBeLessThanOrEqual(limit["maximum"] as number);
    expect(AUDIT_PAGE_SIZE).toBeGreaterThanOrEqual(limit["minimum"] as number);
    expect(since).toBe("2019-03-03T09:00:00.000Z");
    expect(periodSince("all", now)).toBeNull();
    expect(new URL(auditApiPath(DEFAULT_FILTERS, now, null), CONSOLE_ORIGIN).searchParams.has("actor")).toBe(false);
  });

  test("every action the API can record reads as a phrase and never as its code", () => {
    // What breaks if this is deleted: a thirteenth action arrives on a screen written in sentences
    // as a bare code. The vocabulary is read from the API's own document.
    const schemas = (apiDocument()["components"] as Record<string, unknown>)["schemas"] as Record<
      string,
      Record<string, unknown>
    >;
    const actions = schemas["AuditAction"]?.["enum"] as string[];

    expect(actions.length).toBeGreaterThan(0);
    expect(Object.keys(ACTION_PHRASES).sort()).toEqual([...actions].sort());
  });

  test("a subject's history asks for exactly that subject, and the address keeps the filters", async () => {
    // What breaks if this is deleted: the history asks for the wrong subject, or opening one
    // throws away the filters the reader chose.
    const { container, idp } = await mount(
      "/audit?action=grant&subject=principal:u_wide",
      (url) => {
        if (url.pathname === HISTORY_OPERATION) {
          return json({ subject_kind: "principal", subject_id: "u_wide", events: [], full: false });
        }
        return url.pathname === AUDIT_OPERATION ? json(ledgerPage(ROWS)) : null;
      },
    );
    await settled(container);
    await waitFor(() => {
      expect(container.textContent).toContain(NO_PERMISSION_CHANGES);
    });

    const [history] = asked(idp, HISTORY_OPERATION);
    expect(history?.searchParams.get("subject_kind")).toBe("principal");
    expect(history?.searchParams.get("subject_id")).toBe("u_wide");
    const address = historyAddress(new URLSearchParams("action=grant"), "principal", "u_wide");
    expect(address.startsWith("/audit?")).toBe(true);
    expect(subjectFrom(new URL(address, CONSOLE_ORIGIN).searchParams)).toEqual({
      kind: "principal",
      id: "u_wide",
    });
    expect(filtersFrom(new URL(address, CONSOLE_ORIGIN).searchParams).action).toBe("grant");
  });
});

describe("what the audit screen shows", () => {
  test("an entry reads as who did what to what, with its details, and says once that nothing withheld is counted", async () => {
    // What breaks if this is deleted: every refusal below is satisfied by a page that renders
    // nothing. This is the positive case.
    const { container } = await mount("/audit", (url) =>
      url.pathname === AUDIT_OPERATION ? json(ledgerPage(ROWS)) : null,
    );
    await settled(container);

    const table = container.querySelector('[aria-label="Audit entries"]')?.textContent ?? "";
    expect(table).toContain("u_admin");
    expect(table).toContain(ACTION_PHRASES["grant"]);
    expect(table).toContain("principal u_wide");
    expect(table).toContain("read:client.name");
    expect(table).toContain(ACTION_PHRASES["leash_change"]);
    expect(container.textContent).toContain(WITHHELD_ENTRIES_ARE_NOT_LISTED);
  });

  test("the people a filter offers are the actors the answer carried and nobody else", async () => {
    // What breaks if this is deleted: the dropdown can list everybody in the ledger, which is the
    // actors of every entry this reader was not shown. The answer carries one actor and the rows
    // name another who is not offered, which only the answer's own list can decide.
    const { container } = await mount("/audit", (url) =>
      url.pathname === AUDIT_OPERATION ? json(ledgerPage(ROWS, { actors: ["u_admin"] })) : null,
    );
    await settled(container);

    const selects = [...container.querySelectorAll("select")];
    const who = selects.find((one) => one.closest("label")?.textContent?.startsWith("Who"));
    const offered = [...(who?.querySelectorAll("option") ?? [])].map((one) => one.value);
    expect(offered).toEqual(["", "u_admin"]);
    expect(offeredActors(readLedgerPage(ledgerPage([], { actors: [] })), "u_typed")).toEqual(["u_typed"]);
  });

  test("choosing a filter narrows the request and a new filter starts from the first page", async () => {
    // What breaks if this is deleted: a select that changes nothing, or a change that appends the
    // new question's answers to the old one's pages.
    const { container, idp } = await mount("/audit", (url) =>
      url.pathname === AUDIT_OPERATION ? json(ledgerPage(ROWS)) : null,
    );
    await settled(container);
    const action = [...container.querySelectorAll("select")].find((one) =>
      one.closest("label")?.textContent?.startsWith("Action"),
    ) as HTMLSelectElement;

    fireEvent.change(action, { target: { value: "revoke" } });
    await waitFor(() => {
      expect(asked(idp, AUDIT_OPERATION).at(-1)?.searchParams.get("action")).toBe("revoke");
    });
    expect(asked(idp, AUDIT_OPERATION).at(-1)?.searchParams.has("cursor")).toBe(false);
  });

  test("more entries are fetched from the cursor and appended, and the control goes when there is no cursor", async () => {
    // What breaks if this is deleted: the page repeats page one, replaces it, or offers a control
    // that fetches nothing.
    const { container, idp } = await mount("/audit", (url) => {
      if (url.pathname !== AUDIT_OPERATION) {
        return null;
      }
      return url.searchParams.get("cursor") === "c1"
        ? json(ledgerPage([{ action: "revoke", actor_id: "u_other", subject_kind: "principal", subject_id: "u_old" }]))
        : json(ledgerPage(ROWS, { next: "c1" }));
    });
    await settled(container);
    fireEvent.click(container.querySelector("button.button") as HTMLElement);

    await waitFor(() => {
      expect(container.textContent).toContain("principal u_old");
    });
    expect(container.textContent).toContain("principal u_wide");
    expect(container.querySelector("button.button")).toBeNull();
    expect(asked(idp, AUDIT_OPERATION)).toHaveLength(2);
  });

  test("nothing, unreachable and refused are three different sentences, and reading is a fourth", async () => {
    // What breaks if this is deleted: an empty ledger, a network that is down and a refusal read
    // alike, which `docs/admin-console.md` forbids; or the refusal is paraphrased into a sentence
    // about permissions, which tells a reader what they may not see.
    const empty = await mount("/audit", (url) =>
      url.pathname === AUDIT_OPERATION ? json(ledgerPage([])) : null,
    );
    await settled(empty.container);
    expect(empty.container.textContent).toContain(NO_ENTRIES);

    const refused = await mount("/audit", (url) =>
      url.pathname === AUDIT_OPERATION ? json({ message: "I could not find that.", trace_id: "t-1" }, 404) : null,
    );
    await settled(refused.container);
    expect(refused.container.textContent).toContain(SOMETHING_DID_NOT_WORK);
    expect(refused.container.textContent).toContain("I could not find that.");
    expect(refused.container.textContent).not.toMatch(/permission|not allowed|denied/i);

    const unreachable = await mount("/audit", (url) => {
      if (url.pathname === AUDIT_OPERATION) {
        throw new TypeError("network down");
      }
      return null;
    });
    await settled(unreachable.container);
    expect(unreachable.container.textContent).toContain(THE_BRAIN_COULD_NOT_BE_REACHED);
    expect(unreachable.container.textContent).not.toContain(SOMETHING_DID_NOT_WORK);

    expect(new Set([NO_ENTRIES, SOMETHING_DID_NOT_WORK, THE_BRAIN_COULD_NOT_BE_REACHED, READING_THE_LEDGER]).size).toBe(4);
  });

  test("a full history says it filled a page and never how much it left out", async () => {
    // What breaks if this is deleted: a full history reads as a complete one, or grows a count.
    const { container } = await mount("/audit?subject=principal:u_wide", (url) => {
      if (url.pathname === HISTORY_OPERATION) {
        return json({
          subject_kind: "principal",
          subject_id: "u_wide",
          events: [{ at: "2019-03-04T09:00:00Z", action: "grant", actor_id: "u_admin", details: {} }],
          full: true,
        });
      }
      return url.pathname === AUDIT_OPERATION ? json(ledgerPage([])) : null;
    });
    await waitFor(() => {
      expect(container.textContent).toContain(HISTORY_FILLED_A_PAGE);
    });
    const history = container.querySelector('[aria-label="Permission history"]')?.textContent ?? "";
    expect(history).toContain(ACTION_PHRASES["grant"]);
    expect(history).not.toMatch(/\b\d+\s+(more|changes|entries|events)\b/i);
  });
});

describe("what the query module does with a body", () => {
  test("a page has no path from a total to a renderer", () => {
    // What breaks if this is deleted: a `total` reaches a component and a footer counts what was
    // withheld.
    const page = readLedgerPage({ ...(ledgerPage(ROWS) as object), total: 47 });

    expect(Object.keys(page).sort()).toEqual(["actions", "actors", "kinds", "nextCursor", "rows"]);
  });

  test("an address with a period or order nobody offered reads as the default rather than as a guess", () => {
    // What breaks if this is deleted: a hand-edited address sends an order the route refuses, and
    // the page is a 422 rather than the ledger.
    const filters = filtersFrom(new URLSearchParams("period=forever&order=sideways"));

    expect(filters.period).toBe(DEFAULT_FILTERS.period);
    expect(filters.order).toBe(DEFAULT_FILTERS.order);
    expect(subjectFrom(new URLSearchParams("subject=nocolon"))).toBeNull();
    expect(subjectFrom(new URLSearchParams("subject=principal:"))).toBeNull();
  });
});
