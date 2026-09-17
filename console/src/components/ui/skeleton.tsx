/**
 * A placeholder shape for something still arriving.
 *
 * Copied from shadcn/ui's Radix "vega" style at CLI 4.21.0 through the design spike.
 *
 * **Hidden from assistive technology, and never the only sign of loading.** A pulsing grey box says
 * nothing to a screen reader, and `tests/screen-states.test.tsx` holds every page to a loading
 * sentence of its own, so a skeleton is decoration beside that sentence and is marked as such.
 * **It is also never a count.** A list that is loading shows a fixed number of placeholder rows, not
 * one per row the server is about to send, because a row count a reader has not been given is the
 * number `CLAUDE.md` says is never emitted.
 *
 * Task ids: M27.10.2
 */

import type { ComponentProps } from "react";
import { cn } from "../../lib/utils";

function Skeleton({ className, ...props }: ComponentProps<"div">) {
  return <div data-slot="skeleton" aria-hidden="true" className={cn("animate-pulse rounded-md bg-muted", className)} {...props} />;
}

export { Skeleton };
