/**
 * The root guard on the path that failed CI twice on 2026-09-28: the console's entry point imported
 * after `vi.resetModules()`, by a file that has imported nothing from `react-dom/client` before.
 *
 * **A file of its own, because the shape is the test.** The suite's mock first runs when something
 * imports `react-dom/client`, and in `accent.test.ts` that is after the reset. A file that imports it
 * at the top, as `react-roots.test.tsx` does, has run the mock already, and a registry that did not
 * survive the reset passed there while missing the entry point here (measured by mutation).
 */

import { afterEach, expect, test, vi } from "vitest";
import { fakeIdentityProvider, ISSUER, stubLocation, stubServedConfig } from "./support/auth";
import { rootsStillMounted } from "./support/reactRoots";

let started: typeof import("../src/main") | null = null;

afterEach(() => {
  started?.root.unmount();
  started = null;
  document.body.innerHTML = "";
});

test("the console's entry point is counted when imported after a module reset", async () => {
  // What breaks if this is deleted: the guard counting nothing on the one path that has leaked. The
  // two tests that mount the entry point would then pass without unmounting it, and the sign-in it
  // starts would go back to failing a run after its window is gone, with every test passing.
  vi.resetModules();
  stubServedConfig({ issuer: ISSUER });
  stubLocation("/");
  vi.stubGlobal("fetch", fakeIdentityProvider().fetch);
  document.body.innerHTML = '<div id="root"></div>';

  started = await import("../src/main");

  expect(rootsStillMounted()).toEqual([started.root]);
  started.root.unmount();
  expect(rootsStillMounted()).toEqual([]);
});
