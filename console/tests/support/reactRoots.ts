/**
 * Every React root the suite's own code makes, held until it is unmounted, so one left mounted is
 * found at the end of the test that made it rather than after that test's window is gone.
 *
 * **A root, and not a timer or a request, is what is counted, because it is the only way late work
 * reaches the page.** React drops an update to an unmounted tree, so a fetch or a timer finishing
 * after its test can only draw through a root still mounted. On 2026-09-28 that failed CI twice
 * with every test passing: `src/main.tsx`'s root, mounted by `accent.test.ts` and `startup.test.ts`
 * and never unmounted, committed a sign-in failure after jsdom's window was closed, and React threw
 * "Right-hand side of 'instanceof' is not an object" from `getActiveElementDeep`. Rejected: failing
 * a test that leaves a timer or a pending promise behind. `vitest --detectAsyncLeaks` counted 116
 * across the suite that day, and only the two entry-point tests' could draw anything.
 *
 * **The registry is held on `globalThis`, not in this module.** The mock in `tests/setup.ts` first
 * runs when something imports `react-dom/client`, which in `accent.test.ts` is after
 * `vi.resetModules()`, so its import of this module is a fresh copy: a registry in module scope
 * recorded the entry point's root where the check could not see it (measured by mutation).
 *
 * Roots made by `@testing-library/react` are not recorded: its `cleanup` unmounts them, and it
 * reaches `react-dom/client` without passing through the suite's module mocks.
 */

import type { Root } from "react-dom/client";

export const A_ROOT_IS_UNMOUNTED_BY_THE_TEST_THAT_MOUNTED_IT =
  "A React root was still mounted when its test ended. It has been unmounted, and the test fails " +
  "because work it had started (a fetch, a timer, a sign-in) would otherwise commit after the " +
  "test's window is torn down, which fails a later, unrelated run with every test passing. Unmount " +
  "the root in the test that made it, for example `(await import('../src/main')).root.unmount()` " +
  "in an afterEach.";

const REGISTRY = Symbol.for("brain.console.tests.mountedRoots");

function mounted(): Set<Root> {
  const holder = globalThis as { [REGISTRY]?: Set<Root> };
  holder[REGISTRY] ??= new Set<Root>();
  return holder[REGISTRY];
}

/** Record a root until it is unmounted. Returns the same root, so a factory can wrap in one line. */
export function trackRoot(root: Root): Root {
  const roots = mounted();
  roots.add(root);
  const unmount = root.unmount.bind(root);
  root.unmount = () => {
    roots.delete(root);
    unmount();
  };
  return root;
}

/** The roots recorded and not yet unmounted, in the order they were made. */
export function rootsStillMounted(): readonly Root[] {
  return [...mounted()];
}

/**
 * Unmount every root still mounted, then refuse if there was one. Unmounting first keeps a leak to
 * one failed test: the root cannot commit later and fail a run nobody can attribute.
 */
export function refuseRootsLeftMounted(): void {
  const left = rootsStillMounted();
  for (const root of left) {
    root.unmount();
  }
  if (left.length > 0) {
    throw new Error(`${A_ROOT_IS_UNMOUNTED_BY_THE_TEST_THAT_MOUNTED_IT} (${String(left.length)} left mounted)`);
  }
}
