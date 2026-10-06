/**
 * What the Audit log asks for its refusal and redaction statistics, and how the answer is read.
 * No React.
 *
 * **Every figure is the API's.** `brain.audit_statistics_routes` counts over the window it loaded
 * and the reader's own view of it, through `brain.console.auditor`, and this module reads what was
 * sent and adds nothing: no sum across shapes, no share, and no line for anything not sent. A shape
 * the reader may not be told is absent from the answer rather than sent at zero, and the page draws
 * the absence as nothing.
 *
 * **The reader's own entries are never in it.** The API counts other people's entries inside the
 * reader's audit reach only (`brain.console.auditor.A_READER_IS_NEVER_COUNTED_WHAT_WAS_KEPT_FROM_THEM`),
 * and the page says so, because a reader who finds their own refusal missing should know it was
 * left out on purpose.
 *
 * **Nothing names what was refused or which field was withheld**, because nothing sent could: a
 * shape, its sentence and a count, and one number of entries that carried a redaction.
 *
 * Task ids: M33.4.1.3
 */

import type { components } from "../../api/schema";

/** `brain.audit_statistics_routes.AuditStatisticsView`. */
export type AuditStatisticsBody = components["schemas"]["AuditStatisticsView"];
/** One shape of refusal. */
export type RefusalShapeBody = components["schemas"]["RefusalShapeView"];

/** Where the API keeps the statistics: `brain.audit_statistics_routes.STATISTICS_PATH`. */
export const AUDIT_STATISTICS_API_PATH = "/audit/statistics";

export const STATISTICS_HEADING = "Refusals and redactions";
export const STATISTICS_LEDE = "The last seven days, over other people's entries you may read. Your own entries are never counted.";
export const REDACTED_LABEL = "Entries with a detail withheld";
export const NO_PATTERN = "No pattern of refusals you may be told about.";
export const UNREADABLE_STATISTICS = "The statistics could not be read.";

function readShape(value: unknown): RefusalShapeBody | null {
  if (typeof value !== "object" || value === null) {
    return null;
  }
  const one = value as Record<string, unknown>;
  if (typeof one["shape"] !== "string" || typeof one["reads_as"] !== "string" || typeof one["occurrences"] !== "number") {
    return null;
  }
  return value as RefusalShapeBody;
}

/** The statistics as sent, or null for a body this page cannot read. */
export function readStatistics(payload: unknown): AuditStatisticsBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as Record<string, unknown>;
  const refusals = body["refusals"];
  if (
    typeof body["since"] !== "string" ||
    typeof body["until"] !== "string" ||
    !Array.isArray(refusals) ||
    !refusals.every((one) => readShape(one) !== null) ||
    typeof body["redacted_entries"] !== "number" ||
    typeof body["read_at_most"] !== "number"
  ) {
    return null;
  }
  return payload as AuditStatisticsBody;
}

/** How often, in words. */
export function timesWords(occurrences: number): string {
  return occurrences === 1 ? "once" : `${String(occurrences)} times`;
}
