/**
 * What can be done to a learning and to a memory from the Learning and Memory pages, and the labels
 * of the acts that have no route yet.
 *
 * **Measured against the routes on main on 2026-09-29.** The API serves the review
 * (`GET /govern/learning`), one undo (`POST /govern/learning/undo`) and one person's memory
 * (`GET /govern/memory`). Nothing records that separate conversations agreed on a rule, so there
 * is no route that promotes a tier-two rule, and nothing records a person's decision on a gated
 * change, so there is none that decides a tier-three one. Each is a `kit/Explanation` of the
 * `action` form, its sentence served (`learning.promote`, `learning.decide`), and
 * `tests/unit/test_console_explanations.py` reads every expiry against the routes the application
 * mounts, so a sentence cannot go on saying "coming soon" about a route that has landed.
 *
 * **Editing a memory is not offered on these pages at all**, rather than coming soon: an edit is
 * written beside the memory it changes by the person it is about, on their own memory tab, and a
 * screen for reading somebody else's memory is the wrong place for it (`docs/admin-console-
 * architecture.md` D3). So it is an `Explanation` of the
 * `line` form (`learning.memory_not_edited`) and no control.
 *
 * Task ids: M27.7.21, M27.7.22, M27.16.1, M27.15.70
 */

/** The labels of the acts that are not built yet, one spelling each. */
export const ACT_LABELS = Object.freeze({
  promote: "Promote",
  decide: "Decide",
});

/** A change kind as a person reads it: underscores as spaces, the first letter capital. */
export function changeWords(change: string): string {
  const words = change.replace(/_/g, " ").trim();
  return words === "" ? change : `${words.slice(0, 1).toLocaleUpperCase("en-GB")}${words.slice(1)}`;
}

/** What an undo would write, by `control_writes`, in a few words for a table cell. */
export const UNDO_WRITES_WORDS: Readonly<Record<string, string>> = Object.freeze({
  demoted: "Stops recalling it",
  superseded: "Puts back what it replaced",
});

export function undoWritesWords(writes: string): string {
  return UNDO_WRITES_WORDS[writes] ?? changeWords(writes);
}
