/**
 * What the template pages ask the API for when a version is withdrawn, put back, exported or
 * imported, and how an answer is read. No React.
 *
 * **Who may do any of it is the API's, and a refusal here is a page that draws nothing.** Every
 * route answers a person without the install authority over the company as it answers a version
 * nobody published, so a page cannot tell "not yours" from "not there" and does not try: a failed
 * read of a version's state hides the whole card, which is also what a reader who may only install
 * should see.
 *
 * **Nothing here counts anything.** The list of withdrawn versions is the versions withdrawn, and
 * the page does not say how many templates there are or how many agents were installed from one.
 *
 * Task ids: M27.15.35
 */

import type { components } from "../../api/schema";

export type WithdrawalState = components["schemas"]["TemplateWithdrawalView"];
export type WithdrawnVersions = components["schemas"]["WithdrawnVersionsView"];
export type WithdrawnVersion = components["schemas"]["WithdrawnVersionView"];
export type ImportReading = components["schemas"]["TemplateImportView"];

/** Where the versions withdrawn now are asked for, under the API base. */
export const WITHDRAWN_API_PATH = "/agent-template-withdrawals";

/** Where a template document is read and, with its digest, added, under the API base. */
export const IMPORT_API_PATH = "/agent-template-imports";

const TEMPLATES = "/agent-templates";

function versionPath(templateId: string, version: number): string {
  return `${TEMPLATES}/${encodeURIComponent(templateId)}/versions/${String(version)}`;
}

/** One version's state and history, and where it is withdrawn from. */
export function withdrawalApiPath(templateId: string, version: number): string {
  return `${versionPath(templateId, version)}/withdrawal`;
}

/** Where a withdrawal is undone. */
export function undoApiPath(templateId: string, version: number): string {
  return `${withdrawalApiPath(templateId, version)}/undo`;
}

/** Where one version is exported as a document. */
export function exportApiPath(templateId: string, version: number): string {
  return `${versionPath(templateId, version)}/export`;
}

/** The file a version is saved as. */
export function exportFileName(templateId: string, version: number): string {
  return `${templateId}-v${String(version)}.template.json`;
}

function isObject(payload: unknown): payload is Record<string, unknown> {
  return typeof payload === "object" && payload !== null;
}

/** Read `TemplateWithdrawalView`, or null for any other body. */
export function readWithdrawal(payload: unknown): WithdrawalState | null {
  if (!isObject(payload)) {
    return null;
  }
  return typeof payload["withdrawn"] === "boolean" && Array.isArray(payload["changes"]) && typeof payload["may_undo"] === "boolean"
    ? (payload as unknown as WithdrawalState)
    : null;
}

/** Read `WithdrawnVersionsView`, or null for any other body. Entries that name no template are left out. */
export function readWithdrawn(payload: unknown): readonly WithdrawnVersion[] | null {
  if (!isObject(payload) || !Array.isArray(payload["versions"])) {
    return null;
  }
  return (payload["versions"] as readonly WithdrawnVersion[]).filter(
    (one) => typeof one.template_id === "string" && typeof one.version === "number",
  );
}

/** Read `TemplateImportView`, or null for any other body. */
export function readImport(payload: unknown): ImportReading | null {
  if (!isObject(payload)) {
    return null;
  }
  return typeof payload["template_id"] === "string" && typeof payload["content_digest"] === "string" && typeof payload["imported"] === "boolean"
    ? (payload as unknown as ImportReading)
    : null;
}

/** The document a person pasted, as an object, or null when it is not JSON that is an object. */
export function parseDocument(text: string): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(text);
    return isObject(parsed) && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}
