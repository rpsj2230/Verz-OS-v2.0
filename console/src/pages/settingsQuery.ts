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
 * **A saved value can be taken away, which is "return to default"** (M27.12.7). It retires the
 * saved row, so the setting reads the environment file's value or the product default again; each
 * row carries which (`without_saved`), so the confirmation names the value before anything is sent.
 *
 * **Every field says what it accepts before it is sent** (`FORMATS`), in the words the API's own
 * refusal would use. It decides nothing: `brain.console.configuration.setting_problem` judges.
 *
 * Task ids: M41.1.4, M41.1.5, M41.1.6, M41.1.7, M41.2.6, M41.4.1, M27.12.7, M27.16.1
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

export const SETTINGS_LEDE =
  "The values that make this install the company's own. Change the editable ones here; each of the " +
  "others says where it is changed. No key, token or password is shown.";
export const READING_SETTINGS = "Reading this install's settings.";
export const RETURN_TO_DEFAULT = "Return to default";
export const KEEP_SAVED = "Keep the saved value";
export const RETURNED = "Returned to its default.";
export const NOT_SAVED = "The setting was not saved";
export const NOT_RETURNED = "The setting was not returned to its default";
export const FURNISHED_HEADING = "Starter set";
export const VARIABLES_LABEL = "Each setting's variable in the environment file, and what reads it.";
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

/** Where a saved value is taken away, returning the setting to its default. */
export function defaultPath(name: string): string {
  return `${SETTINGS_API_PATH}/${encodeURIComponent(name)}/default`;
}

/** Whether "return to default" is offered: an editable setting with a value saved here. */
export function mayReturnToDefault(row: SettingRow): boolean {
  return row.editable && row.source === "saved";
}

/** The confirmation's question for taking a saved value away. */
export function defaultQuestion(row: SettingRow): string {
  return `Return ${row.label.toLowerCase()} to its default?`;
}

/** What taking it away does: the value it reads next and where that comes from. */
export function defaultConsequence(row: SettingRow): string {
  const next = row.without_saved === "" ? NOT_SET_YET : row.without_saved;
  const from = row.without_saved_source === "environment" ? "the environment file" : "the product default";
  return `The saved value is removed and ${row.label} reads "${next}" from ${from}. ${row.applies} The change is recorded with your name.`;
}

/** What each field accepts, said under it before anything is sent. The API judges. */
export const FORMATS: Readonly<Record<string, string>> = Object.freeze({
  INSTALL_COMPANY_NAME: "Up to 200 characters, as the console's header should show it.",
  INSTALL_PRODUCT_NAME: "Up to 200 characters, the name people know this system by.",
  INSTALL_LOGO_URL: "A full address starting https://, or a path on this install such as /logo.svg.",
  INSTALL_ACCENT_COLOUR: "# followed by six hexadecimal digits, such as #2563eb.",
  INSTALL_SENDER_ADDRESS: "One email address that mail from this install is sent from, such as brain@example.com.",
  INSTALL_LOCALES: "Language codes separated by commas, such as en,zh-Hans.",
  INSTALL_CURRENCY: "A three-letter currency code, such as SGD.",
  INSTALL_TIME_ZONE: "A time zone name, such as Asia/Singapore.",
  INSTALL_MODEL_PROFILE: "Where questions may be answered: on this server only, or by online providers.",
  INSTALL_DIGEST_TIME: "A time on the 24-hour clock in the install's time zone, such as 18:00.",
  INSTALL_SERVICES:
    "none, or any of presidio, langfuse and sandbox separated by commas: the personal data detector, the trace ledger and the script sandbox, which needs gVisor on the server. The next update starts each one this server has the memory for.",
  INSTALL_LARK_CARD_APPROVALS:
    "Whether a Lark card's buttons may approve. A press relies on Lark's own sign-in and carries no second factor from the Brain, so switch it on only if your Lark requires two-step verification.",
});

/** What a field accepts, or one plain sentence for a setting the table does not know. */
export function formatOf(name: string): string {
  return FORMATS[name] ?? "Up to 200 characters on one line.";
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
    INSTALL_LARK_CARD_APPROVALS: [
      { value: "off", label: "Off: decide approvals in the console" },
      { value: "on", label: "On: approve from Lark cards" },
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
