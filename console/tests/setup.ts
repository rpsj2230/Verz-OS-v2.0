/**
 * What every test file starts from, and why it has to be reset rather than assumed.
 *
 * Three things in this console live outside React and therefore outside a component's
 * lifetime: the theme's attribute on the root element, the two browser stores, and the
 * modules that hold a session or a discovery promise in a module-level variable. The first
 * two are reset here. The third cannot be reset from outside, so the tests that touch it
 * call `vi.resetModules()` and import again; see `tests/support/auth.ts`.
 *
 * Automatic cleanup from `@testing-library/react` only registers itself when the test
 * globals are present, and this project runs with `globals: false` so that every helper a
 * test uses is imported where a reader can see it. The `cleanup` call below is the price
 * of that and is not optional: without it every render stays in the document, and a test
 * that asserts on "the navigation" finds three of them.
 *
 * **`ResizeObserver` is defined here because jsdom does not have one.** React Flow measures
 * every node it renders and constructs an observer on mount, so without this the graph
 * throws before it draws anything. The stub observes nothing and reports nothing, which is
 * the honest shape: jsdom has no layout to observe, and a stub that invented a size would
 * make a test believe it had measured a rendered graph. What that leaves unchecked is
 * written down in `console/README.md`: this suite reads which nodes and edges reach the
 * DOM, and never where they are on a screen.
 *
 * **A root the suite's own code makes has to be unmounted by the test that made it.** The mock
 * below records each one and the last `afterEach` refuses one left mounted; the argument, and the
 * two CI failures of 2026-09-28 it answers, are in `tests/support/reactRoots.ts`.
 */

import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import { refuseRootsLeftMounted } from "./support/reactRoots";

vi.mock("react-dom/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-dom/client")>();
  const { trackRoot } = await import("./support/reactRoots");
  const createRoot: typeof actual.createRoot = (...args) => trackRoot(actual.createRoot(...args));
  const hydrateRoot: typeof actual.hydrateRoot = (...args) => trackRoot(actual.hydrateRoot(...args));
  return { ...actual, createRoot, hydrateRoot, default: { ...actual, createRoot, hydrateRoot } };
});

if (!("ResizeObserver" in globalThis)) {
  globalThis.ResizeObserver = class {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  } as unknown as typeof ResizeObserver;
}

afterEach(() => {
  cleanup();
  document.documentElement.removeAttribute("data-theme");
  try {
    localStorage.clear();
    sessionStorage.clear();
  } catch {
    // A store that refuses to be read is a state the console handles; it is not a state a
    // test needs to reproduce here.
  }
  // Last, so a refusal skips no reset above. It runs after the test file's own afterEach hooks,
  // so a test that unmounts what it started there passes.
  refuseRootsLeftMounted();
});
