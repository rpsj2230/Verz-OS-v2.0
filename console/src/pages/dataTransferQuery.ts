/**
 * What the Import and export screen asks `brain.data_transfer_routes` for and sends it, and how the
 * answers are read. No React.
 *
 * **The window is whole days, in UTC.** The route takes two instants and exports every audit entry
 * at or after the first and before the second; a person chooses a first and a last day, and the
 * second instant is the start of the day after the last, so the last day chosen is included whole.
 *
 * **The document is saved as a file and kept nowhere else.** The route answers with it once;
 * `saveDocument` hands it to the browser as a download and keeps no copy in the page's state beyond
 * the moment it is saved. A browser with no way to make a file from memory is told so rather than
 * shown the document on the screen.
 *
 * **A readable export is described by what it is, never by numbers it does not have.** An export of
 * the entries its exporter could read has no window of sequence numbers and no verdict, because the
 * API records neither (`brain.tables.data_export.A_READABLE_EXPORT_NAMES_NO_WINDOW`). Its row says
 * so in words rather than drawing an empty window or a verdict of broken, which would read as a
 * ledger somebody tampered with.
 *
 * Task ids: M27.8.16, M27.9.4
 */

import type { components } from "../api/schema";

export type DataTransferBody = components["schemas"]["DataTransferView"];
export type DataSetRow = components["schemas"]["DataSetView"];
export type ExportRecordRow = components["schemas"]["ExportRecordView"];
export type ExportBody = components["schemas"]["ExportAsked"];

/** Where the API keeps the screen, and the one write beneath it. */
export const DATA_TRANSFER_API_PATH = "/data-transfer";
export const EXPORTS_API_PATH = "/data-transfer/exports";

/** The console address and the menu's label. */
export const DATA_TRANSFER_PATH = "/import-export";
export const DATA_TRANSFER_LABEL = "Import and export";

/** The one data set an export can be taken of today. */
export const AUDIT_TRAIL = "audit_trail";

/** Read `DataTransferView` out of a response body, or null when it is not one. */
export function readDataTransfer(payload: unknown): DataTransferBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { catalogue?: unknown; reasons?: unknown; exports?: unknown };
  if (!Array.isArray(body.catalogue) || !Array.isArray(body.reasons) || !Array.isArray(body.exports)) {
    return null;
  }
  return payload as DataTransferBody;
}

/** Each reason for an export, in words. A reason with no words here is shown as the API sent it. */
export const REASON_LABELS: Readonly<Record<string, string>> = Object.freeze({
  legal_discovery: "Legal discovery",
  regulatory_request: "A regulator's request",
  internal_investigation: "An internal investigation",
  subject_access_request: "A subject access request",
  litigation_hold_collection: "Collection under a litigation hold",
  system_migration: "Moving to another system",
});

export function reasonLabel(reason: string): string {
  return REASON_LABELS[reason] ?? reason;
}

/** The two instants a window of whole days covers, or null when either day is not a date. */
export function windowOf(firstDay: string, lastDay: string): { since: string; until: string } | null {
  const first = new Date(`${firstDay}T00:00:00Z`);
  const last = new Date(`${lastDay}T00:00:00Z`);
  if (Number.isNaN(first.getTime()) || Number.isNaN(last.getTime())) {
    return null;
  }
  const after = new Date(last.getTime() + 86_400_000);
  return { since: first.toISOString(), until: after.toISOString() };
}

/** The body an export sends: exactly the five fields the route declares. */
export function exportBody(
  reason: string,
  reference: string,
  window: { since: string; until: string },
): ExportBody {
  return {
    data_set: AUDIT_TRAIL,
    reason,
    reason_reference: reference,
    since: window.since,
    until: window.until,
  };
}

/** What the answer to an export carries: the record, the filename, the document and a sentence. */
export interface Taken {
  readonly export: ExportRecordRow;
  readonly filename: string;
  readonly document: string;
  readonly told: string;
}

export function readTaken(payload: unknown): Taken | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as Record<string, unknown>;
  if (
    typeof body["filename"] !== "string" ||
    typeof body["document"] !== "string" ||
    typeof body["told"] !== "string" ||
    typeof body["export"] !== "object" ||
    body["export"] === null
  ) {
    return null;
  }
  return payload as Taken;
}

/** Said when a browser cannot make a file from memory. */
export const CANNOT_SAVE =
  "This browser could not save the document as a file, and it is not shown on the screen. The " +
  "export is recorded; take it again from a browser that can save files.";

/**
 * Hand a document to the browser as a download. True when a file was offered.
 *
 * The object address is revoked as soon as the click has been dispatched, so nothing on the page
 * can reach the document after it is saved.
 */
export function saveDocument(filename: string, document: string, into: Document): boolean {
  if (typeof URL.createObjectURL !== "function") {
    return false;
  }
  const address = URL.createObjectURL(new Blob([document], { type: "application/x-ndjson" }));
  const link = into.createElement("a");
  link.href = address;
  link.download = filename;
  into.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(address);
  return true;
}

/** What the Window column says about an export of the entries its exporter could read. */
export const READABLE_WINDOW = "The entries you could read";

/** What the Chain column says: the chain's verdict, or that the export is not a chain. */
export const CHAIN_VERIFIED = "Verified";
export const CHAIN_BROKEN = "Broken; the document says where";
export const NOT_A_CHAIN = "Not a chain";

/** The window an export covered, in words. A readable export names no sequence numbers. */
export function windowSentence(row: ExportRecordRow): string {
  if (row.form === "readable") {
    return READABLE_WINDOW;
  }
  return row.first_seq === null ? "" : `Entries ${String(row.first_seq)} to ${String(row.last_seq)}`;
}

/** Whether an export's chain verified, or that it is not a chain and carries no verdict. */
export function chainSentence(row: ExportRecordRow): string {
  if (row.verified === null) {
    return NOT_A_CHAIN;
  }
  return row.verified ? CHAIN_VERIFIED : CHAIN_BROKEN;
}
