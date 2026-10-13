/**
 * A page read from a copy of the database that is behind says so, whichever page it is (M36.1.2.3).
 *
 * The API puts a `staleness` field on every route body that may be read from a replica, and the
 * console used to draw it on two pages and ignore it on the rest. The frame now draws the sentence
 * once above the page, and clears it when the address changes. Mounted through the real route table
 * and shell, signed in, with the stand-in API answering by path from the Spend page case, which
 * carries no staleness of its own: the field is added to its body here, because the frame reads the
 * field and does not care which page sent it.
 *
 * Task ids: M36.1.2.3
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { cleanup, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { COMPANY_CONSOLE, NAVIGATION_ADDRESS } from "./support/navigation";
import { PAGES } from "./support/pageCases";
import { installRadixStubs } from "./support/radix";

beforeAll(() => {
  installRadixStubs();
});

const BEHIND = "This page was read from a copy of the database that is 42 seconds behind. A change made in the last 42 seconds may not be shown yet.";

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json", "x-trace-id": "trace-stale" } });
}

/** The Spend page, its report answered with whatever `staleness` says. */
async function spendWith(staleness: unknown): Promise<Element> {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
  const answers: Record<string, unknown> = { ...(PAGES["/spend"]?.answers ?? {}) };
  const report = answers["/api/v1/report/spend"] as Record<string, unknown>;
  answers["/api/v1/report/spend"] = { ...report, staleness };
  const idp = fakeIdentityProvider({
    api(url) {
      const parsed = new URL(url, "https://console.test");
      if (parsed.pathname === NAVIGATION_ADDRESS) {
        return json(COMPANY_CONSOLE);
      }
      return parsed.pathname in answers ? json(answers[parsed.pathname]) : null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: ["/spend"] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    expect(container.querySelector("[data-slot='report-page']")).not.toBeNull();
  });
  return container;
}

describe("the frame's line about a copy that is behind", () => {
  test("a page whose body says its copy is behind is given the sentence once, above the page", async () => {
    // What breaks if this is deleted: a page read from a replica a minute behind says nothing, and
    // a person acts on a figure that is not current.
    const page = await spendWith({ behind_seconds: 42, message: BEHIND });
    await waitFor(() => {
      expect(page.querySelector("[data-slot='staleness-banner']")?.textContent).toBe(BEHIND);
    });
    expect(page.textContent?.split(BEHIND).length).toBe(2);
  });

  test("a page read from the primary carries no banner and none is drawn", async () => {
    // What breaks if this is deleted: a banner on a current page teaches people to ignore the one
    // that matters.
    const page = await spendWith(null);
    await waitFor(() => {
      expect(page.querySelector("[data-slot='report-page']")).not.toBeNull();
    });
    expect(page.querySelector("[data-slot='staleness-banner']")).toBeNull();
  });
});
