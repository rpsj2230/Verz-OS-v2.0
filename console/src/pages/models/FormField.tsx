/**
 * One labelled field of a module form: its label, the format it accepts said before anything is
 * sent, the control, and the problems found with it, beside it.
 *
 * **The format is said first, not only after a refusal** (the owner's rule for every form,
 * 2026-09-28). A person who types a region, an address or a number of seconds reads what is
 * accepted under the label, and a refusal, the page's own or the API's, is drawn in the same place.
 *
 * Task ids: M27.16.1
 */

import type { ReactNode } from "react";
import type { FieldProblem } from "../../api/errors";
import { FieldProblems } from "../../ui/FieldProblems";

export const FIELD_CONTROL =
  "h-11 w-full min-w-0 rounded-md border border-input bg-panel px-2.5 text-sm text-ink shadow-xs outline-hidden focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring sm:h-9";

export const FIELD_AREA =
  "min-h-20 w-full min-w-0 rounded-md border border-input bg-panel px-2.5 py-2 text-sm whitespace-pre-wrap text-ink shadow-xs outline-hidden [overflow-wrap:anywhere] focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring";

export function FormField({
  id,
  label,
  hint,
  form,
  name,
  problems,
  children,
}: {
  readonly id: string;
  readonly label: string;
  /** What the field accepts, in one sentence. */
  readonly hint: string;
  readonly form: string;
  readonly name: string;
  readonly problems: readonly FieldProblem[];
  readonly children: ReactNode;
}) {
  return (
    <div data-slot="form-field" className="flex min-w-0 flex-col gap-1">
      <label htmlFor={id} className="text-[13px] font-medium text-ink">
        {label}
      </label>
      <p id={`${id}-hint`} className="m-0 text-[12px] leading-snug text-dim">
        {hint}
      </p>
      {children}
      <FieldProblems problems={problems} form={form} names={name} />
    </div>
  );
}
