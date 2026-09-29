/**
 * Where a connect flow keeps its place while its dialog is closed: the step it was on and the
 * plain values typed so far, for as long as the console is open in this tab.
 *
 * **In memory and nowhere else.** The console may not write to the browser's storage
 * (`scripts/check-boundaries.mjs`), and nothing here needs to outlive the tab: somebody who closes
 * the dialog to go and do a step in the vendor's console comes back to the same step, which is the
 * owner's ask. A reload starts again, and the flow reads where the source stands from the API.
 *
 * **Never a secret.** A key, a secret or a token lives in its own field (`ui/secret-field.tsx`) and
 * leaves with the dialog. What a flow keeps here is what it would print on a confirmation: which
 * uses were chosen, an identifier, a link. See `A_FLOW_REMEMBERS_ITS_PLACE_AND_NO_SECRET`.
 *
 * Task ids: M11.9.4, M27.11.9
 */

export const A_FLOW_REMEMBERS_ITS_PLACE_AND_NO_SECRET =
  "A connect flow closed half way keeps the step it was on and the plain values typed, in this " +
  "tab's memory only, so the person can switch to the vendor's console and come back. A secret is " +
  "never kept: it is typed into its own field and is gone when the dialog closes.";

const places = new Map<string, unknown>();

/** Where the flow named `key` was left, or undefined when it was never opened or was finished. */
export function recallFlow<T>(key: string): T | undefined {
  // A cast at the one place this map is read: each flow reads back only what it wrote under its
  // own key, and a mismatch would be a flow writing another's key, which a test would see.
  return places.get(key) as T | undefined;
}

/** Keep where the flow named `key` is. Never pass a secret here: see the module note. */
export function rememberFlow<T>(key: string, place: T): void {
  places.set(key, place);
}

/** Forget the flow named `key`, once what it was for is done. */
export function forgetFlow(key: string): void {
  places.delete(key);
}
