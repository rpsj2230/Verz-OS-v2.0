/**
 * A version's review state and its retirement, as pills in the design of record's `.pill` shape.
 *
 * The word carries the meaning and the colour repeats it, as `agents/pills.tsx` draws an agent's
 * state, so the pill reads the same to somebody who cannot tell the colours apart. A word this
 * console has not heard of is drawn as itself in the plain tone: inventing a meaning for an unknown
 * state is the guess that fails in the wrong direction.
 *
 * Task ids: M27.16.1
 */

import { cn } from "../../lib/utils";
import { RETIRED_WORD, reviewPill } from "./skillActions";

const REVIEW_TONE: Readonly<Record<string, string>> = {
  pending: "bg-warn-wash text-warn",
  approved: "bg-ok-wash text-ok",
  rejected: "bg-sunk text-dim",
  changed: "bg-crit-wash text-crit",
};

const PILL = "inline-block rounded-[2px] px-1.5 py-0.5 font-mono text-[10.5px] font-medium tracking-[0.03em] whitespace-nowrap";

export function ReviewPill({ review }: { readonly review: string }) {
  return (
    <span data-slot="review-pill" className={cn(PILL, REVIEW_TONE[review] ?? "bg-sunk text-ink")}>
      {reviewPill(review)}
    </span>
  );
}

export function RetiredPill() {
  return (
    <span data-slot="retired-pill" className={cn(PILL, "border border-dashed border-line bg-transparent text-dim")}>
      {RETIRED_WORD}
    </span>
  );
}
