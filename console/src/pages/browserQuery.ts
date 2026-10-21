/**
 * What the browser panel on the Features page asks for and says. No React.
 *
 * `brain.browser_routes` answers which websites an agent's browser may be pointed at, which
 * permissions are signed for them and whether declaring and signing are switched on, and it moves
 * each only through the API, which asks for `admin:browser` over everything whatever the page drew.
 * Nothing here decides who may: a reader the API refuses sees the API's refusal.
 *
 * **Declaring a website opens no browser.** The sentence is a field on the answer
 * (`runs_are_on`), so it leaves the page in the commit that makes it false.
 *
 * Task ids: M19.2.4, M19.6.7, M19.7.3, M19.9.7
 */

import type { components } from "../api/schema";

export type BrowserBody = components["schemas"]["BrowserPage"];
export type TargetRow = components["schemas"]["BrowserTargetView"];
export type GrantRow = components["schemas"]["BrowserGrantView"];

/** Where the API keeps this panel. */
export const BROWSER_API_PATH = "/install/browser";
export const TARGETS_API_PATH = `${BROWSER_API_PATH}/targets`;
export const EXCEPTIONS_API_PATH = `${BROWSER_API_PATH}/exceptions`;
export const EXEMPTIONS_API_PATH = `${BROWSER_API_PATH}/exemptions`;

export const BROWSER_TITLE = "Websites for agents' browsers";
export const READING_BROWSER = "Reading which websites are declared.";
export const NO_TARGETS = "No website is declared on this install.";
export const NO_TARGETS_TITLE = "No websites declared";
export const NO_GRANTS = "No exception or exemption is in force.";
export const NO_GRANTS_TITLE = "No permissions signed";
export const UNREADABLE_BROWSER =
  "The API answered in a shape this console does not read, so no website is listed. The console " +
  "and the API are probably from different releases.";
export const SWITCHED_OFF =
  "Declaring websites and signing permissions is switched off. Switch on Declare websites for agents' browsers and sign exceptions in the list above. A website already declared can still be retired and a permission revoked.";
export const OPENS_NO_BROWSER =
  "Declaring a website does not let an agent open it. Agents run a browser only when Let agents run a browser is switched on.";
export const NOT_CHANGED = "That was not changed";
export const NOT_JSON = "That is not JSON, so nothing was sent.";
export const DECLARE = "Declare website";
export const DECLARATION_LABEL = "Declaration (JSON)";
export const SIGN_EXCEPTION = "Sign exception";
export const SIGN_EXEMPTION = "Sign exemption";
export const UNREADABLE_HEADING = "Declarations this release cannot read";

/** The API route one retirement or revocation is posted to. */
export function retirePath(name: string): string {
  return `${TARGETS_API_PATH}/${encodeURIComponent(name)}/retire`;
}

export function revokePath(seq: number): string {
  return `${BROWSER_API_PATH}/grants/${String(seq)}/revoke`;
}

/** Read `brain.browser_routes.BrowserPage`, or null for a shape this console does not read. */
export function readBrowser(payload: unknown): BrowserBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { targets?: unknown; grants?: unknown };
  if (!Array.isArray(body.targets) || !Array.isArray(body.grants)) {
    return null;
  }
  return payload as BrowserBody;
}

/** The declaration a person pasted, or null when it is not a JSON object. */
export function readDeclaration(text: string): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(text);
    return typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

/** A whole number of days in the range the API accepts, or null. */
export function readDays(text: string, most: number): number | null {
  const days = Number(text);
  return Number.isInteger(days) && days >= 1 && days <= most ? days : null;
}

/** What a permission is for, in the words the list uses. */
export function grantSentence(row: GrantRow): string {
  return row.kind === "exception"
    ? `Writes on ${row.target} ${row.what} run without waiting for a person`
    : `Skill ${row.what} may drive ${row.target}`;
}
