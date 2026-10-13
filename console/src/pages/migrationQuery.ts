/**
 * What the migration panel on the Features page asks for and says. No React.
 *
 * `brain.migration_routes` keeps the three documents a migration from another system is run on, the
 * register of what the old system holds, the comparison period and the cutover, checks each as it is
 * saved and says what is outstanding in it. **Nothing here reaches the old system**, and the panel
 * says so only while the API does (`nothing_reaches_the_old_system`). The API asks for
 * `admin:install_setting` over everything whatever the page drew.
 *
 * Task ids: M37.1.1.1, M37.1.1.2, M37.1.1.3, M37.1.3.2, M37.1.3.3, M37.1.4.1, M37.1.4.2,
 * M37.1.4.3, M37.1.4.4, M37.7.5
 */

import type { components } from "../api/schema";

export type WorkspaceBody = components["schemas"]["WorkspacePage"];
export type RegisterBody = components["schemas"]["RegisterView"];
export type ParallelBody = components["schemas"]["ParallelView"];
export type CutoverBody = components["schemas"]["CutoverView"];

/** Where the API keeps this panel. */
export const MIGRATION_API_PATH = "/migration";

export const MIGRATION_TITLE = "Migration from another system";
export const READING_MIGRATION = "Reading the migration records.";
export const UNREADABLE_MIGRATION =
  "The API answered in a shape this console does not read, so no migration record is listed. The console and the API are probably from different releases.";
export const NOTHING_REACHES_IT = "Nothing here reaches the old system: what is recorded is what a person tells it.";
export const SWITCHED_OFF =
  "Keeping a migration is switched off. Switch on Keep the records of a migration from another system in the list above to save one. What was saved can still be read.";
export const NOT_JSON = "That is not JSON, so nothing was sent.";
export const NOT_SAVED = "The record was not saved";
export const NOT_REPORTED = "The cutover was not reported";
export const NOTHING_SAVED = "Nothing has been saved yet.";

/** The three documents, the path each is saved to and what a person pastes into it. */
export interface Document {
  readonly key: "register" | "parallel" | "cutover";
  readonly title: string;
  readonly path: string;
  readonly label: string;
}

export const DOCUMENTS: readonly Document[] = [
  { key: "register", title: "What the old system holds", path: `${MIGRATION_API_PATH}/register`, label: "Register (JSON)" },
  { key: "parallel", title: "Both systems answering", path: `${MIGRATION_API_PATH}/parallel`, label: "Comparison period (JSON)" },
  { key: "cutover", title: "The cutover", path: `${MIGRATION_API_PATH}/cutover`, label: "Cutover record (JSON)" },
];

export const REPORT_COMPLETE = "Report the cutover complete";
export const COMPLETE_PATH = `${MIGRATION_API_PATH}/cutover/complete`;

/** One sentence on where a document stands, from what the API computed. */
export function standing(key: Document["key"], body: WorkspaceBody): string {
  if (key === "register") {
    return body.register.saved === null || body.register.saved === undefined
      ? NOTHING_SAVED
      : body.register.agreed
        ? "Every item is decided and every permission mapped."
        : `${body.register.gaps.length} still outstanding.`;
  }
  if (key === "parallel") {
    return body.parallel.saved === null || body.parallel.saved === undefined
      ? NOTHING_SAVED
      : body.parallel.may_cut_over
        ? "Every criterion is met: a cutover is allowed."
        : `${body.parallel.gaps.length} still stand between this and a cutover.`;
  }
  if (body.cutover.saved === null || body.cutover.saved === undefined) {
    return NOTHING_SAVED;
  }
  if (body.cutover.reported_complete !== null && body.cutover.reported_complete !== undefined) {
    return `Reported complete by ${body.cutover.reported_complete.by}.`;
  }
  return body.cutover.may_report_complete
    ? "Every act with a security consequence is recorded: it may be reported complete."
    : `${body.cutover.acts_outstanding.length} act(s) with a security consequence are unrecorded.`;
}

/** What is outstanding in a document, one finding to a line. */
export function findings(key: Document["key"], body: WorkspaceBody): readonly string[] {
  if (key === "register") {
    return body.register.gaps;
  }
  if (key === "parallel") {
    return [...body.parallel.gaps, ...body.parallel.unreviewed.map((one) => `Unreviewed disagreement: ${one}`)];
  }
  return [...body.cutover.acts_outstanding, ...body.cutover.gaps];
}

/** Read `brain.migration_routes.WorkspacePage`, or null for a shape this console does not read. */
export function readWorkspace(payload: unknown): WorkspaceBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { register?: unknown; parallel?: unknown; cutover?: unknown };
  return typeof body.register === "object" && typeof body.parallel === "object" && typeof body.cutover === "object"
    ? (payload as WorkspaceBody)
    : null;
}

/** The document a person pasted, or null when it is not a JSON object. */
export function readDocument(text: string): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(text);
    return typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}
