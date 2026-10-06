/**
 * What the Incidents screen asks `brain.incident_routes` for, and how the answer is read. No React.
 *
 * **What a source blocks is the API's list or the API's sentence, never an empty cell.** The route
 * sends the tools a degraded source takes with it, or, for a source this release cannot rebuild the
 * declaration of, a sentence saying why they cannot be named; the model refuses both and neither, so
 * this module draws whichever came and never a dash beside a source that is down.
 *
 * **No list is drawn over nothing.** A process that could not read what the worker last found sends
 * `unread`, and the page says that sentence instead of "Nothing is degraded", which would be the
 * reassuring answer from a process that looked at nothing.
 *
 * Task ids: M27.2.7
 */

import type { components } from "../api/schema";

export type IncidentsBody = components["schemas"]["IncidentsView"];
export type IncidentRow = components["schemas"]["IncidentView"];

/** Where the API keeps the screen. */
export const INCIDENTS_API_PATH = "/console/incidents";

/** The console address and the menu's label. */
export const INCIDENTS_PATH = "/incidents";
export const INCIDENTS_LABEL = "Incidents";

/** What each state the worker can leave reads as. */
export const STATE_WORDS: Readonly<Record<string, string>> = {
  degraded: "Slow or partly failing",
  down: "Not answering",
};

/** Read `IncidentsView` out of a response body, or null when it is not one. */
export function readIncidents(payload: unknown): IncidentsBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { items?: unknown; told?: unknown };
  if (!Array.isArray(body.items) || typeof body.told !== "string") {
    return null;
  }
  return payload as IncidentsBody;
}

/** The state the worker left, in words, or the word itself for one this page does not know. */
export function stateWords(state: string): string {
  return STATE_WORDS[state] ?? state;
}

/** What stops working, in words: the tools by name, or the API's sentence when they cannot be named. */
export function blocksWords(row: IncidentRow): string {
  return row.blocks.length === 0 ? (row.blocks_unknown ?? "") : row.blocks.join(", ");
}
