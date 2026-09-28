/**
 * An agent's lifecycle word and its leash rung, as the design of record draws them.
 *
 * `docs/screens.html`' `.pill` and `.rung`: the word carries the meaning and the colour repeats it,
 * so the pill reads the same to somebody who cannot tell the colours apart, and state colours are
 * held apart from the company's accent. A word this console has not heard of is drawn as itself in
 * the plain tone, which is `ui/Status.tsx`' rule: inventing a meaning for an unknown state is the
 * guess that fails in the wrong direction.
 *
 * Task ids: M27.10.2
 */

import { cn } from "../../lib/utils";
import { rungWords, stateWords } from "./agentActions";

const STATE_TONE: Readonly<Record<string, string>> = {
  enabled: "bg-ok-wash text-ok",
  disabled: "bg-sunk text-dim",
  archived: "bg-sunk text-dim",
};

const RUNG_TONE: Readonly<Record<string, string>> = {
  shadow: "text-dim [&>i]:bg-dim",
  assisted: "text-warn [&>i]:bg-warn",
  autonomous: "text-ok [&>i]:bg-ok",
};

export function StatePill({ state }: { readonly state: string }) {
  return (
    <span
      data-slot="state-pill"
      className={cn(
        "inline-block rounded-[2px] px-1.5 py-0.5 font-mono text-[10.5px] font-medium tracking-[0.03em]",
        STATE_TONE[state] ?? "bg-sunk text-ink",
      )}
    >
      {stateWords(state)}
    </span>
  );
}

/** A rung: a dot and a word. `upTo` says it is the highest any action reaches. */
export function LeashPill({ rung, upTo = false }: { readonly rung: string; readonly upTo?: boolean }) {
  const word = (
    <span className={cn("inline-flex items-center gap-1.5 font-mono text-[11px] font-semibold", RUNG_TONE[rung] ?? "text-ink")}>
      <i aria-hidden className="block size-[7px] rounded-full" />
      {rungWords(rung)}
    </span>
  );
  return upTo ? (
    <span data-slot="leash-pill" className="inline-flex items-center gap-1.5 rounded-full border border-line px-2 py-0.5">
      <span className="font-mono text-[10.5px] text-dim">leash up to</span>
      {word}
    </span>
  ) : (
    <span data-slot="leash-pill">{word}</span>
  );
}
