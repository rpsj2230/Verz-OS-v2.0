/**
 * A source's status and health, and the mark for a declaration that changed, as the design draws a
 * `.pill`: the word carries the meaning and the colour repeats it, and a word this console has not
 * heard of is drawn as itself in the plain tone, `ui/Status.tsx`' rule.
 *
 * Task ids: M27.11.9
 */

import { cn } from "../../lib/utils";
import { healthWords, statusWords } from "./connectorSources";

const STATUS_TONE: Readonly<Record<string, string>> = {
  connected: "bg-ok-wash text-ok",
  failing: "bg-crit-wash text-crit",
  not_connected: "bg-sunk text-dim",
};

const HEALTH_TONE: Readonly<Record<string, string>> = {
  ok: "text-ok [&>i]:bg-ok",
  degraded: "text-warn [&>i]:bg-warn",
  down: "text-crit [&>i]:bg-crit",
  unconfigured: "text-dim [&>i]:bg-dim",
};

/** What the mark over a changed declaration says. */
export const DECLARATION_CHANGED_WORDS = "Declaration changed";

const PILL = "inline-block rounded-[2px] px-1.5 py-0.5 font-mono text-[10.5px] font-medium tracking-[0.03em]";

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
      {healthWords(health)}
    </span>
  );
}

export function DriftPill() {
  return <span className={cn(PILL, "bg-warn-wash text-warn")}>{DECLARATION_CHANGED_WORDS}</span>;
}
