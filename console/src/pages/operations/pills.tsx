/**
 * Every state word on the Operations pages as the design draws a `.pill`, and the one table per
 * word that says which colour repeats it.
 *
 * **One module decides what can make something amber or red here**, which is
 * `tests/status-primitives.test.tsx`' rule applied the way `agents/pills.tsx` and
 * `connectors/pills.tsx` apply it: a page hands over the API's own word and the pill looks it up,
 * so a reviewer asking what colours a row reads these tables and nothing else. The word carries the
 * meaning and the colour repeats it, and a word this console has not heard of is drawn as itself in
 * the plain tone, `ui/Status.tsx`' rule: inventing a meaning for an unknown state is the guess that
 * fails in the wrong direction. **No colour here depends on who is reading**: every word is a fact
 * about the job, the run, the log row or the bucket, the same for every reader who is shown it.
 *
 * Task ids: M27.16.1, M27.10.2
 */

import type { ReactNode } from "react";
import { cn } from "../../lib/utils";
import { outcomeWords, stateWords, type JobRow } from "../jobsQuery";
import { LEVEL_LABELS, type Level } from "../logsQuery";

type Shade = "ok" | "warn" | "crit" | "plain";

const SHADES: Readonly<Record<Shade, string>> = {
  ok: "bg-ok-wash text-ok",
  warn: "bg-warn-wash text-warn",
  crit: "bg-crit-wash text-crit",
  plain: "bg-sunk text-dim",
};

const PILL = "inline-block rounded-[2px] px-1.5 py-0.5 font-mono text-[10.5px] font-medium tracking-[0.03em]";

function shaded(shade: Shade, children: ReactNode, key?: string) {
  return (
    <span key={key} data-slot="state-pill" className={cn(PILL, SHADES[shade])}>
      {children}
    </span>
  );
}

/** A word in the plain tone, for a fact with no better or worse reading. */
export function Pill({ children }: { readonly children: ReactNode }) {
  return shaded("plain", children);
}

/** A job's state words, paused first because it is the one a person did. */
export function JobStatePills({ row }: { readonly row: JobRow }) {
  return <span className="flex flex-wrap gap-1">{stateWords(row).map((one) => shaded(one.tone, one.word, one.word))}</span>;
}

const OUTCOME_SHADE: Readonly<Record<string, Shade>> = { ok: "ok", failed: "crit", refused: "plain", unfinished: "warn" };

export function OutcomePill({ outcome }: { readonly outcome: string }) {
  return shaded(OUTCOME_SHADE[outcome] ?? "plain", outcomeWords(outcome));
}

/** Whether a run acts or only reports. */
export function ModePill({ reportOnly, acting, reporting }: { readonly reportOnly: boolean; readonly acting: string; readonly reporting: string }) {
  return shaded(reportOnly ? "plain" : "ok", reportOnly ? reporting : acting);
}

const REQUEST_SHADE: Readonly<Record<string, Shade>> = { failed: "crit", degraded: "warn" };

export function RequestPill({ status, words }: { readonly status: string; readonly words: string }) {
  return shaded(REQUEST_SHADE[status] ?? "plain", words);
}

const LEVEL_SHADE: Readonly<Record<string, Shade>> = { critical: "crit", error: "crit", warning: "warn", info: "plain" };

export function LevelPill({ level }: { readonly level: string }) {
  return shaded(LEVEL_SHADE[level] ?? "plain", LEVEL_LABELS[level as Level] ?? level);
}

const BAND_SHADE: Readonly<Record<string, Shade>> = { notable: "warn", extreme: "crit" };

export function BandPill({ band }: { readonly band: string }) {
  return shaded(BAND_SHADE[band] ?? "plain", band);
}

/** Whether a data set can be moved today. */
export function AvailablePill({ runs }: { readonly runs: boolean }) {
  return shaded(runs ? "ok" : "plain", runs ? "Available" : "Not yet");
}

/** A bucket anybody can read without signing in, which is worth a second look. */
export function PublicPill({ open }: { readonly open: boolean }) {
  return shaded(open ? "warn" : "plain", open ? "Yes" : "No");
}
