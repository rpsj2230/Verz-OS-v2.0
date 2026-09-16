/**
 * A scope's clauses, as the API's own three words. No React, no table library, no form.
 *
 * **Moved here from `matrixQuery.ts` because a second screen needs it, and a second copy is
 * the thing this repository spends the most effort not having.** The routing matrix shows a
 * rung's scope and the govern console shows a named scope's predicate; both are
 * `brain.core.scope.Scope` in its stored shape, and two renderings of one structure disagree
 * the first time somebody adds an operator. `matrixQuery.ts` re-exports these so that nothing
 * importing it has to change and its tests still name it as the source.
 *
 * **It is in a module of its own rather than in either page's query module, and the reason is
 * weight.** `matrixQuery.ts` imports the table library's cell renderers, so a page importing it
 * for two pure functions would pull `@tanstack/react-table` into its chunk, and
 * `tests/bundle-split.test.ts` walks the static import graph from `main.tsx` and would fail.
 * Nothing here imports anything at all.
 *
 * Task ids: M27.7.4
 */

/**
 * One clause of a scope, in the API's own three words.
 *
 * The console supplies the spaces and nothing else: the field name, the operator and the
 * value are all `brain.core.scope.Clause`'s, unchanged. There is no table of friendlier
 * operator words here for the reason `ui/Status.tsx` renders a state word exactly as it
 * arrived: `prefix` is the word the grant tables, the query compiler and every support
 * conversation use, and "starts with" would be a fourth vocabulary.
 *
 * A value that is not a string is rendered as its own JSON. `Op.IN` carries a list and
 * `Op.ANY` carries nothing, and both are payload shapes rather than prose; joining a list
 * with commas would read as a conjunction, which is the opposite of what IN means.
 */
export function clauseText(clause: unknown): string {
  if (typeof clause !== "object" || clause === null) {
    return "";
  }
  const { field, op, value } = clause as { field?: unknown; op?: unknown; value?: unknown };
  if (typeof field !== "string" || typeof op !== "string") {
    return "";
  }
  if (value === null || value === undefined) {
    return `${field} ${op}`;
  }
  return `${field} ${op} ${typeof value === "string" ? value : JSON.stringify(value)}`;
}

/**
 * The clauses of one scope, as text.
 *
 * A scope with no clauses yields no lines, and the cell is empty. That is the honest
 * rendering: an unrestricted scope narrows nothing, and a word like "all" would be this
 * console naming a state the payload does not carry. Every other empty cell in this console
 * means the same thing, which is that there was nothing there to show.
 */
export function scopeLines(scope: unknown): string[] {
  if (typeof scope !== "object" || scope === null) {
    return [];
  }
  const clauses = (scope as { clauses?: unknown }).clauses;
  if (!Array.isArray(clauses)) {
    return [];
  }
  return clauses.map(clauseText).filter((line) => line !== "");
}
