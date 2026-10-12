/**
 * The header's search box: what it asks, what it draws, and what it draws nothing for.
 *
 * **Mounted through the application's own route table**, signed in through the real session
 * modules and answered by a stand-in API that records every request, so a deleted route or a box
 * dropped from the header fails here rather than passing a component rendered on its own.
 *
 * Task ids: M27.10.5
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { MIN_QUERY, NOTHING_MATCHES, SEARCH_LABEL, readSearch, searchPath } from "../src/layout/GlobalSearch";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { installRadixStubs } from "./support/radix";

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/Ask.route");
}, 60_000);

async function consoleWith(search: unknown) {
  cleanup();
  const idp = fakeIdentityProvider({
    api(url) {
      const pathname = new URL(url, "https://console.test").pathname;
      if (pathname === "/api/v1/console/search") {
        return new Response(JSON.stringify(search), { status: 200, headers: { "content-type": "application/json" } });
      }
      return null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: ["/"] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    expect(container.querySelector("[data-slot='global-search']")).not.toBeNull();
  });
  return { container, idp };
}

async function typed(container: HTMLElement, text: string) {
  const box = container.querySelector(`input[aria-label='${SEARCH_LABEL}']`) as HTMLInputElement;
  await act(async () => {
    fireEvent.change(box, { target: { value: text } });
  });
}

describe("the search box", () => {
  test("it reads groups and hits only, drops what is not one, and carries no count", () => {
    // What breaks if this is deleted: a total or a 'more' arriving with the answer and being drawn,
    // which is the size of what the reader was not shown.
    const read = readSearch({
      q: "ada",
      total: 47,
      groups: [
        { key: "people", heading: "People", hits: [{ label: "Ada Okafor", sub: "Web", to: "/people/p_ada" }, { label: "x", to: "https://elsewhere" }, { to: "/nope" }] },
        { key: "empty", heading: "Empty", hits: [] },
        { heading: "No key", hits: [{ label: "y", to: "/y" }] },
      ],
    });
    expect(read).toEqual([{ key: "people", heading: "People", hits: [{ label: "Ada Okafor", sub: "Web", to: "/people/p_ada" }] }]);
    expect(readSearch(null)).toEqual([]);
    expect(searchPath("ada & co")).toBe("/console/search?q=ada%20%26%20co");
  });

  test("a query of two characters asks, lists each module's hits with where to open them, and one character asks nothing", async () => {
    // What breaks if this is deleted: a box that asks on every key, or lists hits with nowhere to go.
    const { container, idp } = await consoleWith({
      q: "ad",
      groups: [{ key: "people", heading: "People", hits: [{ label: "Ada Okafor", sub: "Web", to: "/people/p_ada" }] }],
    });
    await typed(container, "a");
    await new Promise((resolve) => setTimeout(resolve, 400));
    expect(idp.urls.some((url) => url.includes("/console/search"))).toBe(false);
    expect(MIN_QUERY).toBe(2);

    await typed(container, "ad");
    await waitFor(() => {
      expect(container.querySelector("[aria-label='Search results']")).not.toBeNull();
    }, { timeout: 3000 });
    expect(idp.urls.some((url) => url.includes("/console/search?q=ad"))).toBe(true);
    expect(container.querySelector("[aria-label='Search results'] a[href='/people/p_ada']")?.textContent).toContain("Ada Okafor");
  });

  test("a search with nothing in it says so in one sentence, whatever the reason", async () => {
    // The sibling: no match and not permitted are one answer, so there is one sentence for both.
    const { container } = await consoleWith({ q: "zz", groups: [] });
    await typed(container, "zz");
    await waitFor(() => {
      expect(container.querySelector("[aria-label='Search results']")?.textContent).toContain(NOTHING_MATCHES);
    }, { timeout: 3000 });
  });
});
