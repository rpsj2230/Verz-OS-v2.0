/**
 * A destructive act's second step as a modal: what will happen, to what, and a way out.
 *
 * **The same contract as `components/ConfirmAction.tsx`, as a dialog.** The in-page confirmation
 * replaces the control that opened it, which is right beside a row and wrong for an act started
 * from a menu or a bulk bar, where there is no control left to replace. This takes the same six
 * props, so `tests/destructive-confirmed.test.ts` reads it the same way: a write sent from its
 * `onConfirm` is a confirmed write, and every use must name a question ending in a question mark,
 * a consequence, both labels and both handlers. `tests/support/writes.ts` names both elements.
 *
 * **Focus opens on the choice that changes nothing, Escape takes it, and focus goes back to the
 * opener.** Radix's alert dialog focuses its Cancel first; `ui/alert-dialog.tsx` adds the focus
 * return for a dialog opened from state, and `returnFocusTo` covers an opener that is gone.
 *
 * **It decides nothing.** Confirming sends the request; the API accepts or refuses it whatever this
 * dialog believed about the row, and the page renders the API's answer.
 *
 * Task ids: M27.10.2
 */

import type { ReactNode } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "../ui/alert-dialog";

export interface ConfirmDialogProps {
  readonly open: boolean;
  /** The question, naming the thing: "Archive Ticket triage?" */
  readonly question: string;
  /** What happens if they go ahead, in the API's words where it has some. */
  readonly consequence: string;
  /** The facts being agreed to, such as the rows a bulk act will change. */
  readonly details?: ReactNode | undefined;
  /** The button that does it, as a verb. */
  readonly confirmLabel: string;
  /** The button that changes nothing. */
  readonly cancelLabel: string;
  readonly busy?: boolean | undefined;
  readonly onConfirm: () => void;
  readonly onCancel: () => void;
  readonly returnFocusTo?: HTMLElement | null | undefined;
}

export function ConfirmDialog({
  open,
  question,
  consequence,
  details,
  confirmLabel,
  cancelLabel,
  busy = false,
  onConfirm,
  onCancel,
  returnFocusTo,
}: ConfirmDialogProps) {
  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          onCancel();
        }
      }}
    >
      <AlertDialogContent data-slot="confirm-dialog" returnFocusTo={returnFocusTo}>
        <AlertDialogHeader>
          <AlertDialogTitle>{question}</AlertDialogTitle>
          <AlertDialogDescription>{consequence}</AlertDialogDescription>
        </AlertDialogHeader>
        {details === undefined ? null : <div className="min-w-0 text-sm text-body">{details}</div>}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>{cancelLabel}</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={busy}
            onClick={(event) => {
              // The dialog stays open until the page says the act is done or refused, so a
              // failure is drawn where the person is looking rather than after the dialog closed.
              event.preventDefault();
              onConfirm();
            }}
          >
            {confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
