/**
 * A source's figures: a small typed client over the stats route every module shares.
 *
 * **`GET /api/v1/console/connectors/{name}/stats`, served by `brain.console_stats_routes`** (the
 * stats package, PR #148). Its answer is `ConnectorStatsView`: the worker's newest health word,
 * when it last attempted the source and last read it to the end, the failures in a row, how many
 * ids of it this install keeps that the reader's own row scope admits (`index_ids`, never a value),
 * one set of attempt figures per period with the questions that read the source live
 * (`live_reads`), whose questions those are (`live_read_basis`, `own` or `everyone`), the newest of
 * them (`last_live_read`), and `unrecorded`, the figures nothing on the install records, each with
 * its reason.
 *
 * **A figure nothing sent is "Not recorded yet", never nought.** `index_ids` is null when the
 * source's manifest cannot be built today, and a period's figure the route left out is absent here,
 * so the page draws the sentence. See `kit/KpiStrip.tsx`. `last_live_read` sent as null is a
 * different fact, no live read in the longest period, and is kept apart as `null`.
 *
 * **The index size is ids and nothing else.** It is a count of what this install keeps of a source
 * the reader may read, which is the minimal index the owner's rule allows, and never a count of
 * what the reader was not shown: the route counts under the reader's own scope.
 *
 * **The calls questions made to the source are the live reader's own figures** (`calls`, M11.3.4):
 * requests a second and a minute, those in flight, the shares refused as over the source's limit and
 * failed, and the latency. They are everybody's questions' calls on this application process, so a
 * reader who may see only their own usage is sent none and `callsTold` says why, which is drawn.
 *
 * Task ids: M27.11.9, M27.16.1, M11.3.4
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
  /** The questions that read the source live in this period, at `liveReadBasis`. */
  readonly liveReads?: number;
}

/** The calls questions made to the source on this process, over the route's window. */
export interface ConnectorCalls {
  readonly windowSeconds: number;
  readonly requests: number;
  readonly perSecond: number;
  readonly perMinute: number;
  readonly concurrency: number;
  readonly quotaRatio: number;
  readonly errorRatio: number;
  readonly latencyP50Ms: number;
  readonly latencyP95Ms: number;
  readonly quiet: boolean;
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
  /** Whose questions the live reads are: `own` or `everyone`. */
  readonly liveReadBasis?: string;
  /** The newest live read in the longest period; null when the route said there was none. */
  readonly lastLiveRead?: string | null;
  /** The attempts or the live reads were read to their bound, so the figures are at least these. */
  readonly atLeast: boolean;
  readonly periods: readonly ConnectorPeriod[];
  readonly unrecorded: readonly Unrecorded[];
  /** The calls questions made, or absent with `callsTold` saying why. */
  readonly calls?: ConnectorCalls;
  readonly callsTold?: string;
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

function figure(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : undefined;
}

function readCalls(value: unknown): ConnectorCalls | undefined {
  const fields = fieldsOf(value);
  if (fields === null) {
    return undefined;
  }
  const numbers = [
    figure(fields["window_seconds"]),
    counted(fields["requests"]),
    figure(fields["per_second"]),
    figure(fields["per_minute"]),
    counted(fields["concurrency"]),
    figure(fields["quota_ratio"]),
    figure(fields["error_ratio"]),
    figure(fields["latency_p50_ms"]),
    figure(fields["latency_p95_ms"]),
  ];
  const [windowSeconds, requests, perSecond, perMinute, concurrency, quotaRatio, errorRatio, latencyP50Ms, latencyP95Ms] =
    numbers;
  if (
    windowSeconds === undefined ||
    requests === undefined ||
    perSecond === undefined ||
    perMinute === undefined ||
    concurrency === undefined ||
    quotaRatio === undefined ||
    errorRatio === undefined ||
    latencyP50Ms === undefined ||
    latencyP95Ms === undefined
  ) {
    return undefined;
  }
  return {
    windowSeconds,
    requests,
    perSecond,
    perMinute,
    concurrency,
    quotaRatio,
    errorRatio,
    latencyP50Ms,
    latencyP95Ms,
    quiet: fields["quiet"] === true,
  };
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
  const liveReads = counted(fields["live_reads"]);
  return {
    range,
    ...(attempts === undefined ? {} : { attempts }),
    ...(readToTheEnd === undefined ? {} : { readToTheEnd }),
    ...(failures === undefined ? {} : { failures }),
    ...(quotaWaits === undefined ? {} : { quotaWaits }),
    ...(liveReads === undefined ? {} : { liveReads }),
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
  const liveReadBasis = said(fields["live_read_basis"]);
  const lastLiveRead = fields["last_live_read"] === null ? null : instant(fields["last_live_read"]);
  const calls = readCalls(fields["calls"]);
  const callsTold = said(fields["calls_told"]);
  return {
    ...(health === undefined ? {} : { health }),
    ...(lastAttempt === undefined ? {} : { lastAttempt }),
    ...(lastReadToTheEnd === undefined ? {} : { lastReadToTheEnd }),
    ...(consecutiveFailures === undefined ? {} : { consecutiveFailures }),
    ...(indexIds === undefined ? {} : { indexIds }),
    ...(liveReadBasis === undefined ? {} : { liveReadBasis }),
    ...(lastLiveRead === undefined ? {} : { lastLiveRead }),
    atLeast: fields["at_least"] === true,
    periods,
    unrecorded,
    ...(calls === undefined ? {} : { calls }),
    ...(callsTold === undefined ? {} : { callsTold }),
  };
}

/** A share of calls as a page draws it, or the sentence that there were too few to mean one. */
export function shareWords(ratio: number, calls: ConnectorCalls): string {
  return calls.quiet ? "Too few calls to say" : `${Math.round(ratio * 100).toString()}%`;
}

/** One period's figures, or the first sent when that period was not. */
export function connectorPeriodOf(stats: ConnectorStats | null, range: string): ConnectorPeriod | undefined {
  return stats?.periods.find((one) => one.range === range) ?? stats?.periods[0];
}

/** An index size as a page draws it: ids, grouped for reading. */
export function idsWords(value: number | undefined): string | undefined {
  return value === undefined ? undefined : `${value.toLocaleString("en-GB")} ids`;
}

/** Whose questions the live reads are, in words: the route's two bases. */
export function questionsWords(basis: string | undefined): string | undefined {
  return basis === "own" ? "your questions" : basis === "everyone" ? "all questions" : undefined;
}
