/**
 * What the Models and health screen asks four routes for, how their answers become its three
 * cards and its Advanced section, and the words for a provider's controls. No React.
 *
 * **The owner's screenshot is the design, and SCREEN 11 is not any more.** On 2026-09-22 he
 * called the screen "very complicated": about ten tables, and the failover matrix he had drawn on
 * 2026-09-03 (`.scratch/owner-imgs/0903_1.png`) nowhere on it. The screen is now three cards and a
 * closed Advanced section: Providers (one row each, a status in words, and the key, test and
 * switch on the row), the Failover matrix exactly as he drew it (Complexity, Step, Provider,
 * Model, Role), and Cost this month. Everything else the screen used to draw is under Advanced,
 * unchanged in behaviour, because nothing an administrator could do here was taken away.
 *
 * **Four requests, each to the route that owns the figure, and each card draws its own answer.**
 * The providers and the matrix are one answer, `GET /models/providers` (`brain.provider_routes`),
 * which is the plan the next call makes; the cost is `GET /report/spend` behind the usage grant;
 * the p95 under Advanced is `GET /report/service-levels` behind the same; and the figures only
 * this screen knows are `GET /operate/models` behind the models screen's own grant
 * (`brain.operate_routes`). A reader holding some and not others sees the cards they hold and the
 * API's refusal where they do not, which is `A_FIGURE_ANOTHER_ROUTE_SERVES_IS_READ_THERE` on
 * `brain.operate_routes`. `GET /routing/rungs` is no longer asked here: the matrix it drew was a
 * second copy of the steps the providers answer already carries, and the copy without health.
 *
 * **Levels, not tiers, and the words are the architecture note's.** `brain.models.routing.Tier`
 * says the architecture calls the three pools simple, medium and complex and the table calls them
 * small, main and heavy. The owner's screenshot uses the first set, so the screen does, through
 * `LEVEL_NAMES`; the tier stays the key in every request and every row.
 *
 * **The role is the API's, never worked out here.** A step's role is `brain.models.routing.
 * RungRole`, derived from its position and its provider against the level's default, and the
 * routing screen draws the same field (`matrixQuery.A_DERIVED_LABEL_IS_NEVER_AN_INPUT`). Working
 * it out again from the previous row would be a second derivation that disagrees with the first
 * the day a level alternates providers.
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
 * **No count of steps, levels or providers is rendered** beyond the share of requests answered
 * without a model, the fallbacks fired and each step's recent calls, which are over the whole
 * install and served only to a reader who may see all of it.
 *
 * Task ids: M27.2.3, M27.8.8, M5.7.1, M5.7.3
 */

import type { components } from "../api/schema";
import { when } from "./sessionsQuery";
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
  "something had called every rung. That is right for the router and wrong for a screen: a step " +
  "nothing has called would be drawn healthy on the strength of nobody having looked. So a step " +
  "the API marks unmeasured is drawn as not called yet, a provider none of whose steps has been " +
  "called is not used yet, and working or healthy is drawn only when attempts stand behind it.";

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

/** Where the API is told where answers are made, `brain.provider_routes.choose_profile`. */
export const PROFILE_API_PATH = "/models/profile";

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
 * How long a window the figures under Advanced read, in days. Seven, the old design's "Last 7
 * days", and the one window those figures are asked for so no two beside each other cover
 * different spans. The cost card reads the calendar month instead, which is what its heading says.
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
 * The first UTC day of the month `now` falls in, as the spend route reads a day.
 *
 * UTC and not the browser's own month, because `since` is a UTC day, the spend view's grain: a
 * browser east of Greenwich on the first of the month would otherwise ask from the month before.
 */
export function monthStart(now: Date): string {
  return `${now.toISOString().slice(0, 7)}-01`;
}

/** The request the cost card makes of the spend route: by department, from the first of the month. */
export function spendThisMonthApiPath(spendApiPath: string, dimension: string, now: Date): string {
  return `${spendApiPath}?dimension=${dimension}&${SINCE_PARAMETER}=${monthStart(now)}`;
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

// ------------------------------------------------------------------------ names and levels

/**
 * The built-in providers by the names a person knows them by. Every other provider is called by
 * the label its registry row carries, or by its slug when it has none. Held against
 * `brain.ops.provider_keys.PROVIDER_SLOTS` by a test, so a fifth built-in provider fails there.
 */
export const PROVIDER_NAMES: Readonly<Record<string, string>> = Object.freeze({
  anthropic: "Anthropic (Claude)",
  openai: "OpenAI",
  moonshot: "Moonshot (Kimi)",
  deepseek: "DeepSeek",
  local: "Local model",
});

/** One provider's name for a person, from this table, its registry label or its slug. */
export function providerName(provider: string, providers: readonly ProviderStateRow[] = []): string {
  return (
    PROVIDER_NAMES[provider] ?? providers.find((one) => one.provider === provider)?.registered?.label ?? provider
  );
}

/**
 * The three ladder tiers by the architecture's names for them, which are the owner's. Held
 * against `brain.models.routing.TIER_LADDER` by a test.
 */
export const LEVEL_NAMES: Readonly<Record<string, string>> = Object.freeze({
  small: "Simple",
  main: "Medium",
  heavy: "Complex",
});

/** A tier's level name, or the tier itself for one this console has not heard of. */
export function levelName(tier: string): string {
  return LEVEL_NAMES[tier] ?? tier;
}

// ------------------------------------------------------------------------ the providers card

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

// ------------------------------------------------------------------ where answers are made

/** The heading of the control that chooses the profile, in the owner's words rather than the setting's. */
export const WHERE_ANSWERS_ARE_MADE = "Where answers are made";

/** Each profile as a person chooses it. */
export const PROFILE_WORDS: Readonly<Record<string, string>> = Object.freeze({
  local: "On this server only",
  hosted: "Online providers",
});

/** The other profile, which is the one the control offers. */
export function otherProfile(profile: string): string {
  return profile === HOSTED_PROFILE ? LOCAL_PROFILE : HOSTED_PROFILE;
}

/** What the current profile means, in one sentence under the heading. */
export function profileNowSentence(profile: string): string {
  return profile === HOSTED_PROFILE
    ? "Questions may be sent to the online providers below that are turned on and hold a key."
    : "No question leaves this server, so the online providers below are not used, whatever their keys.";
}

/** The button that offers the other profile. */
export function chooseProfileLabel(profile: string): string {
  return profile === HOSTED_PROFILE ? "Use online providers" : "Keep answers on this server";
}

/** The confirmation's question for choosing `profile`. */
export function profileQuestion(profile: string): string {
  return profile === HOSTED_PROFILE ? "Send questions to online providers?" : "Keep answers on this server only?";
}

/**
 * What choosing `profile` does. The online direction says what leaves the server and to whom,
 * because that is the decision: the text of a question and the passages found for it.
 */
export function profileConsequence(profile: string): string {
  return profile === HOSTED_PROFILE
    ? "From the next question, the text of a question and the passages found for it may be sent " +
        "to the online providers below that are turned on and hold a key. Each provider's region, " +
        "retention and training terms are on its own page."
    : "From the next question, no text leaves this server. The online providers below stop being " +
        "used, and a question that needs a model goes unanswered unless one runs on this server.";
}

/** Said once the choice is saved, above the card the API's new plan is drawn in. */
export function profileChosenSentence(profile: string): string {
  return `Answers are now made by ${(PROFILE_WORDS[profile] ?? profile).toLowerCase()}.`;
}

/** The one field the write carries, `brain.provider_routes.ProfileAsked`. */
export function profileBody(profile: string): { readonly profile: string } {
  return { profile };
}

// ------------------------------------------------------------------ the providers' statuses

/** How a provider is doing, as one of seven words, each with the pill's text. */
export type ProviderStatusKind = "off" | "no_key" | "server_only" | "key_refused" | "resting" | "unused" | "working";

export interface ProviderStatus {
  readonly kind: ProviderStatusKind;
  readonly label: string;
}

export const TURNED_OFF = "Turned off";
export const NO_KEY = "No key";
export const KEY_SAVED = "Key saved";
export const SERVER_ONLY = "Not used: this server only";
export const KEY_REFUSED = "Key refused by the provider";

/**
 * One provider's status pill, from its switch, the key this server holds, where answers are made
 * and the health of its steps that answer.
 *
 * In that order, because each hides the next: a provider switched off is not called whatever its
 * key, one with no key is not called whatever the profile, and an online provider on an install
 * keeping answers on its own server is not called whatever its health. A provider none of whose
 * answering steps has been called is "not used yet" and never "working", which is
 * `AN_UNCALLED_RUNG_IS_NOT_A_HEALTHY_ONE` said about the provider rather than the step.
 * The key is `key_held`, the fact that decides whether its steps answer, and not the vault's.
 * A step whose latest call the provider refused as a key is never "working", whatever its
 * breaker says (`brain.provider_routes.A_REFUSED_KEY_IS_NOT_A_HEALTHY_PROVIDER`).
 */
export function providerStatus(
  row: ProviderStateRow,
  steps: readonly RungStateRow[],
  profile: string = HOSTED_PROFILE,
): ProviderStatus {
  if (!row.switched_on) {
    return { kind: "off", label: TURNED_OFF };
  }
  if (row.key_held === false) {
    return { kind: "no_key", label: NO_KEY };
  }
  if (row.hosted && profile !== HOSTED_PROFILE) {
    return { kind: "server_only", label: SERVER_ONLY };
  }
  const answering = steps.filter((one) => one.provider === row.provider && one.enabled && one.answers);
  if (answering.some((one) => one.key_refused === true)) {
    return { kind: "key_refused", label: KEY_REFUSED };
  }
  const [kind, words] = answering.some((one) => one.measured && one.state !== "closed")
    ? (["resting", "resting after errors"] as const)
    : answering.some((one) => one.measured)
      ? (["working", "working"] as const)
      : (["unused", "not used yet"] as const);
  // A provider needing no key has nothing saved, so its status is the health alone.
  const label = row.key_held === true ? `${KEY_SAVED}, ${words}` : `${words.charAt(0).toUpperCase()}${words.slice(1)}`;
  return { kind, label };
}

export const ADD_KEY = "Add key";
export const REPLACE_KEY = "Replace key";

/**
 * Whether a provider's key action replaces a key or adds the first one. Either fact counts: a key
 * this server holds from its environment and a key the vault holds for the next start are both a
 * key the new one replaces.
 */
export function keyAction(row: ProviderStateRow): string {
  return row.key_held === true || row.credential?.held === true ? REPLACE_KEY : ADD_KEY;
}

/**
 * When the vault took this provider's key, for a reader the API sent the vault's column to, or
 * null. Said beside the status because "which keys did I save" is answered by the vault, while the
 * status is what this server holds; after a save the two can differ for a minute, and both are true.
 */
export function vaultKeyLine(row: ProviderStateRow): string | null {
  const vault = row.credential;
  if (vault === null) {
    return null;
  }
  if (vault.held === null) {
    return VAULT_NOT_KNOWN;
  }
  if (!vault.held) {
    return "No key in the vault";
  }
  return vault.set_at === null ? "Key in the vault" : `Key in the vault since ${when(vault.set_at)}`;
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
  "which is what decides whether its steps answer here. No key is ever shown.";

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

// ------------------------------------------------------------------------ the failover matrix

/** The Role column's words for `brain.models.routing.RungRole`, held against it by a test. */
export const ROLE_WORDS: Readonly<Record<string, string>> = Object.freeze({
  primary: "default",
  same_provider_failover: "next model, same provider",
  cross_provider_failover: "next provider",
});

/** The role that is drawn as the default pill rather than as words. */
export const DEFAULT_ROLE = "primary";

/** Why a step does not answer the next call, as one of seven words, each with its marker's text. */
export type StepMarkerKind =
  | "paused"
  | "turned_off"
  | "no_key"
  | "local_only"
  | "cannot_call"
  | "resting"
  | "key_refused";

export interface StepMarker {
  readonly kind: StepMarkerKind;
  readonly label: string;
}

/** Each `brain.models.assembly.RungSkip` as the step's marker. Held against the enum by a test. */
export const SKIPPED_MARKERS: Readonly<Record<string, StepMarker>> = Object.freeze({
  switched_off: { kind: "turned_off", label: "provider turned off" },
  no_key: { kind: "no_key", label: "no key" },
  local_profile: { kind: "local_only", label: "not sent online" },
  no_transport: { kind: "cannot_call", label: "cannot be called" },
  no_inference_server: { kind: "cannot_call", label: "no server address" },
});

export const PAUSED: StepMarker = Object.freeze({ kind: "paused", label: "paused on the routing screen" });
export const RESTING_MARKER: StepMarker = Object.freeze({ kind: "resting", label: "resting after errors" });
export const KEY_REFUSED_MARKER: StepMarker = Object.freeze({ kind: "key_refused", label: "key refused" });

/**
 * The marker a step carries when it will not answer the next call, or null when it will.
 *
 * Quiet by default, as the owner's screenshot is: a step that answers says nothing beyond its
 * role. A step nothing has called is not marked, because not having been called is not a fault.
 */
export function stepMarker(step: RungStateRow): StepMarker | null {
  if (!step.enabled) {
    return PAUSED;
  }
  if (!step.answers) {
    return SKIPPED_MARKERS[step.skipped_because ?? ""] ?? { kind: "cannot_call", label: "not answering" };
  }
  if (step.key_refused === true) {
    return KEY_REFUSED_MARKER;
  }
  if (step.measured && step.state === "open") {
    return RESTING_MARKER;
  }
  return null;
}

/** One row of the failover matrix, as the owner drew it. */
export interface MatrixRow {
  readonly key: string;
  readonly tier: string;
  /** The level's name on the first row of its group, and null on every row after it. */
  readonly level: string | null;
  /** From 1, in the order the level tries its steps. Null on a level with no step. */
  readonly step: number | null;
  readonly provider: string;
  readonly model: string;
  readonly role: string;
  readonly marker: StepMarker | null;
}

export const NO_STEP_FOR_THE_LEVEL = "No model is set up for this level.";

/**
 * The matrix's rows: each ladder level in the order the API lists them, its steps by position
 * whatever order they arrived in, and a level with no step as one row saying so.
 *
 * The levels are the providers answer's `tiers`, which are `TIER_LADDER`, so a level nobody has
 * set up is drawn rather than left out: a missing group reads as a level that cannot be asked.
 */
export function matrixRows(body: ProvidersBody): MatrixRow[] {
  const rows: MatrixRow[] = [];
  // Tolerated when absent, which only a body older than the field can be: a page that fell over
  // on it would lose every card, and the steps still carry their own level.
  const tiers = (body.tiers as ProvidersBody["tiers"] | undefined)?.map((one) => one.tier) ?? [];
  // A step naming a tier the API did not list is drawn after the ones it did, never dropped.
  for (const step of body.rungs) {
    if (!tiers.includes(step.tier)) {
      tiers.push(step.tier);
    }
  }
  for (const tier of tiers) {
    const steps = body.rungs
      .filter((one) => one.tier === tier)
      .slice()
      .sort((a, b) => a.position - b.position);
    if (steps.length === 0) {
      rows.push({
        key: `${tier}-none`,
        tier,
        level: levelName(tier),
        step: null,
        provider: NO_STEP_FOR_THE_LEVEL,
        model: "",
        role: "",
        marker: null,
      });
      continue;
    }
    steps.forEach((one, index) => {
      rows.push({
        key: one.rung_id,
        tier,
        level: index === 0 ? levelName(tier) : null,
        step: index + 1,
        provider: providerName(one.provider, body.providers),
        model: one.model,
        role: one.role,
        marker: stepMarker(one),
      });
    });
  }
  return rows;
}

/**
 * A step's number within its level, from 1, in the order the level tries its steps: the Step
 * column of the owner's matrix. Worked out from the positions rather than drawn as one, because a
 * position is the ladder's index and a level whose first step was removed starts at 1, not 0.
 */
export function stepNumber(step: { readonly tier: string; readonly position: number }, steps: readonly { readonly tier: string; readonly position: number }[]): number {
  return steps.filter((one) => one.tier === step.tier && one.position < step.position).length + 1;
}

/** A role in words; an unknown role keeps the API's own spelling. */
export function roleWords(role: string): string {
  return ROLE_WORDS[role] ?? role;
}

export const LEVELS_CANNOT_ANSWER = "Not every level can answer";

/** One level the API names as exhausted. */
export function exhaustedSentence(tier: string): string {
  return (
    `The ${levelName(tier)} level cannot answer: every step on it is resting after recent failures, ` +
    "so a question needing it fails until one recovers."
  );
}

// ------------------------------------------------------------------------ under Advanced

export const ANSWERS_NOW = "Answers";
export const STEP_PAUSED = "Paused on the routing screen";

/**
 * Whether a step answers the next call, in words: paused, answering, or the API's own sentence
 * for why it is left out.
 */
export function answersWords(step: RungStateRow): string {
  if (!step.enabled) {
    return STEP_PAUSED;
  }
  if (step.answers) {
    return ANSWERS_NOW;
  }
  return step.told ?? NOT_ANSWERING;
}

/** A step left out with no sentence from the API, which the route does not send and a release might. */
export const NOT_ANSWERING = "Does not answer the next call.";

export const NOT_CALLED_YET = "Not called yet, so there is no health to show";
export const KEY_REFUSED_HEALTH = "The provider refused the key on the latest call";
export const HEALTHY = "Healthy";
export const RECOVERING = "Recovering: the next call to it is a test";
export const RESTING = "Resting after failures";

/** Why a step started resting, by `brain.models.routing.FallbackTrigger` value. */
export const UNHEALTHY_BECAUSE: Readonly<Record<string, string>> = Object.freeze({
  connection_error: "the provider could not be reached",
  timeout: "the provider did not answer in time",
  rate_limited: "the provider asked for fewer requests",
  provider_error: "the provider reported a fault on its side",
  circuit_open: "it was already resting",
  context_exceeded: "a request did not fit the model's window",
});

/**
 * One step's health in words. See `AN_UNCALLED_RUNG_IS_NOT_A_HEALTHY_ONE`: an unmeasured step is
 * not called yet whatever state the API sends beside it.
 */
export function healthWords(step: RungStateRow): string {
  if (step.key_refused === true) {
    return KEY_REFUSED_HEALTH;
  }
  if (!step.measured) {
    return NOT_CALLED_YET;
  }
  switch (step.state) {
    case "closed":
      return HEALTHY;
    case "half_open":
      return RECOVERING;
    case "open": {
      if (step.unhealthy_because === null) {
        return RESTING;
      }
      return `${RESTING}: ${UNHEALTHY_BECAUSE[step.unhealthy_because] ?? step.unhealthy_because}`;
    }
  }
}

/** A step's recent calls, as the API counted them. */
export function recentCalls(step: RungStateRow): string {
  const calls = step.live_seen === 1 ? "recent call" : "recent calls";
  return `${String(step.live_seen)} ${calls}, ${String(step.live_failed)} failed`;
}

export const NO_PROVIDER = "No provider is listed.";
export const NO_STEP_ON_THE_MATRIX =
  "No step is on the failover matrix, so no question can be answered by a model.";

// ------------------------------------------------------------------------ the row controls

export const TURN_ON = "Turn on";
export const TURN_OFF = "Turn off";
export const KEEP_IT_AS_IT_IS = "Keep it as it is";
export const TEST = "Test";
export const SEND_THE_TEST = "Send the test";
export const DO_NOT_TEST = "Do not test";

/** The confirmation's question for a switch, naming the provider as a person knows it. */
export function switchQuestion(name: string, on: boolean): string {
  return `Turn ${on ? "on" : "off"} ${name}?`;
}

/** What a switch does, in each direction, naming the provider. */
export function switchConsequence(name: string, on: boolean): string {
  if (on) {
    return (
      `From the next call, in every server process, steps naming ${name} may answer again ` +
      "where a key is held and the model profile allows it."
    );
  }
  return (
    `From the next call, in every server process, no question is sent to ${name}. Its steps ` +
    "leave the failover matrix, and a level with no other step that answers cannot answer."
  );
}

/** Said once the switch has been made, above the card the API's new plan is drawn in. */
export function switchedSentence(name: string, on: boolean): string {
  return `${name} is now turned ${on ? "on" : "off"}.`;
}

/** The confirmation's question for a test, naming the provider. */
export function checkQuestion(name: string): string {
  return `Test ${name}?`;
}

/** What a test does. See `A_CHECK_SPENDS_TOKENS_SO_IT_IS_CONFIRMED`. */
export function checkConsequence(name: string): string {
  return (
    `This sends one short fixed sentence to ${name}, through its first step that answers or, when ` +
    "no step uses it yet, through its default model. It costs a few tokens and is recorded under " +
    "your name. The provider's reply is not shown."
  );
}

/** The heading over a test's outcome. */
export function checkHeading(name: string): string {
  return `Test of ${name}`;
}

/**
 * What a test that answered cost, as the API measured it. Which model answered is the API's own
 * sentence (`told`), and the deployment id is not drawn: the owner's screen names a model.
 */
export function checkServedSentence(check: CheckBody): string {
  return `It used ${String(check.tokens_in ?? 0)} tokens in and ${String(check.tokens_out ?? 0)} tokens out.`;
}

/** The provider's status on a test that failed with one. */
export function checkStatusSentence(status: number): string {
  return `The provider answered with HTTP status ${String(status)}.`;
}

// ------------------------------------------------------------------------ cost this month

/** One department's line in the cost card, with its share of the total the API sent. */
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
