/**
 * The Audit log on the page kit: what it asks for, what a row says, what its filters offer, one
 * subject's page, and the four states.
 *
 * The pages are mounted through their own route file on a memory router, signed in through the real
 * session modules and answered by a stand-in API, so an address that does not resolve fails here.
 *
 * **The failures worth testing are about reading and about leaking.** A row that prints a principal
 * id or a fragment such as "placed or lifted" where a person needs a name and what happened; a
 * filter offering somebody the reader was never shown; a parameter the route does not declare, which
 * FastAPI drops without a word; and a count of anything.
 *
 * **What a filter offers is asserted over the rendered options**, and every parameter the page sends
 * and every action it can label are read out of the API's own document.
 *
 * Task ids: M27.7.13, M27.16.1, M33.4.1.3
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  AUDIT_PAGE_SIZE,
  auditApiPath,
  DEFAULT_FILTERS,
  filtersFrom,
  historyAddress,
  periodSince,
  readLedgerPage,
  subjectAddress,
  subjectFrom,
} from "../src/pages/auditQuery";
import {
  AUDIT_HEADING,
  NO_ENTRIES,
  NOTHING_MATCHES,
  READING_THE_LEDGER,
} from "../src/pages/audit/AuditPage";
import { HISTORY_FILLED_A_PAGE, PERMISSIONS_VIEW } from "../src/pages/audit/AuditSubjectPage";
import { NO_PATTERN, REDACTED_LABEL, STATISTICS_HEADING } from "../src/pages/audit/auditStatistics";
import { ACTION_LABELS, NO_NAME, whatWords } from "../src/pages/audit/auditWords";
import { THAT_DID_NOT_WORK, THE_BRAIN_COULD_NOT_BE_REACHED } from "../src/ui/FailureNotice";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { apiDocument, declaredParameterSchema, declaredQueryParameters } from "./support/openapi";
import { installRadixStubs } from "./support/radix";

const AUDIT_OPERATION = "/api/v1/audit";
const HISTORY_OPERATION = "/api/v1/audit/history";
const CONSOLE_ORIGIN = "https://console.test";

/** Principal ids nothing may print: the rows' people are named in `people`. */
const ADMIN = "u_admin_4f1c";
const WIDE = "u_wide_9a2e";
const STEWARD = "u_steward_77b0";

beforeAll(async () => {
  installRadixStubs();
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

const PEOPLE = { [ADMIN]: "Priya Shah", [WIDE]: "Ahmed Khan" };

function ledgerPage(rows: Row[], extra: { next?: string | null; actors?: string[] } = {}): unknown {
  return {
    items: rows.map((one) => ({ at: one.at ?? "2019-03-04T09:00:00Z", details: one.details ?? {}, ...one })),
    next_cursor: extra.next ?? null,
    order: "newest",
    actions: Object.keys(ACTION_LABELS),
    subject_kinds: ["agent", "legal_hold", "principal"],
    actors: extra.actors ?? [...new Set(rows.map((one) => one.actor_id))],
    people: PEOPLE,
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

type Answer = (url: URL) => Response | null;

async function mount(path: string, answer: Answer): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url) {
      return answer(new URL(url, CONSOLE_ORIGIN));
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/pages/Audit.route");
  const router = createMemoryRouter(routes.map((one) => ({ path: `/${one.path}`, element: one.element })), {
    initialEntries: [path],
  });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    const text = container.textContent ?? "";
    if (container.querySelector("h1") === null || text.includes(READING_THE_LEDGER)) {
      throw new Error("still reading");
    }
  });
  return { container, idp };
}

function asked(idp: FakeIdp, operation: string): URL[] {
  return idp.urls.map((url) => new URL(url, CONSOLE_ORIGIN)).filter((url) => url.pathname === operation);
}

function button(container: HTMLElement, words: string): HTMLButtonElement | undefined {
  return [...container.querySelectorAll<HTMLButtonElement>("button")].find((one) => (one.textContent ?? "").trim() === words);
}

function choice(container: HTMLElement, label: string): HTMLSelectElement {
  const found = [...container.querySelectorAll("label")].find((one) => one.textContent === label);
  const select = found === undefined ? null : (container.ownerDocument.getElementById(found.htmlFor) as HTMLSelectElement | null);
  if (select === null) {
    throw new Error(`no ${label} filter`);
  }
  return select;
}

const ROWS: Row[] = [
  { action: "grant", actor_id: ADMIN, subject_kind: "principal", subject_id: WIDE, details: { capability: "read:client.name" } },
  { action: "legal_hold", actor_id: ADMIN, subject_kind: "legal_hold", subject_id: "MATTER-12", details: { change: "lifted" } },
  { action: "leash_change", actor_id: STEWARD, subject_kind: "agent", subject_id: "quote-helper-slug" },
];

describe("what the Audit log asks for", () => {
  test("every parameter the pages send is one the route declares, the subject's page included", async () => {
    // What breaks if this is deleted: a filter the API ignores. FastAPI drops an undeclared query
    // parameter without a word, so a page narrowed to one subject would list the whole ledger.
    const declared = new Set(declaredQueryParameters(AUDIT_OPERATION, "get"));
    const list = await mount("/audit?action=grant&kind=principal&period=day&order=oldest", (url) =>
      url.pathname === AUDIT_OPERATION ? json(ledgerPage(ROWS, { next: "c1" })) : null,
    );
    fireEvent.click(button(list.container, "Show newer entries") as HTMLElement);
    await waitFor(() => {
      expect(asked(list.idp, AUDIT_OPERATION)).toHaveLength(2);
    });
    const subject = await mount(subjectAddress("principal", WIDE), (url) =>
      url.pathname === AUDIT_OPERATION ? json(ledgerPage(ROWS.slice(0, 1))) : null,
    );

    const sent = [...asked(list.idp, AUDIT_OPERATION), ...asked(subject.idp, AUDIT_OPERATION)].flatMap((url) => [
      ...url.searchParams.keys(),
    ]);
    expect(sent.filter((name) => !declared.has(name))).toEqual([]);
    const [first, second] = asked(list.idp, AUDIT_OPERATION);
    expect(first?.searchParams.get("subject_kind")).toBe("principal");
    expect(first?.searchParams.get("action")).toBe("grant");
    expect(first?.searchParams.get("order")).toBe("oldest");
    expect(second?.searchParams.get("cursor")).toBe("c1");
    const [narrowed] = asked(subject.idp, AUDIT_OPERATION);
    expect(narrowed?.searchParams.get("subject_kind")).toBe("principal");
    expect(narrowed?.searchParams.get("subject_id")).toBe(WIDE);
    expect(narrowed?.searchParams.has("since")).toBe(false);
  });

  test("the page size is one the route answers and a period is sent as an instant with its offset", () => {
    // What breaks if this is deleted: every load is a 422; or `since` goes without an offset and the
    // route refuses the naive instant.
    const limit = declaredParameterSchema(AUDIT_OPERATION, "get", "limit");
    const now = new Date("2019-03-04T09:00:00Z");
    const since = new URL(auditApiPath({ ...DEFAULT_FILTERS, period: "day" }, now, null), CONSOLE_ORIGIN).searchParams.get("since");

    expect(AUDIT_PAGE_SIZE).toBeLessThanOrEqual(limit["maximum"] as number);
    expect(AUDIT_PAGE_SIZE).toBeGreaterThanOrEqual(limit["minimum"] as number);
    expect(since).toBe("2019-03-03T09:00:00.000Z");
    expect(periodSince("all", now)).toBeNull();
  });

  test("every action the API can record has a label in words, and a change is named by what it was", () => {
    // What breaks if this is deleted: an action added next month arrives as its code, or a legal
    // hold lifted reads the same as one placed, which is what the owner could not read.
    const schemas = (apiDocument()["components"] as Record<string, unknown>)["schemas"] as Record<string, Record<string, unknown>>;
    const actions = schemas["AuditAction"]?.["enum"] as string[];

    expect(actions.length).toBeGreaterThan(0);
    expect(Object.keys(ACTION_LABELS).sort()).toEqual([...actions].sort());
    expect(whatWords("legal_hold", { change: "lifted" })).toBe("Legal hold lifted");
    expect(whatWords("legal_hold", { change: "placed" })).toBe("Legal hold placed");
    expect(whatWords("organisation", { change: "joined" })).toBe("Added to a team");
    expect(whatWords("halt", { act: "resume" })).toBe("Work resumed");
    expect(whatWords("grant", {})).toBe("Capability granted");
    expect(whatWords("setting", { change: "on" })).toBe("Setting switched on");
  });
});

describe("what the Audit log shows", () => {
  test("a row reads as a name, what happened and what it was about, and no principal id is printed", async () => {
    // What breaks if this is deleted: every refusal below is satisfied by a page that renders
    // nothing; and the ids the owner found cluttering the page come back.
    const { container } = await mount("/audit", (url) => (url.pathname === AUDIT_OPERATION ? json(ledgerPage(ROWS)) : null));

    const table = within(container.querySelector("table") as HTMLElement);
    expect(table.getAllByText("Priya Shah").length).toBeGreaterThan(0);
    expect(table.getByText("Capability granted")).toBeTruthy();
    expect(table.getByText("Legal hold lifted")).toBeTruthy();
    expect(table.getByText("Ahmed Khan")).toBeTruthy();
    expect(table.getByText("Legal hold MATTER-12")).toBeTruthy();
    expect(table.getByText(NO_NAME)).toBeTruthy();
    expect(container.textContent).toContain("Capability: read:client.name");
    expect(container.textContent).not.toContain(ADMIN);
    expect(container.textContent).not.toContain(WIDE);
    expect(container.textContent).not.toContain("quote-helper-slug");
    expect(container.querySelector("h1")?.textContent).toBe(AUDIT_HEADING);
    expect(container.textContent).not.toMatch(/\bof \d+\b|\btotal\b|\bshowing\b/i);
  });

  test("the people a filter offers are the actors the answer carried, by name, and nobody else", async () => {
    // What breaks if this is deleted: the dropdown can list everybody in the ledger, which is the
    // actors of every entry this reader was not shown, or list them by id.
    const { container } = await mount("/audit", (url) =>
      url.pathname === AUDIT_OPERATION ? json(ledgerPage(ROWS, { actors: [ADMIN] })) : null,
    );
    const who = choice(container, "Who");

    expect([...who.options].map((one) => one.value)).toEqual(["", ADMIN]);
    expect([...who.options].map((one) => one.textContent)).toEqual(["Anybody", "Priya Shah"]);
  });

  test("choosing a filter and searching narrow the request, and a narrowed empty answer says so", async () => {
    // What breaks if this is deleted: a select that changes nothing, or an empty narrowed ledger that
    // reads as an empty ledger.
    const { container, idp } = await mount("/audit", (url) => {
      if (url.pathname !== AUDIT_OPERATION) {
        return null;
      }
      return url.searchParams.has("action") ? json(ledgerPage([])) : json(ledgerPage(ROWS));
    });
    fireEvent.change(choice(container, "What"), { target: { value: "revoke" } });
    await waitFor(() => {
      expect(container.textContent).toContain(NOTHING_MATCHES);
    });
    fireEvent.change(container.querySelector('input[type="search"]') as HTMLInputElement, { target: { value: "client" } });
    await waitFor(() => {
      expect(asked(idp, AUDIT_OPERATION).at(-1)?.searchParams.get("q")).toBe("client");
    });

    expect(asked(idp, AUDIT_OPERATION).at(-1)?.searchParams.get("action")).toBe("revoke");
  });

  test("older entries are fetched from the cursor and appended, and the control goes with the cursor", async () => {
    // What breaks if this is deleted: the page repeats page one, replaces it, or offers a control that
    // fetches nothing.
    const { container, idp } = await mount("/audit", (url) => {
      if (url.pathname !== AUDIT_OPERATION) {
        return null;
      }
      return url.searchParams.get("cursor") === "c1"
        ? json(ledgerPage([{ action: "revoke", actor_id: ADMIN, subject_kind: "principal", subject_id: WIDE }]))
        : json(ledgerPage(ROWS, { next: "c1" }));
    });
    fireEvent.click(button(container, "Show older entries") as HTMLElement);

    await waitFor(() => {
      expect(container.textContent).toContain("Capability removed");
    });
    expect(container.textContent).toContain("Capability granted");
    expect(button(container, "Show older entries")).toBeUndefined();
    expect(asked(idp, AUDIT_OPERATION)).toHaveLength(2);
  });

  test("nothing, unreachable and refused are different sentences, and reading is another", async () => {
    // What breaks if this is deleted: an empty ledger, a network that is down and a refusal read
    // alike; or the refusal is paraphrased into a sentence about permissions.
    const empty = await mount("/audit", (url) => (url.pathname === AUDIT_OPERATION ? json(ledgerPage([])) : null));
    expect(empty.container.textContent).toContain(NO_ENTRIES);

    const refused = await mount("/audit", (url) =>
      url.pathname === AUDIT_OPERATION ? json({ message: "I could not find that.", trace_id: "t-1" }, 404) : null,
    );
    expect(refused.container.textContent).toContain(THAT_DID_NOT_WORK);
    expect(refused.container.textContent).not.toMatch(/permission|not allowed|denied/i);

    const unreachable = await mount("/audit", (url) => {
      if (url.pathname === AUDIT_OPERATION) {
        throw new TypeError("network down");
      }
      return null;
    });
    expect(unreachable.container.textContent).toContain(THE_BRAIN_COULD_NOT_BE_REACHED);
    expect(new Set([NO_ENTRIES, THAT_DID_NOT_WORK, THE_BRAIN_COULD_NOT_BE_REACHED, READING_THE_LEDGER]).size).toBe(4);
  });
});

describe("the refusal and redaction statistics", () => {
  const STATISTICS_OPERATION = "/api/v1/audit/statistics";
  const ENUMERATING = "A colleague is being told there is nothing there across a spread of different places.";
  const MISSING_A_GRANT = "A colleague keeps being told there is nothing there, always in the same place.";

  function statistics(over: Record<string, unknown> = {}): unknown {
    return {
      since: "2019-02-25T09:00:00Z",
      until: "2019-03-04T09:00:00Z",
      refusals: [
        { shape: "access_needed", reads_as: MISSING_A_GRANT, occurrences: 1 },
        { shape: "enumeration", reads_as: ENUMERATING, occurrences: 37 },
      ],
      redacted_entries: 29,
      read_at_most: 5000,
      ...over,
    };
  }

  function card(container: HTMLElement): Element | undefined {
    return [...container.querySelectorAll('[data-slot="section-card"]')].find((one) => one.querySelector("h2")?.textContent === STATISTICS_HEADING);
  }

  test("each shape is drawn in the API's own sentence with how often, and the redactions as one number", async () => {
    // What breaks if this is deleted: the card can sum the shapes into a total, draw a figure it
    // computed, or name what was refused, and nothing reading the page would notice.
    const { container, idp } = await mount("/audit", (url) => {
      if (url.pathname === STATISTICS_OPERATION) {
        return json(statistics());
      }
      return url.pathname === AUDIT_OPERATION ? json(ledgerPage(ROWS)) : null;
    });
    await waitFor(() => {
      expect(card(container)?.textContent ?? "").toContain(ENUMERATING);
    });
    const text = card(container)?.textContent ?? "";

    expect(text).toContain(MISSING_A_GRANT);
    expect(text).toContain("37 times");
    expect(text).toContain("once");
    expect(text).toContain(REDACTED_LABEL);
    expect(text).toContain("29");
    expect(text).not.toContain("38");
    expect(text).not.toMatch(/\bof \d+\b|\btotal\b|\bshowing\b/i);
    const sent = asked(idp, STATISTICS_OPERATION);
    expect(sent).toHaveLength(1);
    expect([...(sent[0]?.searchParams.keys() ?? [])]).toEqual([]);
  });

  test("a card the API answers 404 is left out and the ledger still draws, and no pattern is said in words", async () => {
    // What breaks if this is deleted: a reader the statistics are not for is shown an empty card, or
    // a window with no pattern draws an empty list that reads as a broken page.
    const refused = await mount("/audit", (url) => {
      if (url.pathname === STATISTICS_OPERATION) {
        return json({ message: "I could not find that.", trace_id: "t-9" }, 404);
      }
      return url.pathname === AUDIT_OPERATION ? json(ledgerPage(ROWS)) : null;
    });
    await waitFor(() => {
      expect(refused.container.textContent).toContain("Capability granted");
    });
    expect(card(refused.container)).toBeUndefined();

    const quiet = await mount("/audit", (url) => {
      if (url.pathname === STATISTICS_OPERATION) {
        return json(statistics({ refusals: [], redacted_entries: 0 }));
      }
      return url.pathname === AUDIT_OPERATION ? json(ledgerPage(ROWS)) : null;
    });
    await waitFor(() => {
      expect(card(quiet.container)?.textContent ?? "").toContain(NO_PATTERN);
    });
  });
});

describe("one subject's page", () => {
  test("an old history link opens the subject's page, titled by name, with its ids only in Advanced", async () => {
    // What breaks if this is deleted: links from the Overview and from colleagues stop opening the
    // subject, or the page is titled with a principal id.
    const { container } = await mount(`/audit?subject=principal:${WIDE}`, (url) => {
      if (url.pathname === AUDIT_OPERATION) {
        return json(ledgerPage(ROWS.slice(0, 1)));
      }
      return null;
    });

    await waitFor(() => {
      expect(container.querySelector("h1")?.textContent).toBe("Ahmed Khan");
    });
    const advanced = container.querySelector('[data-slot="advanced"]') as HTMLElement;
    expect(advanced.textContent).toContain(WIDE);
    const outside = [...container.querySelectorAll("*")].filter(
      (one) => one.children.length === 0 && !advanced.contains(one),
    );
    expect(outside.some((one) => (one.textContent ?? "").includes(WIDE))).toBe(false);
    expect(historyAddress(new URLSearchParams("action=grant"), "principal", WIDE)).toBe(subjectAddress("principal", WIDE));
  });

  test("a person's access changes come from the history route, and a full history says so without a number", async () => {
    // What breaks if this is deleted: the question an auditor brings about a person (who gave them
    // that) has no answer, or a full history reads as a complete one or grows a count.
    const { container, idp } = await mount(subjectAddress("principal", WIDE, "permissions"), (url) => {
      if (url.pathname === HISTORY_OPERATION) {
        return json({
          subject_kind: "principal",
          subject_id: WIDE,
          events: [{ at: "2019-03-04T09:00:00Z", action: "grant", actor_id: ADMIN, details: {} }],
          full: true,
          people: PEOPLE,
        });
      }
      return url.pathname === AUDIT_OPERATION ? json(ledgerPage([])) : null;
    });
    await waitFor(() => {
      expect(container.textContent).toContain(HISTORY_FILLED_A_PAGE);
    });

    const [history] = asked(idp, HISTORY_OPERATION);
    expect(history?.searchParams.get("subject_kind")).toBe("principal");
    expect(history?.searchParams.get("subject_id")).toBe(WIDE);
    expect(container.querySelector('[data-slot="view-switch"] [aria-current="page"]')?.textContent).toContain(PERMISSIONS_VIEW);
    expect(container.textContent).toContain("Capability granted");
    expect(container.textContent).not.toMatch(/\b\d+\s+(more|changes|entries|events)\b/i);
  });

  test("a subject whose reach nothing grants is offered no access changes view", async () => {
    // What breaks if this is deleted: a legal hold's page offers a view that can only ever be empty.
    const { container, idp } = await mount(subjectAddress("legal_hold", "MATTER-12", "permissions"), (url) =>
      url.pathname === AUDIT_OPERATION ? json(ledgerPage(ROWS.slice(1, 2))) : null,
    );

    expect(container.querySelector('[data-slot="view-switch"]')).toBeNull();
    expect(asked(idp, HISTORY_OPERATION)).toEqual([]);
    expect(container.querySelector("h1")?.textContent).toBe("Legal hold MATTER-12");
  });
});

describe("what the query module does with a body", () => {
  test("a page has no path from a total to a renderer", () => {
    // What breaks if this is deleted: a `total` reaches a component and a footer counts what was
    // withheld.
    const page = readLedgerPage({ ...(ledgerPage(ROWS) as object), total: 47 });

    expect(Object.keys(page).sort()).toEqual(["actions", "actors", "kinds", "nextCursor", "people", "rows"]);
  });

  test("an address with a period or order nobody offered reads as the default rather than as a guess", () => {
    // What breaks if this is deleted: a hand-edited address sends an order the route refuses.
    const filters = filtersFrom(new URLSearchParams("period=forever&order=sideways"));

    expect(filters.period).toBe(DEFAULT_FILTERS.period);
    expect(filters.order).toBe(DEFAULT_FILTERS.order);
    expect(subjectFrom(new URLSearchParams("subject=nocolon"))).toBeNull();
  });
});
