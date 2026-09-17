/**
 * Which of the API's problems belong beside which input, and which belong to no input at all.
 * No React: `ui/FieldProblems.tsx` draws what this decides.
 *
 * **Written once, here, because it had been written four times.** The Webhooks screen read a
 * 422's problems and matched them to its fields, and Connectors, Notifications and Import and
 * export borrowed its reader and each drew a private list beside their inputs. Every other form
 * in the console drew nothing: a validation refusal from any of the forty other writes reached a
 * person as one sentence under a heading, with the words about which box was wrong thrown away.
 * The API now lists problems on every refusal it writes, so the matching is the console's
 * business everywhere and one copy of it is the only kind that stays in step.
 *
 * **A problem that matches no input is listed, never dropped.** A field of `""` is a problem with
 * the request as a whole; a field the form has no input for is a problem with something the form
 * sent without asking, such as an id taken from the row. Both are the API explaining a refusal,
 * and a form that silently discarded them would be back to "That did not work" with the
 * explanation in the response and not on the screen. See `A_PROBLEM_WITH_NO_INPUT_IS_STILL_SAID`.
 *
 * **Matching is by name and nothing looser.** A field matches an input when it is one of the
 * names the form gives that input, exactly. Rejected: matching on the last segment, so that
 * `rungs.0.attempts` would land beside any input called `attempts`. On a form with two rungs that
 * is the wrong box, and a problem beside the wrong box is worse than a problem in the list.
 *
 * Task ids: M27.8.5
 */

import type { FieldProblem } from "./errors";

export type { FieldProblem } from "./errors";

/** The rule a reviewer must not break when tidying a form's refusal. */
export const A_PROBLEM_WITH_NO_INPUT_IS_STILL_SAID =
  "Every problem the API lists is shown: beside the input it names when the form has one, and " +
  "under the failure notice when it does not, including a problem with the request as a whole.";

/** The sentences for one input, in the order the API gave them. `names` are every name it has. */
export function problemsFor(problems: readonly FieldProblem[], names: string | readonly string[]): string[] {
  const wanted: readonly string[] = typeof names === "string" ? [names] : names;
  return problems.filter((one) => one.field !== "" && wanted.includes(one.field)).map((one) => one.message);
}

/** The problems no input on the form is named for, in the API's order. */
export function unmatchedProblems(
  problems: readonly FieldProblem[],
  names: readonly string[],
): FieldProblem[] {
  return problems.filter((one) => one.field === "" || !names.includes(one.field));
}
