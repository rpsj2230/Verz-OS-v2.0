/**
 * What the Settings screen asks `brain.settings_routes` for, and how the answer is read. No React.
 *
 * Every installation value `brain.console.configuration` resolves, grouped, each with where it came
 * from and when a change to it takes effect. Nothing on the answer is a credential, and a value
 * shaped like an address arrives without anything that could carry one, so this module shows what it
 * is sent and adds nothing.
 *
 * Task ids: M41.1.4, M41.1.5, M41.1.6, M41.1.7, M41.2.6, M41.4.1
 */

import type { components } from "../api/schema";

export type SettingsBody = components["schemas"]["SettingsPage"];
export type SettingGroup = components["schemas"]["SettingGroupView"];
export type SettingRow = components["schemas"]["SettingRowView"];
export type LeavingStep = components["schemas"]["LeavingStepView"];

/** Where the API keeps the screen, and where one branding value is saved. */
export const SETTINGS_API_PATH = "/install/settings";

/** The console address and the menu's label. */
export const SETTINGS_PATH = "/settings";
export const SETTINGS_LABEL = "Settings";

export const SETTINGS_CRUMB = "Install › Settings";
export const SETTINGS_LEDE =
  "Every value that makes this install the company's own: branding, the identity provider, the " +
  "model profile and where files and embeddings are kept. Each says where it came from and when a " +
  "change takes effect. No key, token or password is shown here.";
export const READING_SETTINGS = "Reading this install's settings.";
export const UNREADABLE_SETTINGS = "The answer could not be read as this install's settings.";
export const SAVE = "Save";
export const SAVED = "Saved.";
export const FINDINGS_HEADING = "Needs attention";
export const STARTER_HEADING = "What this install was furnished with";
export const LEAVING_HEADING = "Leaving: handover and uninstall";

/** Who removes one part, in words. The keys are `brain.ops.handover_run.By`. */
export const BY_WORDS: Readonly<Record<string, string>> = {
  command: "The handover command",
  operator: "The operator, by hand",
};

/** Who removes a step, or the API's own word when this console does not know it. */
export function byWords(by: string): string {
  return BY_WORDS[by] ?? by;
}

/** How each source reads on the screen. The keys are `brain.console.configuration.Source`. */
export const SOURCE_WORDS: Readonly<Record<string, string>> = {
  saved: "Saved here",
  environment: "Environment file",
  default: "Product default",
  missing: "Not set",
};

/** Where a saved value is sent. */
export function savePath(name: string): string {
  return `${SETTINGS_API_PATH}/${encodeURIComponent(name)}`;
}

/** Read `SettingsPage` out of a response body, or null when it is not one. */
export function readSettings(payload: unknown): SettingsBody | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as { groups?: unknown; findings?: unknown; starter?: unknown };
  if (!Array.isArray(body.groups) || !Array.isArray(body.findings) || !body.starter) {
    return null;
  }
  return payload as SettingsBody;
}

/** A source in words, or the API's own word when it sends one this console does not know. */
export function sourceWords(source: string): string {
  return SOURCE_WORDS[source] ?? source;
}
