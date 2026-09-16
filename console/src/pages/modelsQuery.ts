/**
 * What the Models and health screen asks four routes for, and how their answers become the
 * design's cards. No React.
 *
 * `docs/screens.html` SCREEN 11 is the design of record: four figures across the top (answered
 * without a model, p95 answer, fallbacks fired, cost over seven days), a Priority and fallback
 * table with a row per lane and a column per rung, and two cards beneath it, Provider health and
 * Spend by department, with an Edit routing action in the bar. This module turns four answers
 * into those cards and decides nothing about who may read any of them.
 *
 * **Four requests, each to the route that owns the figure, and each card draws its own answer.**
 * The chain is `GET /routing/rungs` behind the matrix's grant, the p95 against its objective is
 * `GET /report/service-levels` behind the usage grant, the cost is `GET /report/spend` behind the
 * same, and what only this screen knows is `GET /operate/models` behind the models screen's own
 * grant (`brain.operate_routes`). A reader holding some and not others sees the cards they hold
 * and the API's refusal where they do not, which is `A_FIGURE_ANOTHER_ROUTE_SERVES_IS_READ_THERE`
 * on that module: one set of rows behind two grants is the day one screen shows what another
 * refuses.
 *
 * **The design draws lanes and the chain is kept by tier, and the table says tier.** Fast, Answer
 * and Task are how a request is admitted (`brain.core.lane`); None, Small, Main and Heavy are the
 * pools a model is chosen from (`brain.models.routing.Tier`), and `ops.routing_rung` is keyed by
 * the second. Relabelling tiers as lanes would put the design's words on rows that mean something
 * else, so the column is headed Tier and each row says what it handles.
 *
 * **Three of the design's figures have no source, and each is said once in the API's terms.**
 * No model is called by this install, so there is no provider health to draw, no fallback to have
 * fired and no latency or budget per tier. `brain.operate_routes` sends which measurements the
 * ledger cannot fill (`brain.ops.telemetry.UNFILLABLE_TODAY`) and whether a breaker or a key's
 * presence is readable; `MEASURE_SENTENCES` is those facts in an administrator's words, and a
 * measurement this console has no sentence for is shown in the API's own. See
 * `A_BAR_WITH_NOTHING_BEHIND_IT_IS_A_HEALTHY_PROVIDER`.
 *
 * **No count of rungs, tiers or providers is rendered** beyond the share of requests answered
 * without a model, which is over the whole install's traffic and is served only to a reader who
 * may see all of it.
 *
 * Task ids: M27.2.3
 */

import type { components } from "../api/schema";
import type { RungRow } from "./matrixQuery";
import type { LaneReadingRow } from "./serviceLevelsQuery";
import type { SpendReportBody } from "./spendQuery";

/** What only the models route knows, as `brain.operate_routes.ModelsView` sends it. */
export type ModelsBody = components["schemas"]["ModelsView"];
export type ProviderSlotRow = components["schemas"]["ProviderView"];
export type TierRow = components["schemas"]["TierView"];
export type LaneTrafficRow = components["schemas"]["LaneTrafficView"];

/** Written down because the design's Provider health card is a row of green bars. */
export const A_BAR_WITH_NOTHING_BEHIND_IT_IS_A_HEALTHY_PROVIDER =
  "SCREEN 11 draws each provider with a bar of its success rate and its latency. Nothing in this " +
  "install has called a provider, so there is no rate and no latency, and a bar drawn at full " +
  "width or left empty would say healthy or down about a provider nobody has asked anything. The " +
  "card lists the providers and where the chain names them, and says in words that their health " +
  "is not recorded.";

/** Where the API keeps this screen's own answer. */
export const MODELS_API_PATH = "/operate/models";

/**
 * The console address, which is the screen's key in `brain.console.screens` so that
 * `brain.ops.console_screens.routed_screen_keys` matches the route against the registry.
 */
export const MODELS_PATH = "/models";

/** The design's navigation label and this page's heading. */
export const MODELS_LABEL = "Models and health";

/** The window parameter the models and service-level routes both declare. */
export const HOURS_PARAMETER = "hours";

/** The window the spend route is asked from, as the first day it covers. */
export const SINCE_PARAMETER = "since";

/**
 * How long a window this screen reads, in days. Seven, the design's own "Last 7 days", and the
 * one window every card on the page is asked for so no two figures beside each other cover
 * different spans.
 */
export const WINDOW_DAYS = 7;

/** The same window in hours, for the two routes that take hours. */
export const WINDOW_HOURS = WINDOW_DAYS * 24;

/** The request this screen makes of its own route. */
export function modelsApiPath(): string {
  return `${MODELS_API_PATH}?${HOURS_PARAMETER}=${String(WINDOW_HOURS)}`;
}

/** The request this screen makes of the service-level route, over the same window. */
export function answerLatencyApiPath(serviceLevelsApiPath: string): string {
  return `${serviceLevelsApiPath}?${HOURS_PARAMETER}=${String(WINDOW_HOURS)}`;
}

/**
 * The request this screen makes of the spend route: by department, from the first day of the
 * window. `since` is a UTC day, which is the spend view's own grain.
 */
export function spendSinceApiPath(spendApiPath: string, dimension: string, now: Date): string {
  const first = new Date(now.getTime() - WINDOW_DAYS * 86_400_000).toISOString().slice(0, 10);
  return `${spendApiPath}?dimension=${dimension}&${SINCE_PARAMETER}=${first}`;
}

/**
 * Read `ModelsView` out of a response body, or null.
 *
 * Null rather than an empty answer, for `readServiceLevels`' reason: an answer with no providers
 * and no lanes would be drawn as an install with nothing configured.
 */
export function readModels(payload: unknown): ModelsBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as {
    tiers?: unknown;
    lanes?: unknown;
    providers?: unknown;
    unmeasured?: unknown;
  };
  if (
    !Array.isArray(body.tiers) ||
    !Array.isArray(body.lanes) ||
    !Array.isArray(body.providers) ||
    !Array.isArray(body.unmeasured)
  ) {
    return null;
  }
  return payload as ModelsBody;
}

/** The fast lane's name, which is the lane that answers with no model at all. */
export const FAST_LANE = "fast";

/** The lane whose p95 the design's second figure is. */
export const ANSWER_LANE = "answer";

/**
 * The share of requests the fast lane answered, as a whole percentage, or null when nothing
 * finished in the window.
 *
 * A unit change over two figures the API sent about the whole install, and null rather than
 * zero for an empty window: zero per cent would say every request needed a model.
 */
export function withoutAModel(lanes: readonly LaneTrafficRow[]): string | null {
  const total = lanes.reduce((sum, one) => sum + one.requests, 0);
  if (total === 0) {
    return null;
  }
  const fast = lanes.find((one) => one.lane === FAST_LANE)?.requests ?? 0;
  return `${String(Math.round((fast / total) * 100))}%`;
}

/** The answer lane's reading, or null when the reading carries none. */
export function answerReading(lanes: readonly LaneReadingRow[]): LaneReadingRow | null {
  return lanes.find((one) => one.lane === ANSWER_LANE) ?? null;
}

/** One tier's row in the Priority and fallback table. */
export interface ChainRow {
  readonly tier: string;
  readonly handles: string;
  /** The tier's rungs, in the order the router tries them. */
  readonly rungs: readonly RungRow[];
}

/**
 * The tiers in the order the API declares them, each with its rungs in position order.
 *
 * Rungs are grouped by the tier they name and sorted by position, which is the order the router
 * follows, so the first is the primary whatever order the page arrived in.
 */
export function chainRows(tiers: readonly TierRow[], rungs: readonly RungRow[]): ChainRow[] {
  return tiers.map((tier) => ({
    tier: tier.tier,
    handles: tier.handles,
    rungs: rungs
      .filter((one) => one.tier === tier.tier)
      .slice()
      .sort((a, b) => a.position - b.position),
  }));
}

/** The tier that answers with no model, whose empty chain is the design's "no model" pill. */
export const NO_MODEL_TIER = "none";

/** One provider's row in the Provider health card. */
export interface ProviderRow {
  readonly provider: string;
  /** What the slot says it is for, or null when the chain names a provider with no slot. */
  readonly description: string | null;
  /** Where the chain names it, as "tier position", in chain order. */
  readonly inChain: readonly string[];
}

/**
 * Every provider slot, then every provider the chain names that has no slot.
 *
 * The second group is the finding worth drawing: a rung naming a provider this system cannot hold
 * a key for is a rung that cannot answer, and it would otherwise look like any other row.
 */
export function providerRows(
  slots: readonly ProviderSlotRow[],
  rungs: readonly RungRow[],
): ProviderRow[] {
  const ordered = rungs.slice().sort((a, b) => a.tier.localeCompare(b.tier) || a.position - b.position);
  const where = (provider: string) =>
    ordered
      .filter((one) => one.provider === provider)
      .map((one) => `${one.tier} ${String(one.position)}`);
  const slotted = new Set(slots.map((one) => one.provider));
  const unslotted = [...new Set(ordered.map((one) => one.provider))].filter(
    (one) => !slotted.has(one),
  );
  return [
    ...slots.map((one) => ({
      provider: one.provider,
      description: one.description,
      inChain: where(one.provider),
    })),
    ...unslotted.map((provider) => ({ provider, description: null, inChain: where(provider) })),
  ];
}

/**
 * What an administrator is told about each measurement the ledger cannot fill, by the ledger's
 * own field name. A measurement not in this table is shown in the API's sentence.
 */
export const MEASURE_SENTENCES: Readonly<Record<string, string>> = Object.freeze({
  model:
    "No model is called by this install yet, so no answer records which model produced it. The " +
    "chain below is recorded and can be edited, and a change to it changes what is recorded " +
    "rather than what answers.",
  provider:
    "No provider has been called, so there is no success rate or latency to draw for any of them.",
  fallback_count:
    "Not measured. A fallback is a step down the chain, and no chain runs until a model is called.",
});

/** The sentence for one unmeasured measurement: this console's, or the API's own. */
export function measureSentence(measure: string, because: string): string {
  return MEASURE_SENTENCES[measure] ?? because;
}

/** Beside every provider while nothing stores a breaker. */
export const HEALTH_NOT_RECORDED = "Not recorded";

/** Beside every provider while the key's presence is not served here. */
export const KEY_STATUS_ARRIVES_WITH_THE_VAULT =
  "Whether a key is held for each provider is shown once the secrets vault screen is in place; " +
  "this screen never shows a key, only whether one is held.";

/** Beside a provider the chain names with no key slot. */
export const NO_KEY_SLOT =
  "No key slot: this system cannot hold a key for this provider, so a rung naming it cannot answer.";

/** One department's line in the spend card, with its share of the total the API sent. */
export interface SpendShare {
  readonly key: string;
  readonly costMinor: number;
  /** Between zero and one. A share of `total_minor`, which is the API's own sum of these lines. */
  readonly share: number;
}

/**
 * Each line with its share of the report's total, in the order the API sent them.
 *
 * The total is the API's and is not added up here, which is `spendQuery.
 * A_TOTAL_IS_READ_AND_NEVER_ADDED_UP_HERE`. Every line the reader may see is on the report, so a
 * share of that total is not a share of anything they were not shown.
 */
export function spendShares(report: SpendReportBody): SpendShare[] {
  const total = report.total_minor ?? 0;
  return report.lines.map((line) => ({
    key: line.key,
    costMinor: line.cost_minor,
    share: total > 0 ? line.cost_minor / total : 0,
  }));
}
