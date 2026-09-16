/**
 * What the five install screens ask the API for, and the three rules they all render by. No
 * React.
 *
 * The split is `matrixQuery.ts`'s and `recordsQuery.ts`'s: this decides what may be asked and
 * what a row is, the pages render it. What makes it one module for five screens rather than
 * five modules is that they are one API surface and one argument. `brain.console.installation`,
 * `brain.console.version_view` and `brain.console.recovery_view` answer them, `brain.
 * install_routes` serves all five, and the three rules below hold on every one of them. Five
 * copies of those rules would be five places for one of them to be relaxed on the screen where
 * it matters most.
 *
 * **Rule one: a fact carries where it came from, and the console never drops it.** `brain.
 * console.installation.Fact` puts `measured`, `declared` or `unknown` beside every value, and
 * `A_FIELD_CHECKED_BEFORE_DECIDING_NOT_TO_WORRY_IS_MEASURED` is why: nobody opens an install
 * screen out of curiosity, they open it because something is wrong or because they are about
 * to tell somebody that nothing is, and then they stop looking. A screen that showed the value
 * and not the label would render a head read out of the source tree exactly like a revision
 * read from the database. See `A_SOURCE_LABEL_IS_NOT_DECORATION`.
 *
 * **Rule two: an unknown fact renders its sentence and no value, and nothing renders a dash.**
 * The API refuses to send a value on an unknown fact and requires a sentence saying what would
 * have to exist for it to be known. A console that drew a dash there would put the reassuring
 * blank back, one line below the model that refuses it, and the field it would do it to is
 * "last verified restore". See `A_DASH_IS_WHERE_A_BLANK_BECOMES_NOT_APPLICABLE`.
 *
 * **Rule three: nothing on these screens is a tick, and no value here chooses a colour.** Every
 * verdict arrives as a word plus two sentences the API composed: `brain.console.version_view.
 * ANSWERS` and `brain.console.recovery_view.ANSWERS` are total over their enumerations and are
 * written for somebody with a server and no source tree. Both modules hold exactly one answer
 * that may be drawn as reassurance and refuse to claim it without the conditions behind it, so
 * a console mapping a word to a tone would be the second place that decision is made, and the
 * one an attacker edits. `ui/Status.tsx` is the one place in this console a value picks a
 * colour and it is a closed table of connector health; these words are not in it and must not
 * be added to it. See `A_TICK_DRAWN_HERE_IS_A_SECOND_OPINION_ABOUT_WHETHER_TO_WORRY`.
 *
 * **A surface that could not read its source sends no panel, and the page says so loudly.**
 * `RecoveryView` and `LimitsView` each carry exactly one of a panel and a sentence, refused in
 * the API's own models. The readers below return a discriminated value rather than a nullable
 * one, so a page cannot fall through to an empty list: an empty list of who is being throttled
 * reads as nobody, and an empty recovery panel reads as an install whose backups have never
 * run.
 *
 * **No count of anything, on any of these screens.** The throttling list is the one collection
 * here the reader's own grant narrows and the API sends no total for it. Nothing below computes
 * a length for display and no page renders one, which is the rule this console keeps everywhere
 * rather than per endpoint.
 *
 * Task ids: M27.7.25, M27.7.27
 */

import type { components } from "../api/schema";

/** One labelled statement about this deployment, as `brain.console.installation.Fact` sends it. */
export type Fact = components["schemas"]["FactView"];

/** What is running, as `brain.install_routes.InstallView` sends it. */
export type InstallFacts = components["schemas"]["InstallView"];

/** The version panel, as `brain.console.version_view.Panel` reaches a browser. */
export type Updates = components["schemas"]["UpdatesView"];

/** The backup panel, or the admission that nothing looked. */
export type Recovery = components["schemas"]["RecoveryView"];
export type RecoveryPanel = components["schemas"]["RecoveryPanelView"];

/** The ceilings, and the throttling list when there is one. */
export type Limits = components["schemas"]["LimitsView"];

/** Memory and connections. */
export type Capacity = components["schemas"]["CapacityView"];

/**
 * Written down because dropping the label is the single change that makes these screens lie,
 * and it looks like tidying.
 */
export const A_SOURCE_LABEL_IS_NOT_DECORATION =
  "Every value on an install screen carries measured, declared or unknown beside it, because " +
  "the same row holds a release read out of a running image and a head read out of the source " +
  "tree, and the second is the answer to a different question. A column of values with the " +
  "labels taken off for tidiness is a screen where the two are the same fact, read by somebody " +
  "who came to decide whether to stop investigating.";

/**
 * Written down because a dash is what every renderer supplies for a missing value, and this is
 * the one group of screens where it is the failure rather than the convention.
 */
export const A_DASH_IS_WHERE_A_BLANK_BECOMES_NOT_APPLICABLE =
  "A fresh backup date beside an empty last verified restore is the worst state this system " +
  "has wearing the appearance of the best one, and the appearance comes entirely from the " +
  "blank: a dash reads as not applicable and the reader stops. So an unknown fact renders the " +
  "sentence the API sent saying what would have to happen for it to be known, and this console " +
  "has no placeholder for a value it was not given.";

/**
 * Written down because a green tick is one line of markup and is the thing the two panels
 * behind these screens spend their whole length refusing.
 */
export const A_TICK_DRAWN_HERE_IS_A_SECOND_OPINION_ABOUT_WHETHER_TO_WORRY =
  "Up to date and cannot tell are read the same way when they are drawn the same way, and " +
  "recoverable and never verified are worse. Each panel names one answer that may be drawn as " +
  "reassurance and refuses to claim it without the conditions behind it, which are conditions " +
  "this browser cannot check. So a standing and an assurance render as the API's own word " +
  "with the API's own two sentences under it, in one appearance, and nothing here turns either " +
  "into a colour.";

// ------------------------------------------------------------------- where the API answers

export const INSTALL_API_PATH = "/install";
export const UPDATES_API_PATH = "/install/updates";
export const RECOVERY_API_PATH = "/install/recovery";
export const LIMITS_API_PATH = "/install/limits";
export const CAPACITY_API_PATH = "/install/capacity";

// ------------------------------------------------------------- where the console answers
//
// One address per screen and no parameter on any of them, which is `brain.install_routes`'
// own shape: none of these screens has a sub-object, so a path segment would be an address for
// something that does not exist. Each address is the screen's key in `brain.console.screens`,
// because `brain.ops.console_screens.routed_screen_keys` reads the first path segment out of
// `App.tsx` and matches it against the registry. A prettier address would take these screens
// off that list while leaving them reachable, which is the one failure that check exists to
// prevent arriving from the direction that looks like a tidy-up.

export const INSTALL_PATH = "/install";
export const UPDATES_PATH = "/updates";
export const RECOVERY_PATH = "/recovery";
export const LIMITS_PATH = "/limits";
export const CAPACITY_PATH = "/connections";

/** Every install screen's console address, with the title the registry gives it. */
export const INSTALL_SECTIONS: readonly { readonly to: string; readonly label: string }[] = [
  { to: INSTALL_PATH, label: "This install" },
  { to: UPDATES_PATH, label: "Version and updates" },
  { to: RECOVERY_PATH, label: "Backup and recovery" },
  { to: LIMITS_PATH, label: "Rate limits" },
  { to: CAPACITY_PATH, label: "Capacity" },
];

// ------------------------------------------------------------------------ reading a fact

/** The three words `brain.console.installation.Source` uses. Rendered, never translated. */
export const UNKNOWN_SOURCE = "unknown";

/**
 * Whether a fact has a value to show at all.
 *
 * Asked rather than inferred from the string being empty, because the two are different
 * questions and only one of them is the API's: a `measured` fact is refused by `Fact` if it
 * carries no value, so an empty value on anything but an unknown fact is a payload from an API
 * this console was not built against, and drawing it as unknown would be this console repairing
 * a response it should be showing as it arrived.
 */
export function isKnown(fact: Fact): boolean {
  return fact.source !== UNKNOWN_SOURCE;
}

/**
 * The facts on a response, or none.
 *
 * A reader rather than a cast, in `readMatrixPage`'s shape and for its reason: a body that is
 * not the shape this screen asked for is a console built against a different API, and there is
 * no sentence worth composing about it. The page shows the API's own failure when there is one
 * and an empty list of facts when there is not, which is visibly nothing rather than a
 * plausible something.
 */
export function factsOf(payload: unknown): readonly Fact[] {
  if (typeof payload !== "object" || payload === null) {
    return [];
  }
  const found = (payload as { facts?: unknown }).facts;
  return Array.isArray(found) ? (found as Fact[]) : [];
}

// ------------------------------------------------------- reading a surface that may be unread

/** A panel, or the sentence saying nothing looked. Never both and never neither. */
export type Read<T> = { readonly panel: T } | { readonly unread: string };

/** Whether a read produced something to draw. A function so the narrowing is written once. */
export function wasRead<T>(read: Read<T>): read is { readonly panel: T } {
  return "panel" in read;
}

/**
 * The recovery panel, or why there is none.
 *
 * The absence is turned into a value here rather than left as a null on the payload, so a page
 * cannot write `panel?.copies ?? []` and render three empty coverage rows. That expression is
 * one keystroke and it puts back exactly the blank
 * `A_DASH_IS_WHERE_A_BLANK_BECOMES_NOT_APPLICABLE` describes.
 *
 * A body carrying neither is treated as unread with the API's own empty sentence rather than as
 * a panel, because the direction to fail in is the alarming one: a console that drew nothing
 * would be indistinguishable from a page that had not loaded.
 */
export function readRecovery(payload: Recovery | null): Read<RecoveryPanel> {
  const panel = payload?.panel;
  if (panel === null || panel === undefined) {
    return { unread: payload?.unread ?? "" };
  }
  return { panel };
}

/**
 * The throttling list, or why there is none.
 *
 * The same shape and the same reason, and it matters more here: an absent list and an empty
 * list both draw no rows, and one of them means nobody is being throttled while the other means
 * nothing looked. `throttled` is `null` on the payload when it is absent, so the check is
 * against null rather than against length, and a genuinely empty list is a panel with no rows
 * in it, which is the answer a department-scoped reader gets.
 */
export function readThrottled(payload: Limits | null): Read<readonly Throttled[]> {
  const rows = payload?.throttled;
  if (rows === null || rows === undefined) {
    return { unread: payload?.unread ?? "" };
  }
  return { panel: rows };
}

/** One ceiling that is refusing right now. */
export type Throttled = components["schemas"]["ThrottleView"];

/** One external ceiling requests run into. */
export type Ceiling = components["schemas"]["CeilingView"];

/** One database's connection budget. */
export type Connection = components["schemas"]["ConnectionView"];

/** One coverage's two facts and whether it is inside the promise. */
export type Copies = components["schemas"]["CopyStateView"];

/**
 * How a ceiling's columns are shown, in the order somebody reads them.
 *
 * The header is the API's own field name, unchanged, for the reason `recordsQuery.ts` gives:
 * the API owns the vocabulary, and a console renaming `per_day` to "Daily limit" would show a
 * word no docstring and no support conversation uses. `derived` is a column rather than a
 * footnote because a daily figure calculated from a per-minute one always flatters the source.
 */
export const CEILING_COLUMNS: readonly (keyof Ceiling)[] = [
  "name",
  "per_day",
  "raisable",
  "derived",
];

/** How a throttled row's columns are shown. No count of refused requests, and none available. */
export const THROTTLE_COLUMNS: readonly (keyof Throttled)[] = [
  "scope",
  "subject",
  "limit",
  "retry_after_seconds",
];

/** How a connection budget's columns are shown, in the order the arithmetic runs. */
export const CONNECTION_COLUMNS: readonly (keyof Connection)[] = [
  "database",
  "admissible",
  "demand",
  "headroom",
];
