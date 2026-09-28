/**
 * A channel's figures: a small typed client over the stats route every module shares.
 *
 * **`GET /api/v1/console/channels/{name}/stats`, served by `brain.console_stats_routes`.** Its
 * answer is `ChannelStatsView`: the people bound on the channel at the People screen's basis, when
 * anything last crossed it, whether the deliveries were read to their bound, one set of figures per
 * period (received, sent, failed, not known, refused inbound), and `unrecorded`. The route answers
 * only a channel this release receives on, so the page asks only for those.
 *
 * **A figure nothing sent is "Not recorded yet", never nought**, `kit/KpiStrip.tsx`' rule: a period
 * the route left out, or a field it did not send, is absent here and the card draws the sentence.
 *
 * **Bound people on the narrower basis is the reader alone.** A reader who may not read the People
 * screen over everything is told whether they are bound themselves, and the card says so, so a 1
 * there is never read as the channel's total.
 *
 * Task ids: M27.13.1, M27.16.1
 */

import { statsApiPath } from "../agents/agentStats";

/** The module name the stats route answers channels under. */
export const CHANNELS_MODULE = "channels";

/** The period the page shows first. */
export const FIRST_PERIOD = "30d";

export function channelStatsApiPath(name: string): string {
  return statsApiPath(CHANNELS_MODULE, name);
}

/** One period's traffic. A figure is absent when none was sent. */
export interface ChannelPeriod {
  readonly range: string;
  readonly received?: number;
  readonly sent?: number;
  readonly failed?: number;
  readonly unknown?: number;
  readonly refusedInbound?: number;
}

export interface Unrecorded {
  readonly figure: string;
  readonly why: string;
}

export interface ChannelStats {
  readonly boundPeople?: number;
  /** `everyone` or `own`, as the route says whose bindings were counted. */
  readonly boundBasis?: string;
  readonly lastEvent?: string;
  readonly atLeast: boolean;
  readonly periods: readonly ChannelPeriod[];
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

function readPeriod(value: unknown): ChannelPeriod | null {
  const fields = fieldsOf(value);
  const range = said(fields?.["range"]);
  if (fields === null || range === undefined) {
    return null;
  }
  const received = counted(fields["received"]);
  const sent = counted(fields["sent"]);
  const failed = counted(fields["failed"]);
  const unknown = counted(fields["unknown"]);
  const refusedInbound = counted(fields["refused_inbound"]);
  return {
    range,
    ...(received === undefined ? {} : { received }),
    ...(sent === undefined ? {} : { sent }),
    ...(failed === undefined ? {} : { failed }),
    ...(unknown === undefined ? {} : { unknown }),
    ...(refusedInbound === undefined ? {} : { refusedInbound }),
  };
}

/** The figures out of a body, or null when the body is not an object at all. */
export function readChannelStats(payload: unknown): ChannelStats | null {
  const fields = fieldsOf(payload);
  if (fields === null) {
    return null;
  }
  const seen = new Set<string>();
  const periods: ChannelPeriod[] = [];
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
  const boundPeople = counted(fields["bound_people"]);
  const boundBasis = said(fields["bound_basis"]);
  const lastEvent = instant(fields["last_event"]);
  return {
    ...(boundPeople === undefined ? {} : { boundPeople }),
    ...(boundBasis === undefined ? {} : { boundBasis }),
    ...(lastEvent === undefined ? {} : { lastEvent }),
    atLeast: fields["at_least"] === true,
    periods,
    unrecorded,
  };
}

/** One period's figures, or the first sent when that period was not. */
export function channelPeriodOf(stats: ChannelStats | null, range: string): ChannelPeriod | undefined {
  return stats?.periods.find((one) => one.range === range) ?? stats?.periods[0];
}

/** What the bound people figure is over, in words, or nothing when it is everyone's. */
export function boundBasisWords(basis: string | undefined): string | undefined {
  return basis === "own" ? "you alone: whether you are bound" : undefined;
}
