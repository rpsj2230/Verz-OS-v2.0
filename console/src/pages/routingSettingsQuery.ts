/**
 * The Models screen's routing settings: each tier's window and escalation headroom, the residency
 * constraints attached to scopes, and the chain-depth alerts the live path raised. No React.
 *
 * It reads nothing of its own. The providers answer (`brain.provider_routes.ProvidersView`) carries
 * `tiers`, `residency` and `depth_alerts` beside the chain, so the settings drawn are the ones the
 * next call is planned with, and every write (`brain.model_health_routes`) answers with that view
 * after it, which the health card draws from then on.
 *
 * **A tier's numbers are the router's, and a tier running at the product default says so.** The
 * API marks each tier `configured` or not; a tier with no row is drawn as the product's default
 * rather than as a setting somebody made, and resetting one retires its row.
 *
 * **A residency constraint is drawn as its scope and what it demands, in the grant tables' words.**
 * The scope is the clauses the API sent, rendered field by field, because a paraphrase written here
 * would be a second vocabulary for a structure that already has one.
 *
 * **An alert names a tier, a depth and the deployment that served, never a question**, which is the
 * API's rule and this module only draws it.
 *
 * Task ids: M5.2.2, M5.5.1, M5.4.8, M5.4.3
 */

import type { FieldProblem } from "../api/errors";

export interface TierSetting {
  readonly tier: string;
  readonly context_window: number;
  readonly escalation_headroom: number;
  readonly configured: boolean;
}

export interface ScopeClause {
  readonly field: string;
  readonly op: string;
  readonly value: string | readonly string[] | null;
}

export interface ResidencySetting {
  readonly id: string;
  readonly clauses: readonly ScopeClause[];
  readonly allowed_regions: readonly string[] | null;
  readonly on_prem_only: boolean;
  readonly note: string;
  readonly created_by: string;
  readonly created_at: string;
}

export interface DepthAlert {
  readonly raised_at: string;
  readonly level: string;
  readonly tier: string;
  readonly depth: number;
  readonly served_by: string | null;
  readonly reason: string;
  readonly trace_id: string;
}

export interface RoutingSettings {
  readonly editable: boolean;
  readonly tiers: readonly TierSetting[];
  readonly residency: readonly ResidencySetting[];
  readonly alerts: readonly DepthAlert[];
}

/** What a tier write sends, `brain.model_health_routes.TierRuleAsked`. */
export interface TierAsked {
  readonly context_window: number;
  readonly escalation_headroom: number | null;
}

/** What a residency write sends, `brain.model_health_routes.ResidencyAsked`. */
export interface ResidencyAsked {
  readonly scope: { readonly clauses: readonly ScopeClause[] };
  readonly allowed_regions: readonly string[] | null;
  readonly on_prem_only: boolean;
  readonly note: string;
}

// ------------------------------------------------------------------------------ the paths

const TIERS_API_PATH = "/models/tiers";
export const RESIDENCY_API_PATH = "/models/residency";

/** Where one tier's numbers are set. */
export function tierApiPath(tier: string): string {
  return `${TIERS_API_PATH}/${encodeURIComponent(tier)}`;
}

/** Where one tier's row is retired, so it runs at the product default. */
export function tierResetApiPath(tier: string): string {
  return `${tierApiPath(tier)}/reset`;
}

/** Where one residency constraint is retired. */
export function residencyRetireApiPath(id: string): string {
  return `${RESIDENCY_API_PATH}/${encodeURIComponent(id)}/retire`;
}

// ------------------------------------------------------------------------------ the reader

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function clausesOf(scope: unknown): ScopeClause[] {
  if (!isRecord(scope) || !Array.isArray(scope["clauses"])) {
    return [];
  }
  return scope["clauses"].flatMap((one: unknown) => {
    if (!isRecord(one) || typeof one["field"] !== "string" || typeof one["op"] !== "string") {
      return [];
    }
    const value = one["value"];
    const kept =
      typeof value === "string"
        ? value
        : Array.isArray(value)
          ? value.filter((entry): entry is string => typeof entry === "string")
          : null;
    return [{ field: one["field"], op: one["op"], value: kept }];
  });
}

/** The three settings out of a providers answer. Absent lists read as empty, never as a failure. */
export function readRoutingSettings(payload: unknown): RoutingSettings | null {
  if (!isRecord(payload)) {
    return null;
  }
  const tiers = Array.isArray(payload["tiers"]) ? payload["tiers"] : [];
  const residency = Array.isArray(payload["residency"]) ? payload["residency"] : [];
  const alerts = Array.isArray(payload["depth_alerts"]) ? payload["depth_alerts"] : [];
  return {
    editable: payload["editable"] === true,
    tiers: tiers.flatMap((one: unknown) =>
      isRecord(one) &&
      typeof one["tier"] === "string" &&
      typeof one["context_window"] === "number" &&
      typeof one["escalation_headroom"] === "number"
        ? [
            {
              tier: one["tier"],
              context_window: one["context_window"],
              escalation_headroom: one["escalation_headroom"],
              configured: one["configured"] === true,
            },
          ]
        : [],
    ),
    residency: residency.flatMap((one: unknown) =>
      isRecord(one) && typeof one["id"] === "string"
        ? [
            {
              id: one["id"],
              clauses: clausesOf(one["scope"]),
              allowed_regions: Array.isArray(one["allowed_regions"])
                ? one["allowed_regions"].filter((entry): entry is string => typeof entry === "string")
                : null,
              on_prem_only: one["on_prem_only"] === true,
              note: text(one["note"]),
              created_by: text(one["created_by"]),
              created_at: text(one["created_at"]),
            },
          ]
        : [],
    ),
    alerts: alerts.flatMap((one: unknown) =>
      isRecord(one) && typeof one["tier"] === "string" && typeof one["depth"] === "number"
        ? [
            {
              raised_at: text(one["raised_at"]),
              level: text(one["level"]),
              tier: one["tier"],
              depth: one["depth"],
              served_by: typeof one["served_by"] === "string" ? one["served_by"] : null,
              reason: text(one["reason"]),
              trace_id: text(one["trace_id"]),
            },
          ]
        : [],
    ),
  };
}

// ------------------------------------------------------------------------ the decisions

/** The window and headroom a person typed, as the body sent; headroom blank is the default. */
export function tierAsked(window: string, headroom: string): TierAsked {
  const fraction = headroom.trim() === "" ? null : Number(headroom.trim());
  return { context_window: Number(window.trim()), escalation_headroom: fraction };
}

/** A tier form with a blank window, as the problem a person is told beside it. */
export function blankTierProblems(window: string): FieldProblem[] {
  return window.trim() === ""
    ? [{ field: "context_window", code: "blank", message: "Say how many tokens this tier can hold." }]
    : [];
}

/** The scope a constraint is attached to: one department, or every row when none is named. */
export function scopeFor(department: string, wholeCompany: boolean): { clauses: ScopeClause[] } {
  return wholeCompany ? { clauses: [] } : { clauses: [{ field: "department", op: "eq", value: department.trim() }] };
}

/** The region names a person typed, comma separated, trimmed and without blanks. */
export function regionNames(regions: string): string[] {
  return regions
    .split(",")
    .map((one) => one.trim())
    .filter((one) => one !== "");
}

/** A constraint form left blank, as the problems a person is told beside each field. */
export function blankResidencyProblems(
  department: string,
  wholeCompany: boolean,
  regions: string,
  onPrem: boolean,
): FieldProblem[] {
  const found: FieldProblem[] = [];
  if (!wholeCompany && department.trim() === "") {
    found.push({
      field: "scope",
      code: "blank",
      message: "Name the department it applies to, or tick the whole company.",
    });
  }
  if (!onPrem && regionNames(regions).length === 0) {
    found.push({
      field: "allowed_regions",
      code: "blank",
      message: "List the regions it may be processed in, or tick on-prem only.",
    });
  }
  return found;
}

/** The body a constraint write sends. */
export function residencyAsked(
  department: string,
  wholeCompany: boolean,
  regions: string,
  onPrem: boolean,
  note: string,
): ResidencyAsked {
  const names = regionNames(regions);
  return {
    scope: scopeFor(department, wholeCompany),
    allowed_regions: names.length === 0 ? null : names,
    on_prem_only: onPrem,
    note: note.trim(),
  };
}

// ------------------------------------------------------------------------------ the words

export const ROUTING_SETTINGS_HEADING = "Routing settings";
export const ROUTING_SETTINGS_LEDE =
  "What decides which tier a question lands in and where it may be processed. Both take effect on " +
  "the next question, in every server process.";
export const TIERS_CAPTION = "Each tier's window and the share of it past which a question moves up";
export const RESIDENCY_HEADING = "Residency constraints";
export const RESIDENCY_LEDE =
  "A constraint is attached to a scope. A question from anybody whose access reaches that scope is " +
  "sent only to a model in an allowed region, and refused when there is none.";
export const RESIDENCY_CAPTION = "Each residency constraint and the scope it is attached to";
export const NO_RESIDENCY = "No residency constraint is set, so a question may go to any provider switched on.";
export const ALERTS_HEADING = "Chain depth alerts";
export const ALERTS_LEDE =
  "Raised when a question had to go past the first rung of its tier, whether or not it was answered: " +
  "an answer from a fallback means the primary is failing while nobody complains.";
export const ALERTS_CAPTION = "Chain depth alerts from the last day, newest first";
export const NO_ALERTS = "No question went past its primary in the last day.";
export const EDIT_NUMBERS = "Edit numbers";
export const SAVE_NUMBERS = "Save these numbers";
export const KEEP_NUMBERS = "Keep the numbers as they are";
export const RESET_TIER = "Use the product default";
export const KEEP_TIER = "Keep this tier's setting";
export const ADD_RESIDENCY = "Add this constraint";
export const DO_NOT_ADD_RESIDENCY = "Do not add it";
export const RETIRE_RESIDENCY = "Retire";
export const KEEP_RESIDENCY = "Keep the constraint";
export const PRODUCT_DEFAULT = "product default";
export const SET_HERE = "set here";
export const EVERY_ROW = "the whole company";

/** One scope in the grant tables' words: each clause, or the whole company for none. */
export function scopeWords(clauses: readonly ScopeClause[]): string {
  if (clauses.length === 0) {
    return EVERY_ROW;
  }
  return clauses
    .map((one) => {
      const value = one.value === null ? "" : typeof one.value === "string" ? one.value : one.value.join(", ");
      return `${one.field} ${one.op} ${value}`.trim();
    })
    .join(" and ");
}

/** What a constraint demands, in words. */
export function demandWords(row: ResidencySetting): string {
  const regions = row.allowed_regions === null ? "any region" : row.allowed_regions.join(", ");
  return row.on_prem_only ? `${regions}, on-prem only` : regions;
}

/** A headroom as a share of the window. */
export function headroomWords(fraction: number): string {
  return `${String(Math.round(fraction * 100))}%`;
}

export function tierQuestion(tier: string): string {
  return `Save the ${tier} tier's numbers?`;
}

export function tierConsequence(tier: string, asked: TierAsked): string {
  const headroom = asked.escalation_headroom === null ? "the product default" : headroomWords(asked.escalation_headroom);
  return (
    `From the next question, the ${tier} tier holds ${String(asked.context_window)} tokens and a question ` +
    `past ${headroom} of that moves to the next tier up. Every department's questions are routed by it.`
  );
}

export function resetQuestion(tier: string): string {
  return `Put the ${tier} tier back to the product default?`;
}

export const RESET_CONSEQUENCE =
  "The tier's row is retired and the next question is routed by the numbers the product shipped with.";

export function residencyQuestion(asked: ResidencyAsked): string {
  return `Attach a residency constraint to ${scopeWords(asked.scope.clauses)}?`;
}

export function residencyConsequence(asked: ResidencyAsked): string {
  const regions = asked.allowed_regions === null ? "any region" : asked.allowed_regions.join(", ");
  const where = asked.on_prem_only ? `${regions}, on the company's own hardware only` : regions;
  return (
    `From the next question, anybody whose access reaches ${scopeWords(asked.scope.clauses)} is sent only ` +
    `to a model in ${where}. A question with no such model is refused rather than sent elsewhere.`
  );
}

export function retireResidencyQuestion(row: ResidencySetting): string {
  return `Retire the constraint on ${scopeWords(row.clauses)}?`;
}

export const RETIRE_RESIDENCY_CONSEQUENCE =
  "Questions it held to its regions may go to any provider switched on from the next question. The " +
  "constraint stays on record as retired.";

/** A rung's probes, in the words of `recentCalls`, or that none has been sent. */
export function probeWords(probesSeen: number | undefined, probesFailed: number | undefined): string {
  const seen = probesSeen ?? 0;
  if (seen === 0) {
    return "not probed yet";
  }
  const noun = seen === 1 ? "probe" : "probes";
  return `${String(seen)} ${noun}, ${String(probesFailed ?? 0)} failed`;
}
