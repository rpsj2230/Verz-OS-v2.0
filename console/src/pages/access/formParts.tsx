/**
 * The form parts the People and access pages share: a labelled field that says what it accepts
 * before anybody submits, the problems found before a write, and the rules for the values the API
 * checks by shape.
 *
 * **Every field says its format under its label, before submit.** The owner typed
 * `acceptance-test` as a department's short name and was told only afterwards that it was "not in
 * the form this address expects", which is the API's sentence for a pattern it refused and names
 * nothing a person can act on. So a field whose value has a shape carries a hint in words
 * (`SHORT_NAME_HINT`), and the same rule is judged here before the request, with a sentence saying
 * what to change. The API still judges it: this is a courtesy, never the rule, and a value this
 * accepts and the API refuses is drawn in the API's words beside the field.
 *
 * **The rule is the API's rule, spelled once here.** `SHORT_NAME_PATTERN` is
 * `brain.core.department.SLUG_PATTERN`, and `tests/people-access-pages.test.tsx` reads the Python
 * source and holds the two equal, so the hint cannot promise a shape the API refuses.
 *
 * Plain labelled inputs and native selects, not the schema form library, so none of these pages
 * pulls that library into the entry chunk (`tests/bundle-split.test.ts`).
 *
 * Task ids: M27.11.1, M27.16.1
 */

import { useId, type ReactNode } from "react";
import type { FieldProblem } from "../../api/errors";
import { cn } from "../../lib/utils";

/** `brain.core.department.SLUG_PATTERN`, which every short name of a department, team, scope and pack is. */
export const SHORT_NAME_PATTERN = /^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$/;
export const SHORT_NAME_MIN = 2;
export const SHORT_NAME_MAX = 60;

/** What a short name accepts, said under the field before anything is sent. */
export const SHORT_NAME_HINT =
  "Lower-case letters and digits, starting with a letter, 2 to 60 characters. Join words with an " +
  "underscore, for example sales_ops. No spaces or hyphens.";

/** What is said when a short name is not in that form. Says what to change. */
export function shortNameProblem(value: string): string | null {
  const typed = value.trim();
  if (typed === "") {
    return "Give it a short name.";
  }
  if (typed.length < SHORT_NAME_MIN || typed.length > SHORT_NAME_MAX) {
    return "A short name is 2 to 60 characters long.";
  }
  if (/[A-Z]/.test(typed)) {
    return "Use lower-case letters only; capitals are not accepted in a short name.";
  }
  if (/[-\s]/.test(typed)) {
    return "Use an underscore between words; hyphens and spaces are not accepted in a short name.";
  }
  if (!SHORT_NAME_PATTERN.test(typed)) {
    return "Start with a letter, use only lower-case letters, digits and single underscores, and do not end with an underscore.";
  }
  return null;
}

/** A short name from a name a person typed, as a suggestion they may change. */
export function suggestedShortName(name: string): string {
  const joined = name
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .replace(/^[0-9_]+/, "");
  return joined.slice(0, SHORT_NAME_MAX).replace(/_+$/, "");
}

/** `brain.core.entitlement.CAPABILITY_RE`: a verb, a colon, and a dotted target that may end in `.*`. */
export const CAPABILITY_PATTERN = /^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*|\.\*)*$/;

/** What a capability accepts, said under the field before anything is sent. */
export const CAPABILITY_HINT =
  "A verb (read, write, invoke, approve or admin), a colon and what it reaches, in lower case, for example read:client.name or read:ticket.*.";

/** What is said when a capability is not in that form. */
export function capabilityProblem(value: string): string | null {
  const typed = value.trim();
  if (typed === "") {
    return "Name the capability to grant.";
  }
  return CAPABILITY_PATTERN.test(typed)
    ? null
    : "Write it as a verb, a colon and what it reaches, in lower case, for example read:client.name.";
}

/** What a reason is for, said under the field. */
export const REASON_HINT = "Why this is given. Required, up to 500 characters, and kept with the record.";

/** What an expiry means, said under the field. */
export const EXPIRY_HINT = "When it lapses, on this device's clock. Leave it empty for one that stands until somebody removes it.";

/** The longest reason any of these writes carries (`brain.govern_routes.REASON_CHARS`). */
export const REASON_MAX = 500;

/** An instant typed in a `datetime-local` field, as the API is sent it, or undefined for none. */
export function instantFrom(local: string): string | undefined {
  if (local.trim() === "") {
    return undefined;
  }
  const at = Date.parse(local);
  return Number.isNaN(at) ? undefined : new Date(at).toISOString();
}

/** Whether a typed expiry is already past on this device's clock. The API judges it again. */
export function alreadyPast(local: string, now: Date = new Date()): boolean {
  const at = instantFrom(local);
  return at !== undefined && Date.parse(at) <= now.getTime();
}

/** The API's problems about one field, by any of the names it may use for it. */
function problemsAbout(problems: readonly FieldProblem[], names: readonly string[]): readonly string[] {
  return problems.filter((one) => names.includes(one.field)).map((one) => one.message);
}

/**
 * One labelled field: the label, the hint saying what it accepts, the control, and what is wrong
 * with it, found here before submit or by the API after.
 */
export function Field({
  label,
  hint,
  problem,
  apiProblems = [],
  names = [],
  children,
}: {
  readonly label: string;
  /** What the field accepts, in words, shown before anything is submitted. */
  readonly hint?: string | undefined;
  /** What this page found wrong before sending, or null. */
  readonly problem?: string | null | undefined;
  readonly apiProblems?: readonly FieldProblem[] | undefined;
  /** The names the API may use for this field in a refusal. */
  readonly names?: readonly string[] | undefined;
  readonly children: (ids: { readonly id: string; readonly describedBy: string; readonly invalid: boolean }) => ReactNode;
}) {
  const id = useId();
  const hintId = `${id}-hint`;
  const problemId = `${id}-problem`;
  const said = [...(problem === null || problem === undefined ? [] : [problem]), ...problemsAbout(apiProblems, names)];
  const describedBy = [hint === undefined ? "" : hintId, said.length > 0 ? problemId : ""].filter((one) => one !== "").join(" ");
  return (
    <div data-slot="form-field" className="flex min-w-0 flex-col gap-1.5">
      <label htmlFor={id} className="text-[13px] font-medium text-ink">
        {label}
      </label>
      {hint === undefined ? null : (
        <p id={hintId} className="m-0 text-[12px] leading-snug text-dim">
          {hint}
        </p>
      )}
      {children({ id, describedBy, invalid: said.length > 0 })}
      {said.length === 0 ? null : (
        <ul id={problemId} aria-label={`Problems with ${label}`} className="m-0 list-none p-0 text-[12px] leading-snug text-crit">
          {said.map((one) => (
            <li key={one}>{one}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

const SELECT =
  "h-11 w-full min-w-0 rounded-md border border-input bg-panel px-2.5 text-sm text-ink shadow-xs outline-hidden focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring aria-invalid:border-destructive sm:h-9";

/** A native select, which is keyboard-complete and opens the phone's own picker. */
export function NativeSelect({
  id,
  describedBy,
  invalid,
  value,
  onChange,
  children,
  className,
}: {
  readonly id: string;
  readonly describedBy: string;
  readonly invalid: boolean;
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly children: ReactNode;
  readonly className?: string | undefined;
}) {
  return (
    <select
      id={id}
      aria-describedby={describedBy === "" ? undefined : describedBy}
      aria-invalid={invalid ? true : undefined}
      className={cn(SELECT, className)}
      value={value}
      onChange={(event) => {
        onChange(event.target.value);
      }}
    >
      {children}
    </select>
  );
}

/** A form's own sentence when nothing may be sent yet, drawn under its fields. */
export function FormProblem({ children }: { readonly children: ReactNode }) {
  return (
    <p role="alert" className="m-0 text-[12.5px] leading-snug text-crit">
      {children}
    </p>
  );
}

/** An instant as a person reads it, to the minute, in their own zone. */
export function whenWords(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "";
  }
  const at = new Date(value);
  if (Number.isNaN(at.getTime())) {
    return value;
  }
  return at.toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** A date as a person reads it. */
export function dayWords(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "";
  }
  const at = new Date(value);
  if (Number.isNaN(at.getTime())) {
    return value;
  }
  return at.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}
