/**
 * An automation's state as the design draws a `.pill`: the word carries the meaning and the colour
 * repeats it, and a word this console has not heard of is drawn as itself in the plain tone.
 *
 * Task ids: M27.12.3
 */

import { cn } from "../../lib/utils";
import { stateWords } from "./automationsQuery";

const TONE: Readonly<Record<string, string>> = {
  running: "bg-ok-wash text-ok",
  paused: "bg-sunk text-dim",
  ownerless: "bg-warn-wash text-warn",
  removed: "bg-crit-wash text-crit",
};

const PILL = "inline-block rounded-[2px] px-1.5 py-0.5 font-mono text-[10.5px] font-medium tracking-[0.03em]";

export function StatePill({ state }: { readonly state: string }) {
  return (
    <span data-slot="state-pill" className={cn(PILL, TONE[state] ?? "bg-sunk text-ink")}>
      {stateWords(state)}
    </span>
  );
}
