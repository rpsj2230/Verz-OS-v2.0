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
 * **Where a test sends somebody back is the API's too.** Each use's result names the steps to redo by
 * key (`redo`), and `redoSteps` turns those into the steps as the guide serves them, pictures and
 * all, so the flow can say "go back to step 5" and show its picture.
 *
 * Task ids: M11.9.4, M10.2.1
 */

import type { components } from "../api/schema";

export type LarkGuide = components["schemas"]["LarkView"];
export type LarkUse = components["schemas"]["LarkUseView"];
export type LarkScope = components["schemas"]["LarkScopeView"];
export type LarkStep = components["schemas"]["GuideStepView"];
export type LarkAsked = components["schemas"]["LarkAsked"];
export type LarkTested = components["schemas"]["LarkTestView"];
export type LarkUseResult = components["schemas"]["LarkUseResultView"];
export type LarkSaved = components["schemas"]["LarkSavedView"];
export type LarkEvents = components["schemas"]["LarkEventsView"];
export type LarkLastTest = components["schemas"]["LarkLastTestView"];
export type LarkSwitchedOff = components["schemas"]["LarkSwitchedOffView"];

export const THE_SCOPE_LIST_IS_THE_APIS =
  "Which scopes each use needs is written once, on the server, and the test checks exactly that " +
  "list. A copy here would be the one a person reads and the one nobody updates.";

export const THE_SECRET_STAYS_IN_ITS_FIELD =
  "The App Secret, and for the chat channel its Encrypt Key and Verification Token, are typed " +
  "once, sent by a test and by a save, and cleared from their fields when the save is sent. None " +
  "is ever put into an address, a store or a log, and the API never sends one back, so a refused " +
  "save asks for them again.";

export const LARK_API_PATH = "/connectors/lark-app";
export const LARK_TEST_API_PATH = "/connectors/lark-app/test";
export const LARK_SWITCH_OFF_API_PATH = "/connectors/lark-app/switch-off";

/** The key the Lark flow keeps its place under while its dialog is closed. */
export const LARK_FLOW = "lark";

/**
 * The guide for these uses on this platform. The API answers the scope list and the steps.
 *
 * `null` asks for the uses already switched on; an empty list asks for none, spelled `none`, so
 * unticking every use is not read as "show me what is on".
 */
export function guidePath(uses: readonly string[] | null, platform: string, appId = ""): string {
  const query = new URLSearchParams();
  if (uses !== null) {
    query.set("uses", uses.length > 0 ? uses.join(",") : "none");
  }
  if (platform !== "") {
    query.set("platform", platform);
  }
  // Not a secret: the App ID is on every page of the app in Lark, and it builds the steps' links.
  if (appId.trim() !== "") {
    query.set("app_id", appId.trim());
  }
  const text = query.toString();
  return text === "" ? LARK_API_PATH : `${LARK_API_PATH}?${text}`;
}

/** The chat channel's two event keys, from Lark's Encryption Strategy tab. */
export interface ChatKeys {
  readonly encryptKey: string;
  readonly verificationToken: string;
}

export const NO_CHAT_KEYS: ChatKeys = { encryptKey: "", verificationToken: "" };

/** What a test and a save send: exactly these fields, untrimmed. The API judges each in words. */
export function larkBody(
  appId: string,
  appSecret: string,
  uses: readonly string[],
  platform: string,
  baseLink: string,
  keys: ChatKeys = NO_CHAT_KEYS,
): LarkAsked {
  return {
    app_id: appId,
    app_secret: appSecret,
    uses: [...uses],
    platform,
    base_link: baseLink,
    encrypt_key: keys.encryptKey,
    verification_token: keys.verificationToken,
  };
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

/** The uses switched on, in the API's order. */
export function switchedOn(guide: LarkGuide): readonly LarkUse[] {
  return guide.uses.filter((one) => one.switched_on);
}

/** The uses to start the flow with: what is on, with any asked for added, in the API's order. */
export function startingUses(guide: LarkGuide, add: readonly string[]): string[] {
  const wanted = new Set([...guide.uses.filter((one) => one.switched_on).map((one) => one.name), ...add]);
  return guide.uses.map((one) => one.name).filter((one) => wanted.has(one));
}

/** The steps a test sent somebody back to, as the guide serves them, each once, in flow order. */
export function redoSteps(guide: LarkGuide, tested: LarkTested | null): readonly LarkStep[] {
  if (tested === null) {
    return [];
  }
  const keys = new Set([...tested.redo, ...tested.uses.flatMap((one) => one.redo)]);
  return guide.steps.filter((one) => keys.has(one.key));
}

/** The steps one result sends somebody back to, as the guide serves them. */
export function stepsFor(guide: LarkGuide, keys: readonly string[]): readonly LarkStep[] {
  return keys.flatMap((key) => guide.steps.filter((one) => one.key === key));
}

// ------------------------------------------------------------------ the wiki's spaces

export type DeclaredSpaces = components["schemas"]["DeclaredSpacesView"];
export type DeclaredSpace = components["schemas"]["DeclaredSpaceView"];
export type SpacesDeclared = components["schemas"]["SpacesDeclaredView"];
export type LarkSpace = components["schemas"]["LarkSpaceView"];

/** The wiki spaces declared on this install, and where more are declared. */
export const LARK_WIKI_SPACES_API_PATH = "/connectors/lark-app/wiki-spaces";

/** One space the administrator is about to declare: what was chosen or pasted, and its reach. */
export interface SpaceChoice {
  /** The space's id, or the settings link that was pasted for it; the API reads the id out. */
  readonly space: string;
  /** What the row is called on the screen: Lark's name for it, or what was pasted. */
  readonly label: string;
  /** "company", "department", or "" for a space not being declared in this save. */
  readonly reach: string;
  readonly department: string;
}

/** The spaces a test saw, as rows to declare, leaving out any already declared. */
export function spaceChoices(tested: LarkTested | null, declared: readonly DeclaredSpace[]): SpaceChoice[] {
  const already = new Set(declared.map((one) => one.space_id));
  const seen = tested?.uses.find((one) => one.name === "knowledge_wiki")?.spaces ?? [];
  return seen
    .filter((one) => !already.has(one.space_id))
    .map((one) => ({ space: one.space_id, label: one.name === "" ? one.space_id : one.name, reach: "", department: "" }));
}

/** The rows a save sends: every row given a reach, in the order drawn. */
export function spacesBody(choices: readonly SpaceChoice[]): { spaces: { space: string; reach: string; department: string }[] } {
  return {
    spaces: choices
      .filter((one) => one.reach !== "")
      .map((one) => ({ space: one.space, reach: one.reach, department: one.reach === "department" ? one.department : "" })),
  };
}
