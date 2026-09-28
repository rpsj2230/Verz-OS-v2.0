/**
 * The suite's guard against a React root that outlives its test: it sees a root the suite's own
 * code makes, unmounts and refuses one left mounted, and is called by the suite on every test. The
 * console's entry point, the path that failed CI twice on 2026-09-28, is held separately in
 * `react-roots-entry.test.ts`. Why a root is what is counted is in `tests/support/reactRoots.ts`.
 */

import { createElement } from "react";
import { flushSync } from "react-dom";
import { createRoot } from "react-dom/client";
import { afterAll, describe, expect, test } from "vitest";
import {
  A_ROOT_IS_UNMOUNTED_BY_THE_TEST_THAT_MOUNTED_IT,
  refuseRootsLeftMounted,
  rootsStillMounted,
} from "./support/reactRoots";

function drawnRoot(): { readonly root: ReturnType<typeof createRoot>; readonly container: HTMLElement } {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  flushSync(() => {
    root.render(createElement("p", null, "drawn"));
  });
  return { root, container };
}

describe("a React root outliving its test", () => {
  test("a root made outside the testing library is counted until it is unmounted", () => {
    // What breaks if this is deleted: the guard going blind without a sound. If the mock in
    // tests/setup.ts stopped applying, every root would be uncounted, the guard would pass
    // everything, and a leaked root would go back to failing CI at random with every test green.
    const { root, container } = drawnRoot();
    expect(container.textContent).toBe("drawn");
    expect(rootsStillMounted()).toEqual([root]);

    root.unmount();

    expect(rootsStillMounted()).toEqual([]);
    expect(() => {
      refuseRootsLeftMounted();
    }).not.toThrow();
  });

  test("a root left mounted is unmounted before the test is refused", () => {
    // What breaks if this is deleted: a guard that refused without unmounting would still leave the
    // root to commit after the window is torn down, so the leak would fail this test and then fail
    // an unrelated file's run as well, which is the report nobody can trace.
    const { root, container } = drawnRoot();

    expect(() => {
      refuseRootsLeftMounted();
    }).toThrow(A_ROOT_IS_UNMOUNTED_BY_THE_TEST_THAT_MOUNTED_IT);

    expect(rootsStillMounted()).toEqual([]);
    expect(container.textContent).toBe("");
    expect(() => {
      root.render(createElement("p", null, "again"));
    }).toThrow(/unmounted root/);
  });
});

describe("a test that leaves a root mounted", () => {
  // What the test below failed with, read before `test.fails` flips its result. Checked in afterAll
  // so the check does not depend on test order.
  let refusedWith: readonly string[] | null = null;

  afterAll(() => {
    if (refusedWith !== null) {
      expect(refusedWith).toEqual([expect.stringContaining(A_ROOT_IS_UNMOUNTED_BY_THE_TEST_THAT_MOUNTED_IT)]);
    }
  });

  test.fails("fails through the suite's own afterEach, and through nothing else", ({ onTestFailed }) => {
    // What breaks if this is deleted: the call in tests/setup.ts being removed, or moved ahead of the
    // test files' own hooks. Every test above calls the guard by hand, so only this one proves the
    // suite calls it, and the afterAll proves the failure was the refusal and not this body.
    onTestFailed(({ task }) => {
      refusedWith = (task.result?.errors ?? []).map((error) => String(error.message));
    });
    drawnRoot();
    expect(rootsStillMounted()).toHaveLength(1);
  });
});
