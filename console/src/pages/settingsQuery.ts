/**
 * What the Settings screen asks `brain.settings_routes` for, and how the answer is read. No React.
 *
 * Every installation value `brain.console.configuration` resolves, grouped, each with where it came
 * from and when a change to it takes effect. Nothing on the answer is a credential, and a value
 * shaped like an address arrives without anything that could carry one, so this module shows what it
 * is sent and adds nothing.
 *
 * **Every setting that is safe to change is changed here, behind a confirmation** (the owner found
 * nothing he could change on 2026-09-28). Each row is labelled as a person calls it, grouped by what
 * it is for, and a row this screen does not change says why in the API's one line. The currency
 * code meaning none is never drawn: an unset currency reads "Not set yet" and its field starts
 * empty, with an example beside it.
 *
 * Task ids: M41.1.4, M41.1.5, M41.1.6, M41.1.7, M41.2.6, M41.4.1
 */

import type { components } from "../api/schema";
import { UNSET_CURRENCY } from "./spendQuery";

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
  "Every value that makes this install the company's own, grouped by what it is for. The ones that " +
  "are safe to change are changed here; each of the others says where it is changed instead. No " +
  "key, token or password is shown here.";
export const READING_SETTINGS = "Reading this install's settings.";
export const UNREADABLE_SETTINGS = "The answer could not be read as this install's settings.";
export const SAVE = "Save";
export const SAVED = "Saved.";
export const SAVE_CHANGE = "Save the change";
export const KEEP_SETTING = "Keep it as it is";
export const NOT_SET_YET = "Not set yet";
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

/** The currency setting, whose code meaning none is never drawn. */
export const CURRENCY_SETTING = "INSTALL_CURRENCY";

/** Whether a row holds the currency code meaning none. */
function unsetCurrency(row: SettingRow): boolean {
  return row.name === CURRENCY_SETTING && row.value === UNSET_CURRENCY;
}

/** A read-only row's value as drawn: the API's, or where it came from when it is empty. */
export function shownValue(row: SettingRow): string {
  if (unsetCurrency(row)) {
    return NOT_SET_YET;
  }
  return row.value === "" ? sourceWords(row.source) : row.value;
}

/** What an editable row's field starts from: its value, or nothing for a currency not set yet. */
export function startingValue(row: SettingRow): string {
  return unsetCurrency(row) ? "" : row.value;
}

/** A setting offered as a choice rather than typed, with each choice in words. */
export const CHOICES: Readonly<Record<string, readonly { readonly value: string; readonly label: string }[]>> =
  Object.freeze({
    INSTALL_MODEL_PROFILE: [
      { value: "local", label: "On this server only" },
      { value: "hosted", label: "Online providers" },
    ],
  });

/** An example beside a field that is typed, where one helps. */
export const EXAMPLES: Readonly<Record<string, string>> = Object.freeze({
  INSTALL_CURRENCY: "SGD",
  INSTALL_TIME_ZONE: "Asia/Singapore",
  INSTALL_LOCALES: "en,zh-Hans",
});

/** The time zone setting, which is offered the zones this browser knows as suggestions. */
export const TIME_ZONE_SETTING = "INSTALL_TIME_ZONE";

/** The zones this browser knows, for suggestions; the API judges what is saved. */
export function knownTimeZones(): string[] {
  const intl = Intl as unknown as { supportedValuesOf?: (key: string) => string[] };
  try {
    return intl.supportedValuesOf === undefined ? [] : intl.supportedValuesOf("timeZone");
  } catch {
    return [];
  }
}

/** The confirmation's question for saving one setting. */
export function saveQuestion(row: SettingRow): string {
  return `Save ${row.label.toLowerCase()}?`;
}

/** What saving it does: the value it becomes, and when that takes effect, in the API's words. */
export function saveConsequence(row: SettingRow, value: string): string {
  const chosen = CHOICES[row.name]?.find((one) => one.value === value)?.label ?? value.trim();
  return `${row.label} becomes "${chosen}". ${row.applies} The change is recorded with your name.`;
}
