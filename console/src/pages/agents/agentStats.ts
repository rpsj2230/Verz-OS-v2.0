/**
 * An agent's figures: a small typed client over the stats route every module shares.
 *
 * **One path shape for every module, `GET /api/v1/console/<module>/<id>/stats`,** built by a
 * separate package in parallel with this one. This file codes against that path and reads the body
 * defensively, so a route that is absent, still being built or shaped differently draws the strip's
 * failed or empty state and never a number this browser made up. See `kit/KpiStrip.tsx`' rule that a
 * figure nothing sent is "Not recorded yet", never nought.
 *
 * **Each figure is carried only when it is a whole number from nought up.** A null, a string, a
 * negative or a fraction in its place is no figure, and the page says so. A count is the API's
 * answer over what this reader may see; this file adds nothing to it and subtracts nothing from it,
 * and there is deliberately no field here for a total or for anything withheld.
 *
 * The wire names are the stats package's contract as briefed: `runs`, `answered`, `refused`,
 * `cost_minor`, `currency`, `last_active_at` and `range`, at the top of the body or under `stats`.
 * A difference found when that package lands is reconciled here and nowhere else.
 *
 * Task ids: M27.10.2
 */

/** The module name the agents pages ask the stats route about. */
export const AGENTS_MODULE = "agents";

/** Where one entity's figures are asked for, under the API base. */
export function statsApiPath(module: string, id: string): string {
  return `/console/${encodeURIComponent(module)}/${encodeURIComponent(id)}/stats`;
}

/** Where one agent's figures are asked for. */
export function agentStatsApiPath(agentId: string): string {
  return statsApiPath(AGENTS_MODULE, agentId);
}

/** One agent's figures as this console holds them. Every field is absent when none was sent. */
export interface AgentStats {
  /** The window the figures cover, as the API spells it: "30d". */
  readonly range?: string;
  readonly runs?: number;
  readonly answered?: number;
  readonly refused?: number;
  /** Cost in minor units. No currency symbol is invented: see `currency`. */
  readonly costMinor?: number;
  /** The install's currency code, when the API states one. */
  readonly currency?: string;
  /** When the agent last ran, as an ISO instant. */
  readonly lastActiveAt?: string;
}

type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(value: unknown): Fields | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  // A cast at the boundary, where proving a structural match buys nothing: every field is read
  // back through `counted` or `said` below.
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

/** The figures out of a body, or null when the body is not an object at all. */
export function readAgentStats(payload: unknown): AgentStats | null {
  const outer = fieldsOf(payload);
  if (outer === null) {
    return null;
  }
  const fields = fieldsOf(outer["stats"]) ?? outer;
  const range = said(fields["range"]);
  const runs = counted(fields["runs"]);
  const answered = counted(fields["answered"]);
  const refused = counted(fields["refused"]);
  const costMinor = counted(fields["cost_minor"]);
  const currency = said(fields["currency"]);
  const lastActiveAt = instant(fields["last_active_at"]);
  return {
    ...(range === undefined ? {} : { range }),
    ...(runs === undefined ? {} : { runs }),
    ...(answered === undefined ? {} : { answered }),
    ...(refused === undefined ? {} : { refused }),
    ...(costMinor === undefined ? {} : { costMinor }),
    ...(currency === undefined ? {} : { currency }),
    ...(lastActiveAt === undefined ? {} : { lastActiveAt }),
  };
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

/** An instant as a day and a time, in the reader's own time zone. */
export function whenWords(at: string | undefined): string | undefined {
  if (at === undefined) {
    return undefined;
  }
  const date = new Date(at);
  return date.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

/** The window the figures cover, in words. */
export function rangeWords(range: string | undefined): string {
  const days = range === undefined ? null : /^(\d+)d$/.exec(range);
  return days?.[1] === undefined ? "recent" : `${days[1]} days`;
}
