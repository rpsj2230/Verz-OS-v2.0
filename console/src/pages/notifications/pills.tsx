/**
 * A notice's switch, whether anything sends it yet, and a subscriber's state, as the design draws a
 * `.pill`: the word carries the meaning and the colour repeats it. Each is a fact about the notice
 * or the subscriber, the same for every reader shown it.
 *
 * Task ids: M27.8.11, M27.16.1
 */

import { cn } from "../../lib/utils";

const PILL = "inline-block w-fit rounded-[2px] px-1.5 py-0.5 font-mono text-[10.5px] font-medium tracking-[0.03em]";

export function NoticePill({ on }: { readonly on: boolean }) {
  return (
    <span data-slot="state-pill" className={cn(PILL, on ? "bg-ok-wash text-ok" : "bg-warn-wash text-warn")}>
      {on ? "On" : "Off"}
    </span>
  );
}

export function SentPill({ sent }: { readonly sent: boolean }) {
  return (
    <span data-slot="state-pill" className={cn(PILL, sent ? "bg-ok-wash text-ok" : "bg-sunk text-dim")}>
      {sent ? "Sent" : "Not sent yet"}
    </span>
  );
}
