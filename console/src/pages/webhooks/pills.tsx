/**
 * A subscriber's state and a delivery's state as the design draws a `.pill`: the word carries the
 * meaning and the colour repeats it, and a word this console has not heard of is drawn as itself in
 * the plain tone, `ui/Status.tsx`' rule. Every word is a fact about the subscriber or the delivery,
 * the same for every reader shown it.
 *
 * Task ids: M27.8.12, M27.16.1
 */

import { cn } from "../../lib/utils";
import { DELIVERY_STATE_WORDS } from "../webhooksQuery";

const PILL = "inline-block rounded-[2px] px-1.5 py-0.5 font-mono text-[10.5px] font-medium tracking-[0.03em]";

const DELIVERY_TONE: Readonly<Record<string, string>> = {
  pending: "bg-sunk text-dim",
  delivered: "bg-ok-wash text-ok",
  exhausted: "bg-crit-wash text-crit",
};

export const ON_WORD = "On";
export const OFF_WORD = "Off";

export function SubscriberPill({ active }: { readonly active: boolean }) {
  return (
    <span data-slot="state-pill" className={cn(PILL, active ? "bg-ok-wash text-ok" : "bg-sunk text-dim")}>
      {active ? ON_WORD : OFF_WORD}
    </span>
  );
}

export function DeliveryPill({ state }: { readonly state: string }) {
  return (
    <span data-slot="state-pill" className={cn(PILL, DELIVERY_TONE[state] ?? "bg-sunk text-ink")}>
      {DELIVERY_STATE_WORDS[state] ?? state}
    </span>
  );
}
