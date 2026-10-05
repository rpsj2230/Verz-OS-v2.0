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
 * **Four periods, and three more figures, for the agent's own page (M39.1.3).** The route sends 7, 30
 * and 90 days and the month to date; each period carries `messages` (the runs a person started, so an
 * automation's run is a run and not a message) and `callers`, the cost per person, heaviest first,
 * at the cost's basis, so a reader of their own spend is given their own row and no remainder. The
 * body carries `projection`, the month-end projection against the agent's own monthly budget, only
 * for a reader of everybody's spend and only when a budget is set.
 *
 * Task ids: M27.10.2, M39.1.3.1, M39.1.3.2, M39.1.3.3, M39.1.3.4
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

/** One person's spend through the agent over one period, heaviest first. */
export interface CallerSpend {
  readonly principalId: string;
  /** The directory's name, absent for an id it does not hold. */
  readonly name?: string;
  readonly spendMinor: number;
}

/** One agent's figures over one period. A figure is absent when none was sent. */
export interface AgentPeriod {
  /** As the API spells it: "7d", "30d", "90d" or "mtd". */
  readonly range: string;
  readonly runs?: number;
  /** The runs a person started. */
  readonly messages?: number;
  readonly answered?: number;
  /** Refused and abstained together. */
  readonly nothingReturned?: number;
  readonly p50LatencyMs?: number;
  /** In the install's minor units. Absent while nothing records a run's cost. */
  readonly costMinor?: number;
  /** The cost per person, heaviest first; empty while nothing records a run's cost. */
  readonly callers: readonly CallerSpend[];
}

/** Where the month ends against the agent's own monthly budget if nothing changes. */
export interface Projection {
  readonly spentMinor: number;
  readonly projectedMinor: number;
  readonly ceilingMinor: number;
  readonly overCeiling: boolean;
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
  /** Sent only to a reader of everybody's spend, and only with a monthly budget set. */
  readonly projection?: Projection;
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
  const messages = counted(fields["messages"]);
  const callers: CallerSpend[] = [];
  for (const one of listOf(fields["callers"])) {
    const row = fieldsOf(one);
    const principalId = said(row?.["principal_id"]);
    const spendMinor = counted(row?.["spend_minor"]);
    const name = said(row?.["name"]);
    if (principalId !== undefined && spendMinor !== undefined) {
      callers.push({ principalId, spendMinor, ...(name === undefined ? {} : { name }) });
    }
  }
  return {
    range,
    callers,
    ...(runs === undefined ? {} : { runs }),
    ...(messages === undefined ? {} : { messages }),
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
  const projection = readProjection(fields["projection"]);
  return {
    ...(basis === undefined ? {} : { basis }),
    ...(costBasis === undefined ? {} : { costBasis }),
    ...(currency === undefined ? {} : { currency }),
    ...(lastActiveAt === undefined ? {} : { lastActiveAt }),
    ...(projection === undefined ? {} : { projection }),
    atLeast: fields["at_least"] === true,
    periods,
    unrecorded,
  };
}

function readProjection(value: unknown): Projection | undefined {
  const fields = fieldsOf(value);
  const spentMinor = counted(fields?.["spent_minor"]);
  const projectedMinor = counted(fields?.["projected_minor"]);
  const ceilingMinor = counted(fields?.["ceiling_minor"]);
  if (fields === null || spentMinor === undefined || projectedMinor === undefined || ceilingMinor === undefined) {
    return undefined;
  }
  return { spentMinor, projectedMinor, ceilingMinor, overCeiling: fields["over_ceiling"] === true };
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
  if (range === MONTH_TO_DATE) {
    return "Month to date";
  }
  const days = range === undefined ? null : /^(\d+)d$/.exec(range);
  return days?.[1] === undefined ? "recent" : `${days[1]} days`;
}

/** The month-to-date period's key, as `brain.console.workspace.Range` spells it. */
export const MONTH_TO_DATE = "mtd";

/** The four periods an agent's page offers, in the route's order (M39.1.3.2). */
export const AGENT_PERIODS = ["7d", "30d", "90d", MONTH_TO_DATE] as const;

/** Whose figures, in words: the API's two bases. */
export function basisWords(basis: string | undefined): string | undefined {
  return basis === "own" ? "your runs" : basis === "everyone" ? "all runs" : undefined;
}
