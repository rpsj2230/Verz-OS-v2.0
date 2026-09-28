/**
 * What the providers' pages say about a provider, in the owner's plain words: its last test, the
 * models it is used for, its figures and its history.
 *
 * **Every word is chosen from a value the API sent, never guessed.** A last test the API did not
 * send is "Not tested"; a figure it names as not recorded is "Not recorded yet" with its reason,
 * never nought (`kit/KpiStrip.tsx`); a history entry is drawn from the ledger's own change word,
 * and a word this console has not heard of is drawn as itself.
 *
 * **No principal id reaches page text.** The ledger names who acted by id, and a person reads
 * names; the ids are drawn under Advanced only, for quoting in a support request.
 *
 * Task ids: M27.16.1, M5.6.4
 */

import type { components } from "../../api/schema";
import type { ProviderStateRow, RungStateRow } from "../modelsQuery";

export type LastCheck = components["schemas"]["LastCheckView"];
export type ProviderStats = components["schemas"]["ProviderStatsView"];

export const NOT_TESTED = "Not tested";

/** A failed test's outcome as a few plain words. `brain.provider_routes.CHECK_TOLD`'s keys. */
export const TEST_OUTCOME_WORDS: Readonly<Record<string, string>> = Object.freeze({
  key_refused: "key refused",
  timeout: "no answer in time",
  connection_error: "could not be reached",
  rate_limited: "asked for fewer requests",
  provider_error: "a fault at the provider",
  circuit_open: "resting after failures",
  context_exceeded: "too long for the model",
  stopped: "turned down",
  refused: "declined the test sentence",
  no_model: "nothing to test with",
  out_of_rotation: "every step paused",
  switched_off: "turned off",
  no_key: "no key",
  local_profile: "answers stay on this server",
  no_transport: "cannot be called",
  no_inference_server: "no server address",
});

/** A day as a person reads it, in the reader's own calendar. */
export function dayWords(at: string): string {
  return new Date(at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

/** A provider's last test in words: how it ended, and the day. */
export function lastTestWords(check: LastCheck | null | undefined): string {
  if (check === null || check === undefined) {
    return NOT_TESTED;
  }
  if (check.answered) {
    return `Answered, ${dayWords(check.at)}`;
  }
  return `Failed: ${TEST_OUTCOME_WORDS[check.outcome] ?? check.outcome}, ${dayWords(check.at)}`;
}

/** The models a provider's steps use, once each, in the order a question tries them. */
export function modelsInUse(provider: string, steps: readonly RungStateRow[]): string[] {
  const seen: string[] = [];
  for (const step of steps) {
    if (step.provider === provider && !seen.includes(step.model)) {
      seen.push(step.model);
    }
  }
  return seen;
}

/** A provider's own steps, level by level in ladder order and by position within each. */
export function stepsOf(provider: string, steps: readonly RungStateRow[]): RungStateRow[] {
  const levels = ["small", "main", "heavy"];
  return steps
    .filter((one) => one.provider === provider)
    .slice()
    .sort((a, b) => {
      const byLevel = levels.indexOf(a.tier) - levels.indexOf(b.tier);
      return byLevel !== 0 ? byLevel : a.position - b.position;
    });
}

/** Whether this provider was added from the console, which is the only kind that can be retired. */
export function isAdded(row: ProviderStateRow): boolean {
  return row.registered?.kind === "openai_compatible";
}

/** The figure `brain.provider_routes.stats_view` names as not recorded, or undefined. */
export function unrecordedWhy(stats: ProviderStats | null, figure: string): string | undefined {
  return stats?.unrecorded.find((one) => one.figure === figure)?.why;
}

/** Read `ProviderStatsView`, or null for a body this console cannot read. */
export function readStats(payload: unknown): ProviderStats | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { provider?: unknown; days?: unknown; unrecorded?: unknown };
  if (typeof body.provider !== "string" || typeof body.days !== "number" || !Array.isArray(body.unrecorded)) {
    return null;
  }
  return payload as ProviderStats;
}

/** A count as a figure, or undefined when the API sent none, so the card says "not recorded". */
export function figure(value: number | null | undefined): string | undefined {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value.toLocaleString("en-GB") : undefined;
}

// ------------------------------------------------------------------------------ the history

/** One entry of a provider's history as the ledger sent it. */
export interface HistoryRow {
  readonly at: string;
  readonly actor: string;
  readonly subject: string;
  readonly change: string;
  readonly fields: string;
}

/** A registry column as a person names it. */
export const FIELD_WORDS: Readonly<Record<string, string>> = Object.freeze({
  processing_region: "processing region",
  residency_class: "residency",
  storage_location: "storage location",
  retention_terms: "retention terms",
  training_terms: "training terms",
  agreement_url: "agreement link",
  lane_overrides: "time allowed",
  models: "model names",
  label: "name",
  base_url: "address",
});

/** What one entry says happened, from the ledger's change word and the subject it was under. */
export function historyWords(row: HistoryRow): string {
  if (row.subject.startsWith("provider_check.")) {
    return "Tested";
  }
  switch (row.change) {
    case "switched_on":
      return "Turned on";
    case "switched_off":
      return "Turned off";
    case "registered":
      return "Terms recorded for the first time";
    case "changed": {
      const fields = row.fields
        .split(",")
        .filter((one) => one !== "")
        .map((one) => FIELD_WORDS[one] ?? one);
      return fields.length === 0 ? "Terms changed" : `Changed: ${fields.join(", ")}`;
    }
    case "retired":
      return "Retired";
    case "set":
      return "Set";
    default:
      return row.change;
  }
}

/**
 * The entries about this provider out of one page of the ledger: its switch's subject and its
 * last test's, exactly, whichever other subjects the search also matched.
 */
export function readHistory(payload: unknown, provider: string): HistoryRow[] {
  if (typeof payload !== "object" || payload === null) {
    return [];
  }
  const items = (payload as { items?: unknown }).items;
  if (!Array.isArray(items)) {
    return [];
  }
  const subjects = new Set([`provider.${provider}`, `provider_check.${provider}`]);
  const rows: HistoryRow[] = [];
  for (const item of items as readonly unknown[]) {
    if (typeof item !== "object" || item === null) {
      continue;
    }
    const entry = item as Record<string, unknown>;
    const details = (typeof entry["details"] === "object" && entry["details"] !== null ? entry["details"] : {}) as Record<
      string,
      unknown
    >;
    const subject = entry["subject_id"];
    if (typeof subject !== "string" || !subjects.has(subject) || typeof entry["at"] !== "string") {
      continue;
    }
    rows.push({
      at: entry["at"],
      actor: typeof entry["actor_id"] === "string" ? entry["actor_id"] : "",
      subject,
      change: typeof details["change"] === "string" ? details["change"] : "",
      fields: typeof details["fields"] === "string" ? details["fields"] : "",
    });
  }
  return rows;
}
