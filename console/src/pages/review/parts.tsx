/**
 * The small parts the Governance pages share: a state pill, a person's name out of an answer's
 * `people`, and the words for a moment and for a lapse.
 *
 * **A person is drawn by the name the answer carried, never by their id.** Each Governance answer
 * sends the names of the people on its own rows (`brain.people_names`); a person it has no name
 * for is drawn as an account with no name, and their id is on the row's own page, in Advanced.
 *
 * **A pill's word carries the meaning and its colour repeats it**, as the design of record's `.pill`
 * does, so it reads the same to somebody who cannot tell the colours apart. The tone is chosen by
 * the caller from a closed list, never computed from a value this console has not heard of.
 *
 * Task ids: M27.16.1
 */

import type { ReactNode } from "react";
import { cn } from "../../lib/utils";

/** What a person the answer carried no name for reads as. */
export const NO_NAME = "An account with no name";

/** A person's name: the one sent with the row, then the answer's `people`, then the fallback. */
export function nameOf(
  people: Readonly<Record<string, string>>,
  principalId: string | null | undefined,
  known?: string | null,
): string {
  if (known !== undefined && known !== null && known !== "") {
    return known;
  }
  if (principalId === undefined || principalId === null || principalId === "") {
    return "";
  }
  return people[principalId] ?? NO_NAME;
}

export type Tone = "ok" | "warn" | "crit" | "plain" | "brand";

const PILL = "inline-block rounded-[2px] px-1.5 py-0.5 font-mono text-[10.5px] font-medium tracking-[0.03em] whitespace-nowrap";

/** A state's word in a pill whose colour repeats it. */
export function Pill({ tone, children }: { readonly tone: Tone; readonly children: ReactNode }) {
  return (
    <span
      data-slot="state-pill"
      className={cn(
        PILL,
        tone === "ok" && "bg-ok-wash text-ok",
        tone === "warn" && "bg-warn-wash text-warn",
        tone === "crit" && "bg-crit-wash text-crit",
        tone === "plain" && "bg-sunk text-body",
        tone === "brand" && "bg-acc-wash text-acc-text",
      )}
    >
      {children}
    </span>
  );
}

/** An instant as a person reads it, to the minute, in their own zone. Empty for none. */
export function whenWords(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "";
  }
  const at = new Date(value);
  if (Number.isNaN(at.getTime())) {
    return value;
  }
  return at.toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** A map of names from a body that may not carry one, keeping only string values. */
export function peopleIn(payload: unknown): Readonly<Record<string, string>> {
  if (typeof payload !== "object" || payload === null) {
    return {};
  }
  const found = (payload as { people?: unknown }).people;
  if (typeof found !== "object" || found === null || Array.isArray(found)) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(found as Record<string, unknown>).filter((entry): entry is [string, string] => typeof entry[1] === "string"),
  );
}

/** A link-styled text class, for a name or a thing that opens its own page. */
export const LINK = "font-medium text-ink underline-offset-4 hover:text-acc-text hover:underline";
