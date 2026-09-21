/**
 * What Connect Lark asks the API for and sends. No React.
 *
 * `brain.ops.lark_connect` holds the steps, the scope list per use and the test, and
 * `brain.lark_connect_routes` serves them. **Nothing here knows a scope's name**: the guide is read
 * again for every change of the chosen uses, so the list a person reads is the list the test
 * checks. See `THE_SCOPE_LIST_IS_THE_APIS`.
 *
 * **The App Secret is held in one field between a test and a save, and nowhere else.** A test and
 * a save each send it, and asking for it twice in a minute would be asking somebody to paste a
 * secret twice; so it stays in the field until the save is sent, is cleared then whatever comes
 * back, and is never put into an address, a store or a log. See `THE_SECRET_STAYS_IN_ITS_FIELD`.
 *
 * Task ids: M11.9.4
 */

import type { components } from "../api/schema";

export type LarkGuide = components["schemas"]["LarkView"];
export type LarkUse = components["schemas"]["LarkUseView"];
export type LarkScope = components["schemas"]["LarkScopeView"];
export type LarkStep = components["schemas"]["LarkStepView"];
export type LarkAsked = components["schemas"]["LarkAsked"];
export type LarkTested = components["schemas"]["LarkTestView"];
export type LarkUseResult = components["schemas"]["LarkUseResultView"];
export type LarkSaved = components["schemas"]["LarkSavedView"];

export const THE_SCOPE_LIST_IS_THE_APIS =
  "Which scopes each use needs is written once, on the server, and the test checks exactly that " +
  "list. A copy here would be the one a person reads and the one nobody updates.";

export const THE_SECRET_STAYS_IN_ITS_FIELD =
  "The App Secret is typed once, sent by a test and by a save, and cleared from the field when " +
  "the save is sent. It is never put into an address, a store or a log, and the API never sends " +
  "it back, so a refused save asks for it again.";

export const LARK_API_PATH = "/connectors/lark-app";
export const LARK_TEST_API_PATH = "/connectors/lark-app/test";

/**
 * The guide for these uses on this platform. The API answers the scope list and the steps.
 *
 * `null` asks for the uses already switched on; an empty list asks for none, spelled `none`, so
 * unticking every use is not read as "show me what is on".
 */
export function guidePath(uses: readonly string[] | null, platform: string): string {
  const query = new URLSearchParams();
  if (uses !== null) {
    query.set("uses", uses.length > 0 ? uses.join(",") : "none");
  }
  if (platform !== "") {
    query.set("platform", platform);
  }
  const text = query.toString();
  return text === "" ? LARK_API_PATH : `${LARK_API_PATH}?${text}`;
}

/** What a test and a save send: exactly these fields, untrimmed. The API judges each in words. */
export function larkBody(
  appId: string,
  appSecret: string,
  uses: readonly string[],
  platform: string,
  baseLink: string,
): LarkAsked {
  return { app_id: appId, app_secret: appSecret, uses: [...uses], platform, base_link: baseLink };
}

/** The uses in the order the API lists them, with `name` switched to `on`. */
export function toggled(order: readonly LarkUse[], chosen: readonly string[], name: string, on: boolean): string[] {
  const next = new Set(chosen);
  if (on) {
    next.add(name);
  } else {
    next.delete(name);
  }
  return order.map((one) => one.name).filter((one) => next.has(one));
}

/** Whether every use tested works, which is when a save is worth offering first. */
export function allWorking(tested: LarkTested | null): boolean {
  return tested !== null && tested.accepted && tested.uses.every((one) => one.verdict === "working");
}

/** A verdict in two or three words, beside the API's whole sentence. */
export function verdictWords(verdict: string): string {
  switch (verdict) {
    case "working":
      return "Working";
    case "missing_scope":
      return "Missing scope";
    case "not_released":
      return "Not released yet";
    case "not_shared":
      return "Not shared with the app";
    case "needs_setting":
      return "Needs a setting";
    case "credential_refused":
      return "Credential refused";
    default:
      return "Did not answer";
  }
}
