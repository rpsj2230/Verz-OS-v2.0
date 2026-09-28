/**
 * A channel's status and health as the design draws a `.pill`: the word carries the meaning and the
 * colour repeats it, and a word this console has not heard of is drawn as itself in the plain tone,
 * `ui/Status.tsx`' rule. No colour here depends on who is reading: each word is a fact about the
 * channel's record or its deliveries, the same for every reader shown it.
 *
 * Task ids: M27.13.1, M27.16.1
 */

import { cn } from "../../lib/utils";
import { healthWord } from "../channelsQuery";
import { statusWords } from "./channelRows";

const PILL = "inline-block rounded-[2px] px-1.5 py-0.5 font-mono text-[10.5px] font-medium tracking-[0.03em]";

const STATUS_TONE: Readonly<Record<string, string>> = {
  on: "bg-ok-wash text-ok",
  off: "bg-warn-wash text-warn",
  not_set_up: "bg-sunk text-dim",
};

const HEALTH_TONE: Readonly<Record<string, string>> = {
  working: "text-ok [&>i]:bg-ok",
  quiet: "text-dim [&>i]:bg-dim",
  failing: "text-crit [&>i]:bg-crit",
  switched_off: "text-warn [&>i]:bg-warn",
  not_set_up: "text-dim [&>i]:bg-dim",
};

export function StatusPill({ status }: { readonly status: string }) {
  return (
    <span data-slot="status-pill" className={cn(PILL, STATUS_TONE[status] ?? "bg-sunk text-ink")}>
      {statusWords(status)}
    </span>
  );
}

/** A health word: a dot and the word. */
export function HealthPill({ health }: { readonly health: string }) {
  return (
    <span
      data-slot="health-pill"
      className={cn("inline-flex items-center gap-1.5 font-mono text-[11px] font-semibold", HEALTH_TONE[health] ?? "text-ink")}
    >
      <i aria-hidden className="block size-[7px] rounded-full" />
      {healthWord(health)}
    </span>
  );
}
