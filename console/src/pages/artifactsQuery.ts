/**
 * What the Artifacts screen asks the API for, what a row is, and how the rows it holds are
 * narrowed. No React.
 *
 * `brain.artifact_routes` answers, and `brain.console.govern_estate.artifact_estate` has already
 * decided which artifacts this reader may know exist before anything reaches this module. So the
 * search, the kind filter and the order below act on the rows the page holds and on nothing else,
 * and the page says so beside them.
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
 * Task ids: none
 */

import type { components } from "../api/schema";
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

/** The two orders a person reads a list of produced things in. */
export const ORDERS = ["newest", "oldest"] as const;
export type Order = (typeof ORDERS)[number];
export const ORDER_LABELS: Readonly<Record<Order, string>> = {
  newest: "Newest first",
  oldest: "Oldest first",
};

export interface ArtifactFilters {
  /** Matched against the artifact, the agent and the person it was produced for. */
  readonly search: string;
  /** One kind, or empty for every kind the page holds. */
  readonly kind: string;
  readonly order: Order;
}

export const NO_ARTIFACT_FILTERS: ArtifactFilters = { search: "", kind: "", order: "newest" };

/** The kinds the page holds, so the filter never offers a kind nothing on the page is. */
export function offeredKinds(rows: readonly ArtifactRow[]): readonly string[] {
  return [...new Set(rows.map((one) => one.kind))].sort();
}

/** The rows the page holds that match, in the order asked for. */
export function narrowed(
  rows: readonly ArtifactRow[],
  filters: ArtifactFilters,
): readonly ArtifactRow[] {
  const needle = filters.search.trim().toLowerCase();
  const kept = rows.filter(
    (one) =>
      (filters.kind === "" || one.kind === filters.kind) &&
      (needle === "" ||
        [one.artifact_id, one.agent_id, one.produced_for].some((value) =>
          value.toLowerCase().includes(needle),
        )),
  );
  const sorted = [...kept].sort((a, b) =>
    a.produced_at === b.produced_at
      ? a.artifact_id.localeCompare(b.artifact_id)
      : a.produced_at.localeCompare(b.produced_at),
  );
  return filters.order === "oldest" ? sorted : sorted.reverse();
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
