/**
 * The console's half of the list convention: what a question looks like on the wire, which values a
 * filter may offer, and how pages are walked.
 *
 * **The spellings are read out of `brain/listing.py`**, because an undeclared query parameter is
 * discarded by FastAPI without a word, and a console spelling `q` or `sort` any other way would draw
 * an unsearched, unordered list as the answer to the question on the screen.
 *
 * **The hook is driven against a stand-in API** that answers from the query string, so what is held
 * is this console's half: which question each request asks, that a changed question starts from the
 * first page, that "Show more" sends back the cursor it was given and adds rows, and that a slow
 * answer to an old question never lands on the screen.
 *
 * Task ids: M27.8.6
 */

import { act, fireEvent, render, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import {
  DESCENDING,
  LIST_PAGE_SIZE,
  NO_QUESTION,
  SEARCH_PARAMETER,
  SORT_PARAMETER,
  listPath,
  narrows,
  offeredFrom,
  type FilterChoice,
} from "../src/components/listing";
import { ISSUER, stubServedConfig } from "./support/auth";
import { extractOne, readRepoFile } from "./support/repo";

interface Row {
  readonly id: string;
  readonly department: string | null;
  readonly tags: readonly string[];
  readonly active: boolean;
}

const CHOICES: readonly FilterChoice<Row>[] = [
  { column: "department", label: "Department", everything: "All", read: (row) => row.department },
  { column: "tags", label: "Tag", everything: "Any", read: (row) => row.tags },
  { column: "active", label: "Active", everything: "Either", read: (row) => row.active },
];

function python(name: string): string {
  return extractOne(readRepoFile("src/brain/listing.py"), new RegExp(`^${name}: Final = (.+)$`, "m"), name);
}

describe("what a question looks like on the wire", () => {
  test("the parameter names and the page size are the ones brain.listing declares", () => {
    // What breaks if this is deleted: a search or an order sent under a name the route does not
    // declare, which FastAPI discards and answers with the unsearched list.
    expect(JSON.stringify(SEARCH_PARAMETER)).toBe(python("SEARCH_PARAM"));
    expect(JSON.stringify(SORT_PARAMETER)).toBe(python("SORT_PARAM"));
    expect(JSON.stringify(DESCENDING)).toBe(python("DESCENDING"));
    expect(LIST_PAGE_SIZE).toBeLessThanOrEqual(Number(python("MAX_PAGE_ROWS")));
  });

  test("a question is sent whole, filters in column order, and an unset filter is not sent", () => {
    // What breaks if this is deleted: one question spelled two ways, so a cursor minted for one
    // is refused for the other, or an empty filter sent as `department:` and refused.
    const path = listPath(
      "/govern/sessions",
      { search: "  wei  ", filters: { principal_id: "u_1", department: "web", tags: "" }, sort: "-signed_in_at" },
      "c-1",
      20,
      { days: "7" },
    );
    const url = new URL(path, "https://console.test");

    expect(url.pathname).toBe("/govern/sessions");
    expect(url.searchParams.get("limit")).toBe("20");
    expect(url.searchParams.get("q")).toBe("wei");
    expect(url.searchParams.getAll("filter")).toEqual(["department:web", "principal_id:u_1"]);
    expect(url.searchParams.get("sort")).toBe("-signed_in_at");
    expect(url.searchParams.get("days")).toBe("7");
    expect(url.searchParams.get("cursor")).toBe("c-1");
    expect([...new URL(listPath("/x", NO_QUESTION, null), "https://console.test").searchParams.keys()]).toEqual(["limit"]);
  });

  test("a question narrows only when it searches or filters, never when it only orders", () => {
    // What breaks if this is deleted: "nothing matches" said over an empty list nobody narrowed,
    // which reads as a search that failed rather than a list with nothing in it.
    expect(narrows(NO_QUESTION)).toBe(false);
    expect(narrows({ ...NO_QUESTION, sort: "name" })).toBe(false);
    expect(narrows({ ...NO_QUESTION, search: " x " })).toBe(true);
    expect(narrows({ ...NO_QUESTION, filters: { department: "web" } })).toBe(true);
    expect(narrows({ ...NO_QUESTION, filters: { department: "" } })).toBe(false);
  });
});

describe("which values a filter may offer", () => {
  test("only values carried by rows drawn, spelled as the route compares them, and never fewer later", () => {
    // What breaks if this is deleted: a dropdown naming a department no drawn row is in, a boolean
    // offered as a word the route does not match, or a value that disappears once it is chosen.
    const first = offeredFrom<Row>({}, [
      { id: "a", department: "web", tags: ["north", ""], active: true },
      { id: "b", department: null, tags: [], active: false },
    ], CHOICES);
    expect(first).toEqual({ department: ["web"], tags: ["north"], active: ["false", "true"] });

    const later = offeredFrom<Row>(first, [{ id: "c", department: "sales", tags: ["south"], active: true }], CHOICES);
    expect(later).toEqual({ department: ["sales", "web"], tags: ["north", "south"], active: ["false", "true"] });
    expect(offeredFrom<Row>(later, [], CHOICES)).toEqual(later);
  });
});

interface StandIn {
  readonly urls: URL[];
  readonly release: (index: number) => void;
}

/** A stand-in API answering from the query string, holding each answer until released when asked to. */
function standIn(hold = false): StandIn {
  const urls: URL[] = [];
  const waiting: (() => void)[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: unknown) => {
      const url = new URL(String(input), "https://console.test");
      urls.push(url);
      const q = url.searchParams.get("q") ?? "";
      const cursor = url.searchParams.get("cursor");
      const items =
        cursor === "c-2"
          ? [{ id: `${q}-second`, department: "sales", tags: [], active: true }]
          : [{ id: `${q}-first`, department: "web", tags: [], active: true }];
      const body = { items, next_cursor: cursor === null ? "c-2" : null, truncated: false };
      if (hold) {
        await new Promise<void>((resolve) => waiting.push(resolve));
      }
      return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
    }),
  );
  return {
    urls,
    release: (index: number) => {
      waiting[index]?.();
    },
  };
}

async function hook() {
  vi.resetModules();
  stubServedConfig({ issuer: ISSUER });
  const { useListing } = await import("../src/components/useListing");
  return useListing;
}

describe("walking a list", () => {
  test("show more sends back the cursor and adds its rows, and a new question starts again with none", async () => {
    // What breaks if this is deleted: a second page that replaces the first, a cursor never sent
    // back, or a cursor carried into a new question, which the route refuses as malformed.
    const api = standIn();
    const useListing = await hook();
    const { result } = renderHook(() => useListing<Row>("/rows", { choices: CHOICES }));

    await waitFor(() => {
      expect(result.current.busy).toBe(false);
    });
    expect(result.current.more).toBe(true);
    act(() => {
      result.current.showMore();
    });
    await waitFor(() => {
      expect(result.current.rows.map((one) => one.id)).toEqual(["-first", "-second"]);
    });
    expect(result.current.more).toBe(false);
    expect(api.urls[1]?.searchParams.get("cursor")).toBe("c-2");
    expect(result.current.offered["department"]).toEqual(["sales", "web"]);

    act(() => {
      result.current.ask({ ...NO_QUESTION, search: "wei" });
    });
    await waitFor(() => {
      expect(result.current.rows.map((one) => one.id)).toEqual(["wei-first"]);
    });
    const last = api.urls[api.urls.length - 1];
    expect(last?.searchParams.get("q")).toBe("wei");
    expect(last?.searchParams.has("cursor")).toBe(false);
    // Values shown under the old question stay offered: they were shown.
    expect(result.current.offered["department"]).toEqual(["sales", "web"]);
  });

  test("an answer to a question that has since changed never lands", async () => {
    // What breaks if this is deleted: typing "wei" then "wen" with the first answer arriving last,
    // and the rows on the screen answering the question no longer in the search box.
    const api = standIn(true);
    const useListing = await hook();
    const { result } = renderHook(() => useListing<Row>("/rows"));

    await waitFor(() => {
      expect(api.urls).toHaveLength(1);
    });
    act(() => {
      result.current.ask({ ...NO_QUESTION, search: "wen" });
    });
    await waitFor(() => {
      expect(api.urls).toHaveLength(2);
    });
    await act(async () => {
      api.release(1);
      await Promise.resolve();
    });
    await waitFor(() => {
      expect(result.current.rows.map((one) => one.id)).toEqual(["wen-first"]);
    });
    await act(async () => {
      api.release(0);
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    expect(result.current.rows.map((one) => one.id)).toEqual(["wen-first"]);
  });

  test("a moved version asks the first page again with the question kept", async () => {
    // What breaks if this is deleted: a list that shows what was there before a write, or one that
    // forgets the search somebody had typed the moment they end a session from it.
    const api = standIn();
    const useListing = await hook();
    const { result, rerender } = renderHook(({ version }) => useListing<Row>("/rows", { version }), {
      initialProps: { version: 0 },
    });
    await waitFor(() => {
      expect(result.current.busy).toBe(false);
    });
    act(() => {
      result.current.ask({ ...NO_QUESTION, search: "wei" });
    });
    await waitFor(() => {
      expect(result.current.rows.map((one) => one.id)).toEqual(["wei-first"]);
    });
    const before = api.urls.length;
    rerender({ version: 1 });
    await waitFor(() => {
      expect(api.urls.length).toBe(before + 1);
    });
    expect(api.urls[api.urls.length - 1]?.searchParams.get("q")).toBe("wei");
  });
});

describe("the controls", () => {
  test("a filter offers what was shown and keeps saying the value it is set to", async () => {
    // What breaks if this is deleted: a select whose chosen value is not among its options, which
    // a browser draws as the first option, so the page says "All" while asking for one department.
    standIn();
    const useListing = await hook();
    const { ListControls } = await import("../src/components/ListControls");
    function Harness() {
      const listing = useListing<Row>("/rows", { choices: CHOICES, initial: { ...NO_QUESTION, filters: { department: "finance" } } });
      return <ListControls label="Narrow the rows" listing={listing} choices={CHOICES} sorts={[{ value: "", label: "By id" }]} />;
    }
    const { container } = render(<Harness />);
    const department = () =>
      [...container.querySelectorAll("select")].find((one) => one.closest("label")?.firstChild?.textContent === "Department") as HTMLSelectElement;

    await waitFor(() => {
      expect([...department().querySelectorAll("option")].map((one) => one.value)).toEqual(["", "web", "finance"]);
    });
    expect(department().value).toBe("finance");
    expect(container.querySelector('form[role="search"]')?.getAttribute("aria-label")).toBe("Narrow the rows");
    expect([...container.querySelectorAll("label")].map((one) => one.firstChild?.textContent)).toContain("Sort by");
    fireEvent.change(department(), { target: { value: "" } });
    expect(department().value).toBe("");
  });
});
