/**
 * The parts every Knowledge form is written with: a labelled field that states its format before
 * anything is sent, a status line, the submit button, a review date field and the words they share.
 * No write lives here, so a page that only borrows a label reaches none (`tests/console-audit.test.ts`
 * follows each write to the pages whose imports reach it).
 *
 * **Every form says what it accepts before anything is sent.** The file forms name the types and
 * sizes this install takes, read from the API's own options; the link form says it takes an https
 * address; a review date says it must be after today. A draft a form can already tell the API would
 * refuse is said beside its field and never sent.
 *
 * Task ids: M27.15.40, M27.16.1
 */

import { useId, type ReactNode } from "react";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { isAfterToday } from "../knowledgeLifecycleQuery";
import type { TypeChoice } from "../knowledgeQuery";

// ------------------------------------------------------------------ the words
export const FILE_LABEL = "File";
export const FILES_LABEL = "Files";
export const KIND_LABEL = "Type";
export const LEVEL_LABEL = "Visible to";
export const DEPARTMENT_LABEL = "Department";
export const ADDRESS_LABEL = "Web page address";
export const REVIEW_LABEL = "Next review by";
export const REASON_LABEL = "Why the whole company should read it";
export const STEWARD_LABEL = "New steward's person id";

export const ADD_FILE = "Add the file";
export const ADD_LINK = "Add the page";
export const QUEUE_FILES = "Queue the files";
export const CHECK_AGAIN = "Check again";
export const VERIFY = "Verify";
export const ADD_VERSION = "Add as the newer version";
export const ASK_COMPANY = "Ask for approval";
export const HAND_OVER = "Hand over";

export const ADDING = "Adding the document.";
export const FETCHING = "Fetching and reading the page.";
export const QUEUEING = "Sending the files to the queue.";

/** What each field says before a draft is sent: the format it takes. */
export const ADDRESS_HINT = "The whole address as your browser shows it, starting with https. It is read once, now.";
export const REVIEW_HINT = "A day after today. The steward is asked to look again on that day.";
export const STEWARD_HINT =
  "Their id from Advanced on their People page: letters, digits, dots, @, hyphens and underscores. They must be able to read the document or add to its department.";
export const REASON_HINT = "Up to 500 characters. The approver reads it on the Approvals screen.";

/** Said beside a field left empty, or a draft this form can tell will be refused. */
export const PROBLEMS = {
  file: "Choose the file to add.",
  files: "Choose the files to add.",
  type: "This file is not one of the types listed above.",
  size: "This file is larger than this install accepts for its type.",
  kind: "Choose what type of document this is.",
  department: "Choose the department it is for.",
  review: "Choose the next review date.",
  reviewAhead: "The review date has to be after today.",
  reason: "Say why the whole company should read it.",
  steward: "Enter the person id of the new steward.",
} as const;

export const NEW_VERSION_CONSEQUENCE =
  "The newer version is added where this one sits, with the same steward, and answers use it from now on. " +
  "This version stays in the history, readable by the people who could read it.";
export const HAND_OVER_CONSEQUENCE =
  "They become its steward, are told so, and are asked when it falls due for review. The change is recorded in the audit trail.";

/** Said for a file the bulk form did not send, and why. */
export const NOT_SENT_TYPE = "not sent: it is not one of the types listed.";
export const NOT_SENT_SIZE = "not sent: it is larger than this install accepts for its type.";
export const NOT_SENT_QUEUE_FULL = "not sent, because the queue was full. Send it again later.";

// ------------------------------------------------------------------ the parts
export const SELECT =
  "h-11 w-full min-w-0 rounded-md border border-input bg-panel px-2.5 text-sm text-ink shadow-xs outline-hidden focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring sm:h-9";

export function Field({
  label,
  hint,
  problems = [],
  children,
}: {
  readonly label: string;
  readonly hint?: string | undefined;
  readonly problems?: readonly string[];
  readonly children: (id: string, describedBy: string | undefined) => ReactNode;
}) {
  const id = useId();
  const hintId = useId();
  return (
    <div data-slot="field" className="flex min-w-0 flex-col gap-1.5">
      <label htmlFor={id} className="text-[13px] font-medium text-ink">
        {label}
      </label>
      {children(id, hint === undefined ? undefined : hintId)}
      {hint === undefined ? null : (
        <p id={hintId} className="m-0 text-[12px] leading-snug text-dim">
          {hint}
        </p>
      )}
      {problems.map((one) => (
        <p key={one} className="m-0 text-[12.5px] leading-snug text-crit">
          {one}
        </p>
      ))}
    </div>
  );
}

export function Status({ children }: { readonly children: ReactNode }) {
  return (
    <p role="status" className="m-0 text-[12.5px] leading-snug text-ink">
      {children}
    </p>
  );
}

export function Submit({ label, busy }: { readonly label: string; readonly busy: boolean }) {
  return (
    <div className="flex justify-end">
      <Button type="submit" className="min-h-11 sm:min-h-9" disabled={busy}>
        {label}
      </Button>
    </div>
  );
}

export const FORM = "flex min-w-0 flex-col gap-4";

/** A day and what is wrong with it, or null. Said before anything is sent. */
export function reviewProblem(day: string, today: Date = new Date()): string | null {
  if (day === "") {
    return PROBLEMS.review;
  }
  return isAfterToday(day, today) ? null : PROBLEMS.reviewAhead;
}

export function ReviewField({ value, onChange, problems }: { readonly value: string; readonly onChange: (day: string) => void; readonly problems: readonly string[] }) {
  return (
    <Field label={REVIEW_LABEL} hint={REVIEW_HINT} problems={problems}>
      {(id, describedBy) => (
        <Input
          id={id}
          type="date"
          name="review_by"
          className="h-11 sm:h-9"
          aria-describedby={describedBy}
          value={value}
          onChange={(event) => {
            onChange(event.target.value);
          }}
        />
      )}
    </Field>
  );
}

/** What the file inputs accept, in words, from the API's own types and sizes. */
export function acceptsWords(types: readonly TypeChoice[]): string {
  const bySize = new Map<number, string[]>();
  for (const one of types) {
    bySize.set(one.maxBytes, [...(bySize.get(one.maxBytes) ?? []), ...one.extensions]);
  }
  const parts = [...bySize.entries()].map(([bytes, extensions]) => {
    const megabytes = bytes / (1024 * 1024);
    const size = megabytes >= 1 ? `${String(Math.round(megabytes * 10) / 10)} MB` : `${String(Math.round(bytes / 1024))} KB`;
    return `${extensions.join(", ")} up to ${size}`;
  });
  return `Plain text, Markdown, PDF or Word: ${parts.join("; ")}.`;
}

