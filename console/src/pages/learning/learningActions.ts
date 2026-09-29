/**
 * What can be done to a learning and to a memory from the Learning and Memory pages, and for each
 * act that has no route the one sentence saying why it cannot be pressed yet.
 *
 * **Measured against the routes on main on 2026-09-29.** The API serves the review
 * (`GET /govern/learning`), one undo (`POST /govern/learning/undo`) and one person's memory
 * (`GET /govern/memory`). Nothing records that separate conversations agreed on a rule, so there
 * is no route that promotes a tier-two rule, and nothing records a person's decision on a gated
 * change, so there is none that decides a tier-three one. Each is `kit/UnavailableAction` with its
 * sentence here, and `tests/learning-memory-pages.test.tsx` reads every `retiredBy` against the API
 * document, so a sentence cannot go on saying "coming soon" about a route that has landed.
 *
 * **Editing a memory is not offered on these pages at all**, rather than coming soon: an edit is
 * written beside the memory it changes by the person it is about, on their own memory tab, and a
 * screen for reading somebody else's memory is the wrong place for it (`docs/admin-console-
 * architecture.md` D3). So it is a `NotOffered` sentence and no control.
 *
 * Task ids: M27.7.21, M27.7.22, M27.16.1
 */

/** Why each act without a route cannot be pressed, and the path shape whose arrival retires it. */
export const UNAVAILABLE = Object.freeze({
  promote: {
    label: "Promote",
    reason:
      "Coming soon: promoting a rule once enough separate conversations agree. Nothing records that agreement yet, so a rule stays in shadow.",
    retiredBy: /^\/api\/v1\/govern\/learning\/promot/,
  },
  decide: {
    label: "Decide",
    reason:
      "Coming soon: deciding a change that would widen who sees what. Nothing records the decision yet, so it waits here.",
    retiredBy: /^\/api\/v1\/govern\/learning\/(decide|decision)/,
  },
});

export type UnavailableAct = keyof typeof UNAVAILABLE;

/** In place of an edit or delete control on a person's memory. */
export const EDIT_NOT_OFFERED =
  "A memory is not edited or deleted here. A learning that went wrong is undone on Learning, and the change shows in this person's history.";

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
