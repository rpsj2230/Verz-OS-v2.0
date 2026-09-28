/**
 * Two small parts the Staff sources page draws in several places: a headed list of names, and a
 * line saying why something cannot go ahead.
 *
 * Names and never a count of them: an operator reading that four people would be removed cannot
 * tell whether they are the four expected, and a count beside a list narrowed per reader would be
 * a count of what was left out.
 *
 * Task ids: M27.7.2, M27.16.1
 */

import { TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

/** A headed list of names, drawn only when there is one. */
export function Names({ label, names }: { readonly label: string; readonly names: readonly ReactNode[] }) {
  if (names.length === 0) {
    return null;
  }
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <h3 className="m-0 text-[12.5px] font-medium text-dim">{label}</h3>
      <ul aria-label={label} className="m-0 flex min-w-0 list-disc flex-col gap-0.5 pl-5 text-[13px] text-ink">
        {names.map((one, at) => (
          <li key={at}>{one}</li>
        ))}
      </ul>
    </div>
  );
}

/** Why something cannot go ahead, in the API's words. */
export function Problem({ children }: { readonly children: ReactNode }) {
  return (
    <p data-slot="problem" className="m-0 flex items-start gap-1.5 text-[12.5px] leading-snug text-warn">
      <TriangleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" />
      <span className="min-w-0">{children}</span>
    </p>
  );
}
