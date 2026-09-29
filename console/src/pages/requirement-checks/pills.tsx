/**
 * Where a requirement stands and what an acceptance check came to, drawn as the design's `.pill`: the
 * word carries the meaning and the colour repeats it, and a word this console has not heard of is
 * drawn as itself in the plain tone, `ui/Status.tsx`' rule.
 *
 * Task ids: M1.8.8, M27.16.1
 */

import { cn } from "../../lib/utils";
import { EVIDENCE_WORDS, STANDING_WORDS, type Standing } from "../requirementChecksQuery";

const PILL = "inline-block rounded-[2px] px-1.5 py-0.5 font-mono text-[10.5px] font-medium tracking-[0.03em] whitespace-nowrap";

const TONE: Readonly<Record<string, string>> = {
  passed: "bg-ok-wash text-ok",
  failed: "bg-crit-wash text-crit",
  unchecked: "bg-warn-wash text-warn",
  "not run": "bg-sunk text-dim",
};

export function StandingPill({ standing }: { readonly standing: Standing }) {
  return (
    <span data-slot="state-pill" className={cn(PILL, TONE[standing] ?? "bg-sunk text-ink")}>
      {STANDING_WORDS[standing]}
    </span>
  );
}

export function EvidencePill({ outcome }: { readonly outcome: string }) {
  return (
    <span data-slot="state-pill" className={cn(PILL, TONE[outcome] ?? "bg-sunk text-ink")}>
      {EVIDENCE_WORDS[outcome] ?? outcome}
    </span>
  );
}
