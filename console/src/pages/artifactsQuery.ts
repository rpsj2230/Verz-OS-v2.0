/**
 * What the Artifacts screen asks the API for, what a row is, and what it may narrow by. No React.
 *
 * `brain.artifact_routes` answers, and `brain.console.govern_estate.artifact_estate` has already
 * decided which artifacts this reader may know exist before anything reaches this module. **The
 * search, the kind filter and the order are the route's, sent as parameters** (`brain.listing`,
 * M32.5.2.1), and the rows drawn are its answer to the question asked. They were narrowed in the
 * browser over one whole answer until 2026-10-14, which narrows only what arrived and looks
 * identical to the server's answer, and the whole estate in one body does not page.
 *
 * **An answer carries a list or a sentence, and never both.** Nothing on an install records an
 * artifact today, and `ArtifactsView` then carries no list and a sentence saying why. `readArtifacts`
 * turns that into a value the page cannot mistake for an empty list, which is `installQuery.ts`'
 * `readRecovery` rule and for its reason: an empty table under "artifacts produced" reads as an
 * estate that produced nothing.
 *
 * **No count of anything withheld.** The page may count the rows it holds, which are the reader's
 * own answer. Nothing here subtracts.
 *
 * Task ids: M27.7.23, M32.5.2.1
 */

import type { components } from "../api/schema";
import type { FilterChoice, SortChoice } from "../components/listing";
import { wasRead, type Read } from "./installQuery";

export type ArtifactsView = components["schemas"]["ArtifactsView"];
export type ArtifactRow = components["schemas"]["ArtifactView"];

export const ARTIFACTS_API_PATH = "/govern/artifacts";

/** The rows, or the sentence saying nothing records any. */
export function readArtifacts(payload: ArtifactsView | null): Read<readonly ArtifactRow[]> {
  const rows = payload?.artifacts;
  if (rows === null || rows === undefined) {
    return { unread: payload?.unread ?? "" };
  }
  return { panel: rows };
}

export { wasRead };

/**
 * The filters the artifacts route declares that this screen offers: the kind. The values offered
 * are those on rows already drawn (`listing.ts`' `A_FILTER_OFFERS_ONLY_WHAT_WAS_SHOWN`), so no
 * dropdown names a kind this reader was not shown an artifact of.
 */
export const ARTIFACT_FILTERS: readonly FilterChoice<ArtifactRow>[] = [
  {
    column: "kind",
    label: "Kind",
    everything: "Every kind",
    read: (row) => row.kind,
    describe: kindWords,
  },
];

/** The orders the route declares that a person reads a list of produced things in. */
export const ARTIFACT_SORTS: readonly SortChoice[] = [
  { value: "", label: "Newest first" },
  { value: "produced_at", label: "Oldest first" },
];

/** A kind as a person reads it: `quarterly_report` as "Quarterly report". */
export function kindWords(kind: string): string {
  const words = kind.replace(/_/g, " ").trim();
  return words === "" ? kind : `${words.slice(0, 1).toLocaleUpperCase("en-GB")}${words.slice(1)}`;
}

/** An instant as a row shows it: the reader's own locale and zone, to the minute. */
export function when(value: string): string {
  const parsed = new Date(value);
  if (value === "" || Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** When a row stops being kept, in words: the date and the window, or why there is no date. */
export function keptUntil(row: ArtifactRow): string {
  return row.kept_until === "" ? row.kept_because : `${when(row.kept_until)}, ${row.kept_because}`;
}
