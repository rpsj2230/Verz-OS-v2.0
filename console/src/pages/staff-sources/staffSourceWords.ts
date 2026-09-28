/**
 * The words the Staff sources page draws for values the API sends as keys: a source's name, a
 * run's outcome and a time. No React.
 *
 * A source is named by its guide's own title where the API sent a guide for it, so the vendor's
 * name is the API's and not a second copy here. The two sources with no guide, and an outcome this
 * table does not know yet, fall back to the key with its underscores read as spaces, so a new value
 * still reads as words rather than as nothing.
 *
 * Task ids: M27.7.2, M27.16.1
 */

import type { Guides } from "../staffSourcesQuery";

/** The two sources that have no guide, because neither is connected to anything. */
const WITHOUT_A_GUIDE: Readonly<Record<string, string>> = {
  none: "No staff list",
  spreadsheet: "Uploaded spreadsheet",
};

/** What each scheduled run's outcome reads as. */
const OUTCOMES: Readonly<Record<string, string>> = {
  applied: "Applied",
  unchanged: "No changes",
  misconfigured: "Settings refused",
  no_credential: "No credential",
  credential_refused: "Credential refused",
  unreachable: "Source unreachable",
  not_schedulable: "Not read on a schedule",
};

/** A key read as words: underscores as spaces, the first letter a capital. */
function asWords(key: string): string {
  const spaced = key.replaceAll("_", " ").trim();
  return spaced === "" ? key : `${spaced.slice(0, 1).toLocaleUpperCase("en-GB")}${spaced.slice(1)}`;
}

/** A source's name as a person reads it. */
export function sourceTitle(name: string, guides: Guides | null): string {
  return guides?.guides.find((one) => one.source === name)?.title ?? WITHOUT_A_GUIDE[name] ?? asWords(name);
}

/** A run's outcome as a person reads it. */
export function outcomeWords(outcome: string): string {
  return OUTCOMES[outcome] ?? asWords(outcome);
}

/** A time the API sent, in the console's date style. */
export function when(at: string): string {
  const date = new Date(at);
  return Number.isNaN(date.getTime())
    ? at
    : date.toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
