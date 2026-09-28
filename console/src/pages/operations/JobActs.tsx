/**
 * Pause, resume and run now, each confirmed in a dialog that says what the worker will do and what
 * stops being kept true, and the sentence each leaves once the API has answered.
 *
 * One hook for the list and the job's own page, so the two cannot ask different questions about the
 * same act. Confirming sends the request; the API decides again whatever the page believed, and a
 * refusal is drawn in its words where the person is looking.
 *
 * Task ids: M27.8.13, M27.15.47
 */

import { useCallback, useState, type ReactNode } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { ConfirmDialog, FailureState, Note } from "../../components/kit";
import {
  ACTION_LABELS,
  actionConsequence,
  actionPath,
  actionQuestion,
  actionWarning,
  doneSentence,
  KEEP_IT,
  type JobAction,
  type JobRow,
} from "../jobsQuery";

interface Pending {
  readonly action: JobAction;
  readonly row: JobRow;
}

export interface JobActs {
  readonly choose: (action: JobAction, row: JobRow) => void;
  readonly busy: boolean;
  /** The dialog, drawn wherever the page puts it. */
  readonly dialog: ReactNode;
  /** What the last act did, or why it was refused. */
  readonly notice: ReactNode;
}

export function useJobActs(onChanged: () => void): JobActs {
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const confirm = useCallback(
    (asked: Pending) => {
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(actionPath(asked.action, asked.row.control), {
          method: "POST",
          body: {},
        });
        setBusy(false);
        setPending(null);
        if (!result.ok) {
          setDone(null);
          setFailure(result.failure);
          return;
        }
        setFailure(null);
        setDone(doneSentence(asked.action, asked.row));
        onChanged();
      })();
    },
    [onChanged],
  );

  const choose = useCallback((action: JobAction, row: JobRow) => {
    setFailure(null);
    setDone(null);
    setPending({ action, row });
  }, []);

  const warning = pending === null ? undefined : actionWarning(pending.action, pending.row);
  const dialog =
    pending === null ? null : (
      <ConfirmDialog
        open
        question={actionQuestion(pending.action, pending.row)}
        consequence={actionConsequence(pending.action, pending.row)}
        details={warning === undefined ? undefined : <p className="m-0">{warning}</p>}
        confirmLabel={ACTION_LABELS[pending.action]}
        cancelLabel={KEEP_IT}
        busy={busy}
        onConfirm={() => {
          confirm(pending);
        }}
        onCancel={() => {
          setPending(null);
        }}
      />
    );

  const notice =
    failure !== null ? (
      <FailureState failure={failure} />
    ) : done !== null ? (
      <div role="status" aria-live="polite">
        <Note>{done}</Note>
      </div>
    ) : null;

  return { choose, busy, dialog, notice };
}
