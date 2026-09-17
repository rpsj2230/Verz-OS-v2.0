/**
 * The API's words about one input, drawn beside it, and the attributes that tie the two together.
 *
 * `api/problems.ts` decides which problem belongs to which input; this draws it. **One component
 * where there had been four**: Connectors, Notifications, Import and export and Webhooks each
 * carried a private list with a slightly different id, label and class, and every other form had
 * none. A problem is drawn the same way on every form now, so a screen reader hears it the same
 * way on every form: the input carries `aria-invalid` and names the list in `aria-describedby`,
 * and the list is a plain `ul` with no colour, for the reason `ui/Notice.tsx` has none.
 *
 * **The id is built from the form's prefix and the field's name, and the prefix is the caller's.**
 * Two forms on one page can both have a `secret`, and an id that was only the field's name would
 * point both inputs at whichever list came first. The list also carries `aria-label` "Problems
 * with" and the field, which is how the pages that had their own copy were found by their tests,
 * so the fold changed no test's way of finding a problem.
 *
 * Task ids: M27.8.5
 */

import type { FieldProblem } from "../api/errors";
import { problemsFor } from "../api/problems";

/** The id of the list beside `field` on the form whose controls begin with `form`. */
export function problemListId(form: string, field: string): string {
  return `${form}-${field}-problem`;
}

/**
 * What an input carries so its problems are read with it: `aria-invalid` when the API named it,
 * and the list's id added to whatever else describes it.
 *
 * `names` is every name the API may use for this input, first the one the list is drawn under.
 * Spread onto the input: `<input {...problemAttributes(problems, "connect", "port")} />`.
 */
export function problemAttributes(
  problems: readonly FieldProblem[],
  form: string,
  names: string | readonly string[],
  describedBy = "",
): { readonly "aria-invalid"?: true; readonly "aria-describedby"?: string } {
  const all: readonly string[] = typeof names === "string" ? [names] : names;
  const named = problemsFor(problems, all).length > 0;
  const ids = [describedBy, named ? problemListId(form, all[0] ?? "") : ""].filter((one) => one !== "").join(" ");
  return {
    ...(named ? { "aria-invalid": true as const } : {}),
    ...(ids === "" ? {} : { "aria-describedby": ids }),
  };
}

/** The words beside one input. Nothing at all when the API named no problem with it. */
export function FieldProblems({
  problems,
  form,
  names,
}: {
  readonly problems: readonly FieldProblem[];
  readonly form: string;
  /** Every name the API may use for this input, first the one the list is drawn under. */
  readonly names: string | readonly string[];
}) {
  const all: readonly string[] = typeof names === "string" ? [names] : names;
  const field = all[0] ?? "";
  const found = problemsFor(problems, all);
  if (found.length === 0) {
    return null;
  }
  return (
    <ul id={problemListId(form, field)} className="field-description field-problems" aria-label={`Problems with ${field}`}>
      {found.map((one, at) => (
        // The API may say the same sentence twice about one input, for two refused values.
        <li key={`${String(at)} ${one}`}>{one}</li>
      ))}
    </ul>
  );
}
