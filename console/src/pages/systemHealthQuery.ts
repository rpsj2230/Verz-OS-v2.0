/**
 * What the System health section asks `brain.system_health_routes` for, and how the answer is read.
 * No React.
 *
 * **A guarantee is drawn as held only when the API says held.** A body that does not say, or says
 * anything else, is a guarantee that is not held: the one reading nobody should be handed by a
 * page that could not tell. The reason is the API's word, drawn as words here, and an unknown one
 * as itself.
 *
 * Task ids: M27.13.2, M27.15.54
 */

import type { components } from "../api/schema";

export type SystemHealthBody = components["schemas"]["SystemHealthView"];
export type GuaranteeRow = components["schemas"]["GuaranteeView"];
export type PartRow = components["schemas"]["PartView"];

/** Where the API keeps the screen. */
export const SYSTEM_HEALTH_API_PATH = "/console/system-health";

/** What each reason a control is not running reads as. */
export const BECAUSE_WORDS: Readonly<Record<string, string>> = {
  unreachable: "Nothing runs it",
  not_recorded: "Nothing records its runs",
  never_run: "It has never run",
  behind: "It is behind",
};

/** What each standing a part can have reads as. */
export const STANDING_WORDS: Readonly<Record<string, string>> = {
  ready: "Ready",
  not_ready: "Not ready",
  not_configured: "Not set up",
  unknown: "Cannot be told from here",
};

/** Read `SystemHealthView` out of a response body, or null when it is not one. */
export function readSystemHealth(payload: unknown): SystemHealthBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as {
    parts?: unknown;
    guarantees?: unknown;
    worker?: unknown;
  };
  if (
    !Array.isArray(body.parts) ||
    !Array.isArray(body.guarantees) ||
    typeof body.worker !== "object"
  ) {
    return null;
  }
  return payload as SystemHealthBody;
}

/** The standing in words, or the word itself for one this page does not know. */
export function standingWords(standing: string): string {
  return STANDING_WORDS[standing] ?? standing;
}

/** Whether a guarantee is held: only a literal true. */
export function isHeld(row: GuaranteeRow): boolean {
  return row.held === true;
}

/** Why a guarantee is not held, in words, or empty for one that is. */
export function becauseWords(row: GuaranteeRow): string {
  if (isHeld(row)) {
    return "";
  }
  const because = row.because ?? "";
  return (
    BECAUSE_WORDS[because] ??
    (because === "" ? "Not shown to be running" : because)
  );
}
