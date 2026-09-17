/**
 * Whether the window is narrower than the width at which the sidebar stops sitting beside the page.
 *
 * **Read on the first render rather than after it.** shadcn/ui's copy starts at `false` and
 * corrects itself in an effect, so a phone renders the desktop sidebar for one frame, hidden by
 * CSS, and then swaps it for the drawer. The frame is invisible and the markup is not: a test, or a
 * screen reader walking the first render, finds a menu that is about to disappear. Reading the
 * window's width synchronously through `useSyncExternalStore` gives the first render the right
 * answer.
 *
 * **The width, not `matchMedia`.** They agree at every size, and jsdom has the first and not the
 * second, so the tests that hold the sidebar to a phone's width can set the one input this reads.
 *
 * Task ids: M27.10.2
 */

import { useSyncExternalStore } from "react";

/** Tailwind's `md` breakpoint in pixels. The sidebar's `md:` classes switch at the same width. */
export const MOBILE_BREAKPOINT = 768;

function subscribe(onChange: () => void): () => void {
  globalThis.addEventListener("resize", onChange);
  return () => {
    globalThis.removeEventListener("resize", onChange);
  };
}

function narrow(): boolean {
  return globalThis.innerWidth < MOBILE_BREAKPOINT;
}

export function useIsMobile(): boolean {
  return useSyncExternalStore(subscribe, narrow, () => false);
}
