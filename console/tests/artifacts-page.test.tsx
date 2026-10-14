/**
 * The Artifacts page on the shared list: what it asks the route, what it draws of the answer, and
 * what it will not say (M32.5.2.1).
 *
 * Mounted directly on a memory router at its own address, for the reason
 * `tests/sessions-page.test.tsx` gives. The failures worth testing look like the page working: a
 * search that narrows the rows already drawn instead of asking, a filter box offering a kind nobody
 * on the page has, a "Show more" that replaces what was drawn or sends the wrong cursor, a total in
 * a footer, and an empty sentence that says why.
 *
 * **What the controls send is read against the route's own declaration**, so a parameter, a filter
 * column or an order this console invented is a failure here rather than a 422 in front of somebody.
 *
 * Task ids: M32.5.2.1, M27.7.23
 */

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { beforeAll, describe, expect, test } from "vitest";
import { NOTHING_MATCHES, SHOW_MORE } from "../src/components/ListControls";
import { LIST_PAGE_SIZE } from "../src/components/listing";
import { NO_ARTIFACTS, NOTHING_RECORDED, READING_ARTIFACTS } from "../src/pages/operations/ArtifactsPage";
import { ARTIFACT_FILTERS, ARTIFACT_SORTS, type ArtifactRow } from "../src/pages/artifactsQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { backendModelFields } from "./support/python";
import { declaredParameterSchema, declaredQueryParameters } from "./support/openapi";
import { installRadixStubs } from "./support/radix";

const ARTIFACTS_OPERATION = "/api/v1/govern/artifacts";
const CONSOLE_ORIGIN = "https://console.test";
const RULE = "RULE-SENTENCE-SENTINEL";

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/Artifacts");
}, 60_000);

function artifact(id: string, overrides: Partial<ArtifactRow> = {}): ArtifactRow {
  return {
    artifact_id: id,
    kind: "report",
    agent_id: "quote_helper",
    produced_for: "u_someone",
    produced_at: "2019-02-01T00:00:00Z",
    state: "current",
    superseded_by: "",
    run_id: `run_${id}`,
    agent_version: "3",
    kept_as: "payload",
    kept_until: "2019-04-03T09:00:00Z",
    kept_because: "kept 30 days",
    ...overrides,
  };
}

function page(rows: ArtifactRow[], next_cursor: string | null = null): unknown {
  return { items: rows, next_cursor, unread: "", kept_rule: RULE };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

type Answer = (url: URL) => Response | null;

async function mount(answer: Answer): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url) {
      return answer(new URL(url, CONSOLE_ORIGIN));
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { Artifacts } = await import("../src/pages/Artifacts");
  const router = createMemoryRouter([{ path: "/artifacts", element: <Artifacts /> }], { initialEntries: ["/artifacts"] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector("h1") || container.textContent?.includes(READING_ARTIFACTS)) {
      throw new Error("still loading");
    }
  });
  return { container, idp };
}

function asked(idp: FakeIdp): URL[] {
  return idp.urls.map((url) => new URL(url, CONSOLE_ORIGIN)).filter((url) => url.pathname === ARTIFACTS_OPERATION);
}

/** The first `pattern` anywhere in a schema, which is how the route spells what it accepts. */
function patternOf(schema: unknown): RegExp {
  const find = (node: unknown): string | undefined => {
    if (typeof node !== "object" || node === null) {
      return undefined;
    }
    const record = node as Record<string, unknown>;
    if (typeof record["pattern"] === "string") {
      return record["pattern"];
    }
    for (const value of Object.values(record)) {
      const found = find(value);
      if (found !== undefined) {
        return found;
      }
    }
    return undefined;
  };
  const pattern = find(schema);
  if (pattern === undefined) {
    throw new Error("the route declares no pattern for this parameter, so what was sent is unchecked");
  }
  return new RegExp(pattern);
}

function rowsOf(container: HTMLElement): string[] {
  return [...container.querySelectorAll("tbody tr")].map((row) => row.textContent ?? "");
}

describe("what the artifacts page asks for", () => {
  test("it sends only parameters, filters and orders the route declares, and a page size the route allows", async () => {
    // What breaks if this is deleted: a parameter the API ignores (a filter box with a word in it
    // and every row still on the screen), an order the declaration refuses on every change, or a
    // page size it refuses on every load. The filter column and both orders are matched against
    // the patterns the route itself publishes.
    const declared = new Set(declaredQueryParameters(ARTIFACTS_OPERATION, "get"));
    const limit = declaredParameterSchema(ARTIFACTS_OPERATION, "get", "limit");
    const filterGrammar = patternOf(declaredParameterSchema(ARTIFACTS_OPERATION, "get", "filter"));
    const sortGrammar = patternOf(declaredParameterSchema(ARTIFACTS_OPERATION, "get", "sort"));
    const { container, idp } = await mount((url) => (url.pathname === ARTIFACTS_OPERATION ? json(page([artifact("art_1")])) : null));

    fireEvent.change(screen.getByLabelText("Kind"), { target: { value: "report" } });
    fireEvent.change(screen.getByLabelText("Sort by"), { target: { value: "produced_at" } });
    fireEvent.change(container.querySelector('input[type="search"]') as HTMLInputElement, { target: { value: "quote" } });
    await waitFor(() => {
      expect(asked(idp).at(-1)?.searchParams.get("q")).toBe("quote");
    });

    const urls = asked(idp);
    expect(urls.flatMap((url) => [...url.searchParams.keys()]).filter((name) => !declared.has(name))).toEqual([]);
    expect(LIST_PAGE_SIZE).toBeLessThanOrEqual(limit["maximum"] as number);
    const last = urls.at(-1);
    expect(last?.searchParams.getAll("filter")).toEqual(["kind:report"]);
    expect(last?.searchParams.getAll("filter").every((term) => filterGrammar.test(term))).toBe(true);
    for (const order of ARTIFACT_SORTS.map((one) => one.value).filter((one) => one !== "")) {
      expect(sortGrammar.test(order), order).toBe(true);
    }
    expect(last?.searchParams.get("sort")).toBe("produced_at");
  });

  test("the filters the page offers are columns the route declares for filtering", () => {
    // What breaks if this is deleted: a filter offered for a column the route refuses, which is a
    // control that answers every use with a failure. Read from the declared pattern rather than a
    // copy of the column names, so a column removed on the server fails here.
    const grammar = patternOf(declaredParameterSchema(ARTIFACTS_OPERATION, "get", "filter"));
    for (const choice of ARTIFACT_FILTERS) {
      expect(grammar.test(`${choice.column}:anything`), choice.column).toBe(true);
    }
    expect(ARTIFACT_FILTERS.length).toBeGreaterThan(0);
    expect(Object.keys(artifact("x")).sort()).toEqual(backendModelFields("src/brain/artifact_routes.py", "ArtifactView").sort());
  });
});

describe("what the artifacts page draws", () => {
  test("a search is asked of the route and the rows are the route's answer, not the page's narrowing", async () => {
    // What breaks if this is deleted: the search going back into the browser. The stand-in route
    // answers a search for "zzz" with a row that does not contain it, and the page must draw that
    // row: a client-side filter would hide it and look identical to a server's narrowing.
    const first = [artifact("art_1"), artifact("art_2", { kind: "deck" })];
    const { container } = await mount((url) => {
      if (url.pathname !== ARTIFACTS_OPERATION) {
        return null;
      }
      return json(page(url.searchParams.get("q") === "zzz" ? [artifact("art_other", { agent_id: "elsewhere" })] : first));
    });

    expect(rowsOf(container)).toHaveLength(2);
    fireEvent.change(container.querySelector('input[type="search"]') as HTMLInputElement, { target: { value: "zzz" } });
    await waitFor(() => {
      expect(rowsOf(container)).toHaveLength(1);
    });
    expect(container.textContent).not.toContain("quote_helper");
  });

  test("the kind filter offers only kinds on rows drawn", async () => {
    // What breaks if this is deleted: a dropdown naming a kind this reader was not shown an
    // artifact of, which says the kind exists. See `A_FILTER_OFFERS_ONLY_WHAT_WAS_SHOWN`.
    await mount((url) =>
      url.pathname === ARTIFACTS_OPERATION ? json(page([artifact("a", { kind: "deck" }), artifact("b", { kind: "report" })])) : null,
    );

    const kind = screen.getByLabelText("Kind") as HTMLSelectElement;
    expect([...kind.options].map((one) => one.value).sort()).toEqual(["", "deck", "report"]);
    expect([...kind.options].map((one) => one.textContent)).toContain("Deck");
  });

  test("Show more asks for the page after the last one drawn, adds its rows under the others, and ends with the cursor", async () => {
    // What breaks if this is deleted: a pager that replaces the rows, repeats a page, sends a
    // cursor of its own making, or stays after the API stops sending one. The last assertions are
    // the refusal: no total, no "of", no page number anywhere on the page.
    const { container, idp } = await mount((url) => {
      if (url.pathname !== ARTIFACTS_OPERATION) {
        return null;
      }
      return url.searchParams.get("cursor") === "CURSOR-ONE"
        ? json(page([artifact("art_3")]))
        : json(page([artifact("art_1"), artifact("art_2")], "CURSOR-ONE"));
    });
    expect(rowsOf(container)).toHaveLength(2);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: SHOW_MORE }));
    });
    await waitFor(() => {
      expect(rowsOf(container)).toHaveLength(3);
    });
    expect(asked(idp).at(-1)?.searchParams.get("cursor")).toBe("CURSOR-ONE");
    expect(screen.queryByRole("button", { name: SHOW_MORE })).toBeNull();
    expect(container.textContent).not.toMatch(/\b\d+\s+(of|artifacts|more)\b|\bpage \d+\b|\btotal\b/i);
  });

  test("nothing recorded is a sentence with no table and no controls, and the kept rule still shows", async () => {
    // What breaks if this is deleted: an install whose store is not attached drawn as an estate
    // that produced nothing, or a search box over a list that is not there.
    const { container } = await mount((url) =>
      url.pathname === ARTIFACTS_OPERATION ? json({ items: [], next_cursor: null, unread: "UNREAD-SENTINEL", kept_rule: RULE }) : null,
    );

    expect(container.textContent).toContain(NOTHING_RECORDED);
    expect(container.textContent).toContain("UNREAD-SENTINEL");
    expect(container.querySelector("table")).toBeNull();
    expect(container.querySelector('input[type="search"]')).toBeNull();
    expect(container.textContent).toContain(RULE);
  });

  test("empty and narrowed to nothing say different things, and a refusal is not either", async () => {
    // What breaks if this is deleted: "no artifacts yet" said for a search that matched nothing,
    // or the reverse; either says why the list is empty, which a reader cannot know.
    const { container } = await mount((url) =>
      url.pathname === ARTIFACTS_OPERATION ? json(page([])) : null,
    );
    expect(container.textContent).toContain(NO_ARTIFACTS);

    fireEvent.change(container.querySelector('input[type="search"]') as HTMLInputElement, { target: { value: "nobody" } });
    await waitFor(() => {
      expect(container.textContent).toContain(NOTHING_MATCHES);
    });
    expect(container.textContent).not.toContain(NO_ARTIFACTS);

    const refused = await mount((url) =>
      url.pathname === ARTIFACTS_OPERATION ? json({ message: "I could not find that.", trace_id: "t" }, 404) : null,
    );
    expect(refused.container.textContent).not.toContain(NO_ARTIFACTS);
    expect(refused.container.textContent).not.toContain(NOTHING_MATCHES);
  });
});
