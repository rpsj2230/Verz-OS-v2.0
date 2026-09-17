/**
 * What the connectors screen asks the API for, what it sends, and the rules it renders by. No React.
 *
 * The split is `installQuery.ts`'s: this decides what may be asked and what a row is, the page
 * renders it. `brain.console.connector_trust` decides what a reader may be told,
 * `brain.ops.connector_admin` decides who may connect a source and what a connection must be, and
 * `brain.connector_routes` serves both; nothing here adds an opinion about any of it.
 *
 * **Rule one: the sentences are the API's, whole.** What a connector reaches, what its key is,
 * what its ceiling is, what the source contributes to who may see a row, what connecting does not
 * do, and what a confirmation agrees to are each a sentence the Python side composed. A console
 * that summarised any of them would be deciding half the meaning of a permission fact in a
 * browser. See `A_SENTENCE_IS_NOT_A_BADGE`.
 *
 * **Rule two: an absent list and an empty list are drawn differently.** The API sends exactly one
 * of a list and a sentence, refused in its own model, and `readConnectors` turns the absence into
 * a value so a page cannot write `connectors ?? []`.
 *
 * **Rule three: no count, no total, and no bar drawn from a number nobody measured.** See
 * `A_BAR_NEEDS_A_NUMERATOR`.
 *
 * **Rule four: a key is sent once and kept by nobody here.** `connectionBody` is the one place a
 * key is put into anything, it is the request body and nothing else, and the form that holds it
 * clears it before the request leaves. See `A_KEY_IS_SENT_ONCE_AND_KEPT_BY_NOBODY_HERE`.
 *
 * Task ids: M42.6.5, M42.5.9
 */

import type { components } from "../api/schema";
import { problemsFor, when, type Problem } from "./webhooksQuery";

export { problemsFor, when, type Problem };

/** One connected source, as `brain.connector_routes.ConnectedView` sends it. */
export type Connected = components["schemas"]["ConnectedView"];

/** What one connected source is trusted to read, as `brain.connector_routes.TrustView` sends it. */
export type Trust = components["schemas"]["TrustView"];

/** The screen's whole answer. */
export type Connectors = components["schemas"]["ConnectorsView"];

/** A source the console can connect, and what its form asks for. */
export type Connectable = components["schemas"]["ConnectableView"];

/** A source this release has a connector for that the console cannot connect, and why. */
export type NotConnectable = components["schemas"]["NotConnectableView"];

/** One line of what this system copies out of a source and what it never does. */
export type CopyLine = components["schemas"]["CopyLineView"];

/** What a connect sends. */
export type ConnectionBody = components["schemas"]["ConnectAsked"];

/** What a connect or a disconnect answers. */
export type ConnectorChanged = components["schemas"]["ConnectorChangedView"];

/**
 * Written down because turning a sentence into a badge is a tidy-up that removes the argument.
 */
export const A_SENTENCE_IS_NOT_A_BADGE =
  "What a connector reaches, what its key is and what the source contributes to who may see a " +
  "row are each a decision with a reason attached, composed on the server for somebody who has a " +
  "server and no source tree. Rendered as a chip saying read-only they all become one word, and " +
  "the word a reader remembers is the reassuring half of a two-member enumeration. The state " +
  "column is the one place a value picks a colour here, it is `ui/Status.tsx`, and its table is " +
  "the connector health vocabulary and nothing else.";

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
 * Written down because the obvious convenience, keeping what was typed in case the request fails,
 * is a key held in a page's memory for as long as the page is open.
 */
export const A_KEY_IS_SENT_ONCE_AND_KEPT_BY_NOBODY_HERE =
  "A source's key is typed into one field, put into one request body by `connectionBody`, and " +
  "cleared from the form's state before the request leaves, whatever comes back. It is never " +
  "written to a store, an address or a log, never shown on a confirmation, and never echoed by " +
  "the API, so a refused connection asks for the key again rather than offering it back.";

// ------------------------------------------------------------------- where the API answers

export const CONNECTORS_API_PATH = "/connectors";

/** Where a source is disconnected. The name is a path segment and is encoded as one. */
export function disconnectApiPath(name: string): string {
  return `${CONNECTORS_API_PATH}/${encodeURIComponent(name)}/disconnect`;
}

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
 * The connected sources, or why there is no list.
 *
 * A body carrying neither is treated as unread with the API's own empty sentence, because the
 * direction to fail in is the one that claims less.
 */
export function readConnectors(payload: Connectors | null): Read<readonly Connected[]> {
  const rows = payload?.connectors;
  if (rows === null || rows === undefined) {
    return { unread: payload?.unread ?? "" };
  }
  return { rows };
}

/**
 * How a connected source's columns are shown, in `docs/screens.html` SCREEN 9's order.
 *
 * The header is this console's own wording and the values are the API's. Two of these columns
 * answer the design's question in two halves or not at all. The design asks for the last read:
 * `Last checked` is the worker's last attempt and the state it left, and the last time the source
 * was read to the end is a column of its own beside the table (`lastRead`), because an attempt that
 * failed every hour is not a read. The design asks for the budget used today and the API can say
 * only the ceiling. A header repeating the design's word over a weaker fact is the screen claiming
 * a measurement it does not have.
 */
export const TRUST_COLUMNS: readonly { readonly field: keyof Trust; readonly header: string }[] = [
  { field: "name", header: "Source" },
  { field: "wiring", header: "Wiring" },
  { field: "credential", header: "Key" },
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
 * What a source the worker has not tried yet shows in the state column.
 *
 * An empty string reaches here for a source with no attempt, and it is drawn as this word rather
 * than as a blank: a blank in a column of states reads as nothing being wrong with it.
 * `ui/Status.tsx` does not recognise the word, so it renders in the quietest tone.
 */
export const NOT_TRIED = "not tried";

/** The state word for a row, never a blank. */
export function stateOf(row: Trust): string {
  return row.health === "" ? NOT_TRIED : row.health;
}

/** What the last-read column says for a source the worker has never read to the end. */
export const NEVER_READ = "Never";

/**
 * When the worker last read a source to the end, or `NEVER_READ`.
 *
 * Never the attempt's time: a source whose key expired is attempted every hour and read never, and
 * drawing the attempt here would show it as read an hour ago. See
 * `brain.console.connector_trust.A_LAST_PROBE_IS_NOT_A_LAST_READ`.
 */
export function lastRead(row: Connected): string {
  return row.last_synced_at ? when(row.last_synced_at) : NEVER_READ;
}

/**
 * The key column in a few words, beside the API's sentence. `null` is not known and never not
 * held: a vault that did not answer draws every key as unknown rather than as missing.
 */
export function keyWords(row: Connected): string {
  if (row.key_held === null) {
    return "Not known";
  }
  if (!row.key_held) {
    return "Not held";
  }
  return row.key_written_at ? `Held, written ${when(row.key_written_at)}` : "Held";
}

// ------------------------------------------------------------------------ connecting one

/** The settings a form starts with: every setting this source asks for, blank. */
export function blankSettings(source: Connectable): Record<string, string> {
  return Object.fromEntries(source.settings.map((one) => [one.name, ""]));
}

/**
 * What a connect sends: the source, exactly the settings it asks for, and the key.
 *
 * Only the settings the source declares are sent, so a value left in the form from another source
 * cannot arrive as a setting this one does not take. Nothing is trimmed or checked here: the API
 * judges every field in words, and a second judgement in a browser is a second place to be wrong.
 */
export function connectionBody(
  source: Connectable,
  settings: Readonly<Record<string, string>>,
  key: string,
): ConnectionBody {
  return {
    connector: source.name,
    settings: Object.fromEntries(source.settings.map((one) => [one.name, settings[one.name] ?? ""])),
    credential: key,
  };
}

/**
 * The blank fields of a connection, as the problems the API would have answered with.
 *
 * **Only blankness is judged here, before the confirmation opens**, for `webhooksQuery.ts`' reason:
 * a connection with nothing typed was one press from a confirmation a person could agree to and be
 * refused for afterwards. The sentences are the ones the API serves beside the form
 * (`SettingView.blank` and `ConnectorsView.key_blank`), so there is no copy of them here to drift.
 * Every other rule, what the connector refuses and what makes a key one piece, stays the API's.
 */
export function blankConnectionProblems(
  source: Connectable,
  settings: Readonly<Record<string, string>>,
  key: string,
  keyBlank: string,
): Problem[] {
  const found: Problem[] = source.settings
    .filter((one) => (settings[one.name] ?? "").trim() === "")
    .map((one) => ({ field: one.name, code: "blank", message: one.blank }));
  if (key.trim() === "") {
    found.push({ field: "credential", code: "blank", message: keyBlank });
  }
  return found;
}

/** The sentence a success carries, or an empty one when the body is not that document. */
export function readTold(payload: unknown): string {
  if (typeof payload !== "object" || payload === null) {
    return "";
  }
  const told = (payload as { told?: unknown }).told;
  return typeof told === "string" ? told : "";
}

/**
 * The sources this reader may connect, in the API's order, with any the setup wizard named first.
 *
 * `named` is the free text of the wizard's Data sources screen, split on commas; a name there that
 * is a source this reader may connect is offered first, and nothing else about the text is read.
 */
export function offered(
  connectable: readonly Connectable[],
  named: string = "",
): readonly Connectable[] {
  const wanted = named
    .split(",")
    .map((one) => one.trim())
    .filter((one) => one !== "");
  const mine = connectable.filter((one) => one.may_connect);
  const first = mine.filter((one) => wanted.includes(one.name));
  return [...first, ...mine.filter((one) => !wanted.includes(one.name))];
}
