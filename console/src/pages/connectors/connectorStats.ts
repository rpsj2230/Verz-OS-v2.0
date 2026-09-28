/**
 * A source's figures: a small typed client over the stats route every module shares.
 *
 * **`GET /api/v1/console/connectors/{name}/stats`, served by `brain.console_stats_routes`** (the
 * stats package, PR #148). Its answer is `ConnectorStatsView`: the worker's newest health word,
 * when it last attempted the source and last read it to the end, the failures in a row, how many
 * ids of it this install keeps that the reader's own row scope admits (`index_ids`, never a value),
 * one set of attempt figures per period, and `unrecorded`, the figures nothing on the install
 * records, each with its reason.
 *
 * **A figure nothing sent is "Not recorded yet", never nought.** `index_ids` is null when the
 * source's manifest cannot be built today, and a period's figure the route left out is absent here,
 * so the page draws the sentence. See `kit/KpiStrip.tsx`.
 *
 * **The index size is ids and nothing else.** It is a count of what this install keeps of a source
 * the reader may read, which is the minimal index the owner's rule allows, and never a count of
 * what the reader was not shown: the route counts under the reader's own scope.
 *
 * Task ids: M27.11.9, M27.16.1
 */

import { statsApiPath } from "../agents/agentStats";

/** The module name the stats route answers connectors under. */
export const CONNECTORS_MODULE = "connectors";

/** The period the page shows first. */
export const FIRST_PERIOD = "30d";

export function connectorStatsApiPath(name: string): string {
  return statsApiPath(CONNECTORS_MODULE, name);
}

/** One period's attempts on a source. A figure is absent when none was sent. */
export interface ConnectorPeriod {
  readonly range: string;
  readonly attempts?: number;
  readonly readToTheEnd?: number;
  readonly failures?: number;
  readonly quotaWaits?: number;
}

export interface Unrecorded {
  readonly figure: string;
  readonly why: string;
}

/** One source's figures as this console holds them. */
export interface ConnectorStats {
  readonly health?: string;
  readonly lastAttempt?: string;
  readonly lastReadToTheEnd?: string;
  readonly consecutiveFailures?: number;
  /** The ids this install keeps of the source that the reader's own scope admits. */
  readonly indexIds?: number;
  readonly truncated: boolean;
  readonly periods: readonly ConnectorPeriod[];
  readonly unrecorded: readonly Unrecorded[];
}

type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(value: unknown): Fields | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  // A cast at the boundary: every field is read back through `counted`, `said` or `instant`.
  return value as Fields;
}

function counted(value: unknown): number | undefined {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : undefined;
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function instant(value: unknown): string | undefined {
  const text = said(value);
  return text !== undefined && !Number.isNaN(Date.parse(text)) ? text : undefined;
}

function listOf(value: unknown): readonly unknown[] {
  return Array.isArray(value) ? (value as readonly unknown[]) : [];
}

function readPeriod(value: unknown): ConnectorPeriod | null {
  const fields = fieldsOf(value);
  const range = said(fields?.["range"]);
  if (fields === null || range === undefined) {
    return null;
  }
  const attempts = counted(fields["attempts"]);
  const readToTheEnd = counted(fields["read_to_the_end"]);
  const failures = counted(fields["failures"]);
  const quotaWaits = counted(fields["quota_waits"]);
  return {
    range,
    ...(attempts === undefined ? {} : { attempts }),
    ...(readToTheEnd === undefined ? {} : { readToTheEnd }),
    ...(failures === undefined ? {} : { failures }),
    ...(quotaWaits === undefined ? {} : { quotaWaits }),
  };
}

/** The figures out of a body, or null when the body is not an object at all. */
export function readConnectorStats(payload: unknown): ConnectorStats | null {
  const fields = fieldsOf(payload);
  if (fields === null) {
    return null;
  }
  const seen = new Set<string>();
  const periods: ConnectorPeriod[] = [];
  for (const one of listOf(fields["periods"])) {
    const period = readPeriod(one);
    if (period !== null && !seen.has(period.range)) {
      seen.add(period.range);
      periods.push(period);
    }
  }
  const unrecorded: Unrecorded[] = [];
  for (const one of listOf(fields["unrecorded"])) {
    const figure = said(fieldsOf(one)?.["figure"]);
    const why = said(fieldsOf(one)?.["why"]);
    if (figure !== undefined && why !== undefined) {
      unrecorded.push({ figure, why });
    }
  }
  const health = said(fields["health"]);
  const lastAttempt = instant(fields["last_attempt"]);
  const lastReadToTheEnd = instant(fields["last_read_to_the_end"]);
  const consecutiveFailures = counted(fields["consecutive_failures"]);
  const indexIds = counted(fields["index_ids"]);
  return {
    ...(health === undefined ? {} : { health }),
    ...(lastAttempt === undefined ? {} : { lastAttempt }),
    ...(lastReadToTheEnd === undefined ? {} : { lastReadToTheEnd }),
    ...(consecutiveFailures === undefined ? {} : { consecutiveFailures }),
    ...(indexIds === undefined ? {} : { indexIds }),
    truncated: fields["truncated"] === true,
    periods,
    unrecorded,
  };
}

/** One period's figures, or the first sent when that period was not. */
export function connectorPeriodOf(stats: ConnectorStats | null, range: string): ConnectorPeriod | undefined {
  return stats?.periods.find((one) => one.range === range) ?? stats?.periods[0];
}

/** An index size as a page draws it: ids, grouped for reading. */
export function idsWords(value: number | undefined): string | undefined {
  return value === undefined ? undefined : `${value.toLocaleString("en-GB")} ids`;
}
