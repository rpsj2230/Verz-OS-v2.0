/**
 * What the Models and health screen asks five routes for, how their answers become the design's
 * cards, and the words for a provider's two controls. No React.
 *
 * `docs/screens.html` SCREEN 11 is the design of record: four figures across the top (answered
 * without a model, p95 answer, fallbacks fired, cost over seven days), a Priority and fallback
 * table with a row per lane and a column per rung, and two cards beneath it, Provider health and
 * Spend by department, with an Edit routing action in the bar. This module turns five answers
 * into those cards and decides nothing about who may read any of them.
 *
 * **Five requests, each to the route that owns the figure, and each card draws its own answer.**
 * The chain is `GET /routing/rungs` behind the matrix's grant, the p95 against its objective is
 * `GET /report/service-levels` behind the usage grant, the cost is `GET /report/spend` behind the
 * same, the figures only this screen knows are `GET /operate/models` behind the models screen's
 * own grant (`brain.operate_routes`), and the providers with each rung's health are
 * `GET /models/providers` (`brain.provider_routes`) behind that same grant. A reader holding some
 * and not others sees the cards they hold and the API's refusal where they do not, which is
 * `A_FIGURE_ANOTHER_ROUTE_SERVES_IS_READ_THERE` on `brain.operate_routes`: one set of rows behind
 * two grants is the day one screen shows what another refuses.
 *
 * **The design draws lanes and the chain is kept by tier, and the table says tier.** Fast, Answer
 * and Task are how a request is admitted (`brain.core.lane`); None, Small, Main and Heavy are the
 * pools a model is chosen from (`brain.models.routing.Tier`), and `ops.routing_rung` is keyed by
 * the second. Relabelling tiers as lanes would put the design's words on rows that mean something
 * else, so the column is headed Tier and each row says what it handles.
 *
 * **A model is called now, and the health drawn is the evidence of those calls.** The executor
 * `brain.models.calls` makes every model call and records each attempt; `brain.provider_routes`
 * serves the plan the next call will make, with each rung's breaker replayed from those attempts
 * through `brain.console.model_matrix`, marked measured or not. This module draws that plan and
 * recomputes none of it: which rungs answer, why one is left out and whether a breaker is open are
 * the API's sentences and states. The answer lane still answers from fast-path rules, so a busy
 * install can show rungs nothing has called yet, and `AN_UNCALLED_RUNG_IS_NOT_A_HEALTHY_ONE` is
 * what the page draws for them.
 *
 * **A measurement the ledger cannot fill is said in the API's words and not in this console's.**
 * This module used to keep its own sentence for the model, the provider and the fallback count,
 * and every one of them said no model is called. They went on saying it in the commit that started
 * calling one, because a paraphrase kept here does not leave when the ledger's reason does. The
 * API's sentence is written beside the empty field in `brain.ops.telemetry.UNFILLABLE_TODAY` and
 * leaves with it, so that is the sentence drawn.
 *
 * **No count of rungs, tiers or providers is rendered** beyond the share of requests answered
 * without a model, the fallbacks fired and each rung's recent calls, which are over the whole
 * install and served only to a reader who may see all of it.
 *
 * Task ids: M27.2.3, M27.8.8
 */

import type { components } from "../api/schema";
import { when } from "./sessionsQuery";
import type { RungRow } from "./matrixQuery";
import type { LaneReadingRow } from "./serviceLevelsQuery";
import type { SpendReportBody } from "./spendQuery";

/** What only the models route knows, as `brain.operate_routes.ModelsView` sends it. */
export type ModelsBody = components["schemas"]["ModelsView"];
export type TierRow = components["schemas"]["TierView"];
export type LaneTrafficRow = components["schemas"]["LaneTrafficView"];

/** The providers and the ladder as the next call sees them, `brain.provider_routes.ProvidersView`. */
export type ProvidersBody = components["schemas"]["ProvidersView"];
export type ProviderStateRow = components["schemas"]["ProviderStateView"];
export type RungStateRow = components["schemas"]["RungStateView"];
/** How one check ended, `brain.provider_routes.CheckView`. Never the model's reply. */
export type CheckBody = components["schemas"]["CheckView"];

/** Written down because a breaker starts closed, and closed is what healthy looks like. */
export const AN_UNCALLED_RUNG_IS_NOT_A_HEALTHY_ONE =
  "A breaker starts closed, because a router that started unknown would serve nothing until " +
  "something had called every rung. That is right for the router and wrong for a screen: a rung " +
  "nothing has called would be drawn healthy on the strength of nobody having looked. So a rung " +
  "the API marks unmeasured is drawn as not called yet, and a closed breaker is drawn as healthy " +
  "only when attempts stand behind it.";

/** Written down because a check looks like a read and is a call somebody pays for. */
export const A_CHECK_SPENDS_TOKENS_SO_IT_IS_CONFIRMED =
  "A check sends a real request to a provider through the same chain, breaker and meter as a " +
  "question, costs tokens and is recorded under the person who pressed it. A button that did " +
  "that on one press would be a cost nobody agreed to, so it is confirmed like a switch is, and " +
  "the confirmation says what is sent, what it costs and whose name it is recorded under.";

/** Where the API keeps this screen's own answer. */
export const MODELS_API_PATH = "/operate/models";

/** Where the API keeps the providers, their switches and each rung's health. */
export const PROVIDERS_API_PATH = "/models/providers";

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

/** Where one provider is switched on or off. */
export function providerSwitchApiPath(provider: string): string {
  return `${PROVIDERS_API_PATH}/${encodeURIComponent(provider)}`;
}

/** Where one provider is checked. */
export function providerCheckApiPath(provider: string): string {
  return `${providerSwitchApiPath(provider)}/check`;
}

/** The one field a switch carries, `brain.provider_routes.ProviderSwitchAsked`. */
export function switchBody(on: boolean): components["schemas"]["ProviderSwitchAsked"] {
  return { on };
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
    fallbacks_fired?: unknown;
  };
  if (
    !Array.isArray(body.tiers) ||
    !Array.isArray(body.lanes) ||
    !Array.isArray(body.providers) ||
    !Array.isArray(body.unmeasured) ||
    typeof body.fallbacks_fired !== "number"
  ) {
    return null;
  }
  return payload as ModelsBody;
}

/**
 * Read `ProvidersView` out of a response body, or null.
 *
 * Null for the same reason as `readModels`, and one more: an answer with no rungs is drawn as a
 * ladder that cannot answer anything, which is the sentence an administrator acts on fastest.
 */
export function readProviders(payload: unknown): ProvidersBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as {
    profile?: unknown;
    providers?: unknown;
    rungs?: unknown;
    exhausted_tiers?: unknown;
    editable?: unknown;
  };
  if (
    typeof body.profile !== "string" ||
    !Array.isArray(body.providers) ||
    !Array.isArray(body.rungs) ||
    !Array.isArray(body.exhausted_tiers) ||
    typeof body.editable !== "boolean"
  ) {
    return null;
  }
  return payload as ProvidersBody;
}

/** Read `CheckView` out of a response body, or null. */
export function readCheck(payload: unknown): CheckBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { provider?: unknown; answered?: unknown; told?: unknown; trace_id?: unknown };
  if (
    typeof body.provider !== "string" ||
    typeof body.answered !== "boolean" ||
    typeof body.told !== "string" ||
    typeof body.trace_id !== "string"
  ) {
    return null;
  }
  return payload as CheckBody;
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

/**
 * The API's sentence for one measurement it names as unmeasured, or null when it names none.
 *
 * The API's words and never a copy kept here; see the module docstring.
 */
export function unmeasuredBecause(models: ModelsBody, measure: string): string | null {
  return models.unmeasured.find((one) => one.measure === measure)?.because ?? null;
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

// ------------------------------------------------------------------------ provider health

/** The profile that keeps every question on the client's own hardware. */
export const LOCAL_PROFILE = "local";

/** The profile that lets a question reach a hosted provider. */
export const HOSTED_PROFILE = "hosted";

export const LOCAL_PROFILE_SENTENCE =
  "This install's model profile is local, so no question is sent to a hosted provider, whatever " +
  "is switched on below.";

export const HOSTED_PROFILE_SENTENCE =
  "This install's model profile is hosted, so questions may be sent to the hosted providers " +
  "switched on below that hold a key.";

/**
 * The profile in words. Anything but `hosted` is read as local, which is what
 * `brain.provider_routes.normalised_profile` does before it sends it, so the two cannot disagree
 * about a value neither expects.
 */
export function profileSentence(profile: string): string {
  return profile === HOSTED_PROFILE ? HOSTED_PROFILE_SENTENCE : LOCAL_PROFILE_SENTENCE;
}

export const SWITCHED_ON = "On";
export const SWITCHED_OFF = "Off";

/** Who last switched a provider and when, or null for one nobody has switched. */
export function switchedLine(row: ProviderStateRow): string | null {
  if (row.switched_by === null || row.switched_at === null) {
    return null;
  }
  return `Switched ${row.switched_on ? "on" : "off"} by ${row.switched_by} at ${when(row.switched_at)}.`;
}

export const KEY_HELD = "Held";
export const KEY_NOT_HELD = "Not held";
export const KEY_NOT_NEEDED = "Not needed";

/** Whether this server process holds a key for the provider, in words. Null is a provider needing none. */
export function keyHeldWords(held: boolean | null): string {
  return held === null ? KEY_NOT_NEEDED : held ? KEY_HELD : KEY_NOT_HELD;
}

/** Beside the key column, because it is easy to read as the vault's answer and it is not. */
export const KEY_HELD_IS_THIS_SERVER =
  "Key held is whether the server process that answered this page holds a key for the provider, " +
  "which is what decides whether its rungs answer here. No key is ever shown.";

export const VAULT_HELD = "Held in the vault";
export const VAULT_NOT_HELD = "Not in the vault";
export const VAULT_NOT_KNOWN = "Not known: the vault could not be asked";

/** The vault's own answer for one provider's slot, in words. */
export function credentialWords(credential: components["schemas"]["SlotView"]): string {
  if (credential.held === null) {
    return VAULT_NOT_KNOWN;
  }
  if (!credential.held) {
    return VAULT_NOT_HELD;
  }
  return credential.set_at === null ? VAULT_HELD : `${VAULT_HELD}, set ${when(credential.set_at)}`;
}

export const ANSWERS_NOW = "Answers";
export const RUNG_OUT_OF_ROTATION = "Out of rotation";

/**
 * Whether a rung answers the next call, in words: out of rotation, answering, or the API's own
 * sentence for why it is left out.
 */
export function answersWords(rung: RungStateRow): string {
  if (!rung.enabled) {
    return RUNG_OUT_OF_ROTATION;
  }
  if (rung.answers) {
    return ANSWERS_NOW;
  }
  return rung.told ?? NOT_ANSWERING;
}

/** A rung left out with no sentence from the API, which the route does not send and a release might. */
export const NOT_ANSWERING = "Does not answer the next call.";

export const NOT_CALLED_YET = "Not called yet, so there is no health to show";
export const HEALTHY = "Healthy";
export const RECOVERING = "Recovering: the next call to it is a test";
export const RESTING = "Resting after failures";

/** Why a breaker opened, by `brain.models.routing.FallbackTrigger` value. */
export const UNHEALTHY_BECAUSE: Readonly<Record<string, string>> = Object.freeze({
  connection_error: "the provider could not be reached",
  timeout: "the provider did not answer in time",
  rate_limited: "the provider asked for fewer requests",
  provider_error: "the provider reported a fault on its side",
  circuit_open: "its breaker was already open",
  context_exceeded: "a request did not fit the model's window",
});

/**
 * One rung's health in words. See `AN_UNCALLED_RUNG_IS_NOT_A_HEALTHY_ONE`: an unmeasured rung is
 * not called yet whatever state the API sends beside it.
 */
export function healthWords(rung: RungStateRow): string {
  if (!rung.measured) {
    return NOT_CALLED_YET;
  }
  switch (rung.state) {
    case "closed":
      return HEALTHY;
    case "half_open":
      return RECOVERING;
    case "open": {
      if (rung.unhealthy_because === null) {
        return RESTING;
      }
      return `${RESTING}: ${UNHEALTHY_BECAUSE[rung.unhealthy_because] ?? rung.unhealthy_because}`;
    }
  }
}

/** A rung's recent calls, as the API counted them. */
export function recentCalls(rung: RungStateRow): string {
  const calls = rung.live_seen === 1 ? "recent call" : "recent calls";
  return `${String(rung.live_seen)} ${calls}, ${String(rung.live_failed)} failed`;
}

export const TIERS_CANNOT_ANSWER = "Not every tier can answer";

/** One tier the API names as exhausted. */
export function exhaustedSentence(tier: string): string {
  return (
    `The ${tier} tier cannot answer: every rung on it is resting after recent failures, so a ` +
    "question needing it fails until one recovers."
  );
}

export const NO_PROVIDER = "No provider is listed.";
export const NO_RUNG_ON_THE_LADDER =
  "No rung is on the routing ladder, so no question can be answered by a model.";

// ------------------------------------------------------------------------ the two controls

export const SWITCH_ON = "Switch on";
export const SWITCH_OFF = "Switch off";
export const KEEP_IT_AS_IT_IS = "Keep it as it is";
export const CHECK = "Check";
export const SEND_THE_CHECK = "Send the check";
export const DO_NOT_CHECK = "Do not check";

/** The confirmation's question for a switch, naming the provider. */
export function switchQuestion(provider: string, on: boolean): string {
  return `Switch ${on ? "on" : "off"} ${provider}?`;
}

/** What a switch does, in each direction, naming the provider. */
export function switchConsequence(provider: string, on: boolean): string {
  if (on) {
    return (
      `From the next call, in every server process, rungs naming ${provider} may answer again ` +
      "where a key is held and the model profile allows it."
    );
  }
  return (
    `From the next call, in every server process, no question is sent to ${provider}. Its rungs ` +
    "leave the chain every tier walks, and a tier with no other rung that answers cannot answer."
  );
}

/** Said once the switch has been made, above the card the API's new plan is drawn in. */
export function switchedSentence(provider: string, on: boolean): string {
  return `${provider} is now switched ${on ? "on" : "off"}.`;
}

/** The confirmation's question for a check, naming the provider. */
export function checkQuestion(provider: string): string {
  return `Check ${provider}?`;
}

/** What a check does. See `A_CHECK_SPENDS_TOKENS_SO_IT_IS_CONFIRMED`. */
export function checkConsequence(provider: string): string {
  return (
    `This sends one short fixed sentence to ${provider} through its first rung that answers. It ` +
    "costs a few tokens and is recorded under your name. The provider's reply is not shown."
  );
}

/** The heading over a check's outcome. */
export function checkHeading(provider: string): string {
  return `Check of ${provider}`;
}

/** What answered a check and what it cost, as the API measured it. */
export function checkServedSentence(check: CheckBody): string {
  return (
    `Answered by ${check.model ?? "a model the API did not name"} on ` +
    `${check.served_by ?? "a deployment the API did not name"}, with ` +
    `${String(check.tokens_in ?? 0)} tokens in and ${String(check.tokens_out ?? 0)} tokens out.`
  );
}

/** The provider's status on a check that failed with one. */
export function checkStatusSentence(status: number): string {
  return `The provider answered with HTTP status ${String(status)}.`;
}

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
