/**
 * An agent's figures: a small typed client over the stats route every module shares.
 *
 * **One path shape for every module, `GET /api/v1/console/<module>/<id>/stats`,** served by
 * `brain.console_stats_routes` (the stats package, built in parallel with this one). An agent's
 * answer is `AgentStatsView`: whose the figures are (`basis`, `cost_basis`), the install's
 * `currency`, when the agent was `last_active`, whether the requests were read to their bound
 * (`at_least`), one set of figures per period (7 and 30 days), and `unrecorded`, the figures the
 * page asks for that nothing on this install records, each with the reason.
 *
 * **A figure nothing records is "Not recorded yet" with its reason, never nought.** `cost_minor` is
 * null while no run's cost is written, and `unrecorded` names it; this file carries both, and the
 * page draws the sentence and puts the reason where a person can read it. A null, a string, a
 * negative or a fraction in a count's place is no figure. See `kit/KpiStrip.tsx`.
 *
 * **Refused and abstained are one figure, `nothing_returned`, and are never split here.** The route
 * keeps them together (`brain.console.entity_stats.A_REFUSAL_AND_AN_ABSENCE_ARE_ONE_FIGURE`) because
 * a refusal counted apart from an absence tells a reader how often an agent was asked about
 * something they may not see.
 *
 * Task ids: M27.10.2
 */

/** The module name the agents pages ask the stats route about. */
export const AGENTS_MODULE = "agents";

/** The period the page shows first: the design's own thirty days. */
export const FIRST_PERIOD = "30d";

/** Where one entity's figures are asked for, under the API base. */
export function statsApiPath(module: string, id: string): string {
  return `/console/${encodeURIComponent(module)}/${encodeURIComponent(id)}/stats`;
}

/** Where one agent's figures are asked for. */
export function agentStatsApiPath(agentId: string): string {
  return statsApiPath(AGENTS_MODULE, agentId);
}

/** One agent's figures over one period. A figure is absent when none was sent. */
export interface AgentPeriod {
  /** As the API spells it: "7d" or "30d". */
  readonly range: string;
  readonly runs?: number;
  readonly answered?: number;
  /** Refused and abstained together. */
  readonly nothingReturned?: number;
  readonly p50LatencyMs?: number;
  /** In the install's minor units. Absent while nothing records a run's cost. */
  readonly costMinor?: number;
}

/** A figure the page asks for that nothing on this install records, and why. */
export interface Unrecorded {
  readonly figure: string;
  readonly why: string;
}

/** One agent's figures as this console holds them. */
export interface AgentStats {
  /** Whose requests: "own" or "everyone". */
  readonly basis?: string;
  /** Whose cost: "own" or "everyone". */
  readonly costBasis?: string;
  readonly currency?: string;
  /** When the agent last answered, as an ISO instant. */
  readonly lastActiveAt?: string;
  /** The requests were read to their bound, so the figures are at least these. */
  readonly atLeast: boolean;
  readonly periods: readonly AgentPeriod[];
  readonly unrecorded: readonly Unrecorded[];
}

/** The figure `unrecorded` names a run's cost by. `brain.console.entity_stats.RUN_COST_IS_NOT_RECORDED`. */
export const COST_FIGURE = "model_cost";

type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(value: unknown): Fields | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  // A cast at the boundary, where proving a structural match buys nothing: every field is read
  // back through `counted`, `measured`, `said` or `instant` below.
  return value as Fields;
}

function counted(value: unknown): number | undefined {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : undefined;
}

function measured(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : undefined;
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

function readPeriod(value: unknown): AgentPeriod | null {
  const fields = fieldsOf(value);
  const range = said(fields?.["range"]);
  if (fields === null || range === undefined) {
    return null;
  }
  const runs = counted(fields["runs"]);
  const answered = counted(fields["answered"]);
  const nothingReturned = counted(fields["nothing_returned"]);
  const p50LatencyMs = measured(fields["p50_latency_ms"]);
  const costMinor = counted(fields["cost_minor"]);
  return {
    range,
    ...(runs === undefined ? {} : { runs }),
    ...(answered === undefined ? {} : { answered }),
    ...(nothingReturned === undefined ? {} : { nothingReturned }),
    ...(p50LatencyMs === undefined ? {} : { p50LatencyMs }),
    ...(costMinor === undefined ? {} : { costMinor }),
  };
}

/** The figures out of a body, or null when the body is not an object at all. */
export function readAgentStats(payload: unknown): AgentStats | null {
  const fields = fieldsOf(payload);
  if (fields === null) {
    return null;
  }
  const basis = said(fields["basis"]);
  const costBasis = said(fields["cost_basis"]);
  const currency = said(fields["currency"]);
  const lastActiveAt = instant(fields["last_active"]);
  const seen = new Set<string>();
  const periods: AgentPeriod[] = [];
  for (const one of listOf(fields["periods"])) {
    const period = readPeriod(one);
    if (period !== null && !seen.has(period.range)) {
      seen.add(period.range);
      periods.push(period);
    }
  }
  const unrecorded: Unrecorded[] = [];
  for (const one of listOf(fields["unrecorded"])) {
    const row = fieldsOf(one);
    const figure = said(row?.["figure"]);
    const why = said(row?.["why"]);
    if (figure !== undefined && why !== undefined) {
      unrecorded.push({ figure, why });
    }
  }
  return {
    ...(basis === undefined ? {} : { basis }),
    ...(costBasis === undefined ? {} : { costBasis }),
    ...(currency === undefined ? {} : { currency }),
    ...(lastActiveAt === undefined ? {} : { lastActiveAt }),
    atLeast: fields["at_least"] === true,
    periods,
    unrecorded,
  };
}

/** One period's figures, or the first sent when that period was not. */
export function periodOf(stats: AgentStats | null, range: string): AgentPeriod | undefined {
  return stats?.periods.find((one) => one.range === range) ?? stats?.periods[0];
}

/** Why a figure is not recorded, when the route said it is not. */
export function unrecordedWhy(stats: AgentStats | null, figure: string): string | undefined {
  return stats?.unrecorded.find((one) => one.figure === figure)?.why;
}

/** A count as a page draws it, grouped for reading. */
export function countWords(value: number | undefined): string | undefined {
  return value === undefined ? undefined : value.toLocaleString("en-GB");
}

/** A cost in minor units, with the install's currency code when the API stated one. */
export function costWords(minor: number | undefined, currency: string | undefined): string | undefined {
  if (minor === undefined) {
    return undefined;
  }
  const amount = (minor / 100).toFixed(2);
  return currency === undefined ? amount : `${currency} ${amount}`;
}

/** A median time, in seconds below a minute and milliseconds below a second. */
export function latencyWords(ms: number | undefined): string | undefined {
  if (ms === undefined) {
    return undefined;
  }
  return ms < 1000 ? `${String(Math.round(ms))} ms` : `${(ms / 1000).toFixed(1)} s`;
}

/** An instant as a day and a time, in the reader's own time zone. */
export function whenWords(at: string | undefined): string | undefined {
  if (at === undefined) {
    return undefined;
  }
  return new Date(at).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

/** A period in words. */
export function rangeWords(range: string | undefined): string {
  const days = range === undefined ? null : /^(\d+)d$/.exec(range);
  return days?.[1] === undefined ? "recent" : `${days[1]} days`;
}

/** Whose figures, in words: the API's two bases. */
export function basisWords(basis: string | undefined): string | undefined {
  return basis === "own" ? "your runs" : basis === "everyone" ? "all runs" : undefined;
}
