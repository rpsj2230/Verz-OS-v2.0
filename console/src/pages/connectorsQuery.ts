/**
 * What the connectors screen asks the API for, and the three rules it renders by. No React.
 *
 * The split is `installQuery.ts`'s: this decides what may be asked and what a row is, the page
 * renders it. `brain.console.connector_trust` decides what a reader may be told and
 * `brain.connector_routes` serves it, and nothing here adds an opinion about either.
 *
 * **Rule one: the sentences are the API's, whole.** Every column on this screen that is not a
 * word out of an enumeration is a sentence the Python side composed: what a connector reaches,
 * what its credential is allowed to be used for, what its ceiling is, and what the source
 * contributes to who may see a row. A console that summarised any of them would be deciding half
 * the meaning of a permission fact in a browser. See `A_SENTENCE_IS_NOT_A_BADGE`.
 *
 * **Rule two: an absent list and an empty list are drawn differently.** The API sends exactly one
 * of a list and a sentence, refused in its own model, and `readConnectors` turns the absence into
 * a value so a page cannot write `connectors ?? []`. An empty list means this reader may be told
 * of no source; an absent one means nothing on the server looked, and drawing the second as the
 * first says this system reads no outside data, which is the reassuring answer to the question
 * the screen exists to answer honestly.
 *
 * **Rule three: no count, no total, and no bar drawn from a number nobody measured.**
 * `docs/screens.html` SCREEN 9 draws a bar of calls made today against each source's ceiling.
 * The API sends the ceiling in words and a sentence saying why there is no figure for today, and
 * this module offers no field a bar could be drawn from. See `A_BAR_NEEDS_A_NUMERATOR`.
 *
 * Task ids: M42.6.5
 */

import type { components } from "../api/schema";

/** One connector, as `brain.connector_routes.TrustView` sends it. */
export type Trust = components["schemas"]["TrustView"];

/** The screen's whole answer. */
export type Connectors = components["schemas"]["ConnectorsView"];

/** One line of what this system copies out of a source and what it never does. */
export type CopyLine = components["schemas"]["CopyLineView"];

/**
 * Written down because turning a sentence into a badge is a tidy-up that removes the argument.
 */
export const A_SENTENCE_IS_NOT_A_BADGE =
  "What a connector reaches, what its credential may be used for and what the source " +
  "contributes to who may see a row are each a decision with a reason attached, composed on " +
  "the server for somebody who has a server and no source tree. Rendered as a chip saying " +
  "read-only they all become one word, and the word a reader remembers is the reassuring half " +
  "of a two-member enumeration. The state column is the one place a value picks a colour here, " +
  "it is `ui/Status.tsx`, and its table is the connector health vocabulary and nothing else.";

/**
 * Written down because a progress bar is four lines of markup and is the one element on this
 * screen somebody reads before deciding a backfill is safe.
 */
export const A_BAR_NEEDS_A_NUMERATOR =
  "The design draws today's calls against each source's ceiling. The ceiling is verified and " +
  "the numerator is not readable from this install: the store holding the counting windows " +
  "answers about a window it is handed and cannot be asked which windows exist. A bar drawn " +
  "from a zero would show every source idle, which is the direction that gets somebody to start " +
  "a backfill. So the ceiling is a sentence, there is no bar, and the API's own reason is " +
  "rendered beside the column.";

/**
 * Written down because a vault path looks harmless in a row and is the one value on this screen
 * that names a credential rather than describing one.
 */
export const NOTHING_HERE_ASKS_FOR_A_CREDENTIAL =
  "This screen has no field a credential could be typed into and no field a vault path arrives " +
  "in. Connecting a source is two writes on the server, and the API sends the sentence saying " +
  "so in place of a control: a form that collected a key would have nowhere to send it, and a " +
  "button that refused would read as a permission problem with the person pressing it.";

// ------------------------------------------------------------------- where the API answers

export const CONNECTORS_API_PATH = "/connectors";

// ------------------------------------------------------------- where the console answers
//
// The screen's key in `brain.console.screens`, which is what
// `brain.ops.console_screens.routed_screen_keys` matches the registry against. A prettier
// address would take this screen off that list while leaving it reachable.

export const CONNECTORS_PATH = "/connectors";

/**
 * The label the shell offers this screen under, and the label the design names.
 *
 * `docs/screens.html` calls it Connectors and `brain.console.screens` titles it Connector
 * health. The design's word wins in the navigation, because `brain.ops.console_design.
 * navigation_gaps` compares the shell against the design on the label and a screen reachable
 * under another name is a screen somebody following the design cannot find. The constant is
 * exported so this file and `layout/Shell.tsx` cannot disagree about it, and the shell writes
 * the entry out rather than spreading this one, because that sweep reads the shell's own rows.
 */
export const CONNECTORS_LABEL = "Connectors";

// ------------------------------------------------------------------------ reading a body

/** A list, or the sentence saying nothing looked. Never both and never neither. */
export type Read<T> = { readonly rows: T } | { readonly unread: string };

/** Whether a read produced something to draw. A function so the narrowing is written once. */
export function wasRead<T>(read: Read<T>): read is { readonly rows: T } {
  return "rows" in read;
}

/**
 * The connector list, or why there is none.
 *
 * The absence is turned into a value here rather than left as a null on the payload, so a page
 * cannot write `connectors ?? []` and draw an empty table. That expression is one keystroke and
 * it renders "nothing here looked" as "this system reads nothing".
 *
 * A body carrying neither is treated as unread with the API's own empty sentence, because the
 * direction to fail in is the one that claims less: a console that drew an empty table would be
 * indistinguishable from a page that had not loaded.
 */
export function readConnectors(payload: Connectors | null): Read<readonly Trust[]> {
  const rows = payload?.connectors;
  if (rows === null || rows === undefined) {
    return { unread: payload?.unread ?? "" };
  }
  return { rows };
}

/**
 * How a connector's columns are shown, in `docs/screens.html` SCREEN 9's order.
 *
 * The header is this console's own wording and the values are the API's, which is the one place
 * this screen departs from `installQuery.ts`' rule that the API owns the vocabulary. The reason
 * is that two of these columns do not answer the design's question: the design asks for the last
 * read and the API can say only when the source was last probed, and the design asks for the
 * budget used today and the API can say only the ceiling. A header repeating the design's word
 * over the weaker fact is the screen claiming a measurement it does not have.
 */
export const TRUST_COLUMNS: readonly { readonly field: keyof Trust; readonly header: string }[] = [
  { field: "name", header: "Source" },
  { field: "wiring", header: "Wiring" },
  { field: "credential", header: "Credential" },
  { field: "budget", header: "Ceiling" },
  { field: "projected_fields", header: "Projected" },
  { field: "checked_at", header: "Last checked" },
  { field: "health", header: "State" },
];

/** The fields that open under a row, in the order somebody reads them. */
export const TRUST_DETAIL: readonly { readonly field: keyof Trust; readonly label: string }[] = [
  { field: "reaches", label: "Reaches" },
  { field: "access", label: "May do" },
  { field: "permission_sync", label: "The source's own permissions" },
  { field: "lifecycle", label: "Lifecycle" },
  { field: "serving", label: "Serving traffic" },
  { field: "version", label: "Version" },
];

/**
 * What a source nothing has probed shows in the state column.
 *
 * An empty string reaches here for a source with no probe, and it is drawn as this word rather
 * than as a blank: a blank in a column of states reads as nothing being wrong with it.
 * `ui/Status.tsx` does not recognise the word, so it renders in the quietest tone, which is
 * exactly right and is that file's own rule about a word it has never heard of.
 */
export const NOT_PROBED = "not probed";

/** The state word for a row, never a blank. */
export function stateOf(row: Trust): string {
  return row.health === "" ? NOT_PROBED : row.health;
}
