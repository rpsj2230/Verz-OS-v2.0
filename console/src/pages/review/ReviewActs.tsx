/**
 * Keeping and removing a holding, one or several, each confirmed in the API's own words.
 *
 * **The confirmation names the person and the grant, and says what the decision does** in
 * `brain.govern_people_routes`' sentences (`keeping`, `removing`), so a person agrees to what the
 * system will do rather than to a paraphrase. Several are one confirmation listing each holding and
 * what happens to it, sent as one request the route runs as that many single decisions; the page
 * then says, per holding, whether it was decided, so a partial refusal is stated.
 *
 * **Nothing here decides who may decide.** The route asks `govern.certify` under the row's lock
 * whatever was drawn, and a refused press is the API's refusal drawn where the person is looking.
 *
 * Task ids: M27.7.9, M27.16.1
 */

import { useCallback, useState, type ReactNode } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { ConfirmDialog, FailureState, Note } from "../../components/kit";
import {
  decisionBody,
  decisionLine,
  decisionQuestion,
  decisionsBody,
  decisionsQuestion,
  holdingKey,
  readReviewOutcomes,
  REVIEW_DECISION_API_PATH,
  REVIEW_DECISIONS_API_PATH,
  reviewOutcomeLine,
  type ReviewDecisionWord,
  type ReviewRow,
} from "../governPeopleQuery";
import { ACT_LABELS } from "./reviewActions";
import { holdingName } from "./reviewQuery";
import { nameOf, whenWords } from "./parts";

/** One review decision in flight, or several. */
type Pending =
  | { readonly rows: readonly [ReviewRow]; readonly decision: ReviewDecisionWord; readonly several: false }
  | { readonly rows: readonly ReviewRow[]; readonly decision: ReviewDecisionWord; readonly several: true };

/** What a success says: what, whose, and the instant the database recorded. */
export function decidedSentence(row: ReviewRow, decision: ReviewDecisionWord, decidedAt: string): string {
  const verb = decision === "keep" ? "kept" : "removed";
  return `${holdingName(row)} for ${nameOf({}, row.principal_id, row.display_name)} was ${verb} at ${whenWords(decidedAt)}.`;
}

function decidedAtOf(payload: unknown): string {
  const at = typeof payload === "object" && payload !== null ? (payload as { decided_at?: unknown }).decided_at : undefined;
  return typeof at === "string" ? at : "";
}

export interface ReviewActs {
  readonly decide: (row: ReviewRow, decision: ReviewDecisionWord) => void;
  readonly decideMany: (rows: readonly ReviewRow[], decision: ReviewDecisionWord) => void;
  readonly busy: boolean;
  /** The confirmation, the refusal and what was decided, drawn by the page where it chooses. */
  readonly drawn: ReactNode;
}

export function useReviewActs(
  sentences: { readonly keeping: string; readonly removing: string },
  onDecided: () => void,
): ReviewActs {
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [told, setTold] = useState<readonly string[]>([]);

  const decide = useCallback((row: ReviewRow, decision: ReviewDecisionWord) => {
    setFailure(null);
    setTold([]);
    setPending({ rows: [row], decision, several: false });
  }, []);
  const decideMany = useCallback((rows: readonly ReviewRow[], decision: ReviewDecisionWord) => {
    setFailure(null);
    setTold([]);
    setPending({ rows, decision, several: true });
  }, []);

  const send = useCallback(
    (chosen: Pending) => {
      setBusy(true);
      void (async () => {
        const result = chosen.several
          ? await request<unknown>(REVIEW_DECISIONS_API_PATH, { method: "POST", body: decisionsBody(chosen.rows, chosen.decision) })
          : await request<unknown>(REVIEW_DECISION_API_PATH, { method: "POST", body: decisionBody(chosen.rows[0], chosen.decision) });
        setBusy(false);
        setPending(null);
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        if (chosen.several) {
          const byKey = new Map(chosen.rows.map((row) => [holdingKey(row), row]));
          setTold(
            readReviewOutcomes(result.data).map((one) =>
              reviewOutcomeLine(byKey.get(`${one.kind}:${one.row_id}`), one, chosen.decision),
            ),
          );
        } else {
          setTold([decidedSentence(chosen.rows[0], chosen.decision, decidedAtOf(result.data))]);
        }
        onDecided();
      })();
    },
    [onDecided],
  );

  const drawn = (
    <>
      {failure === null ? null : <FailureState failure={failure} />}
      {told.length === 0 ? null : (
        <div role="status" className="flex flex-col gap-1">
          {told.map((line, index) => (
            <Note key={`${String(index)} ${line}`} kind="works">
              {line}
            </Note>
          ))}
        </div>
      )}
      <ConfirmDialog
        open={pending !== null}
        question={
          pending === null
            ? ""
            : pending.several
              ? decisionsQuestion(pending.decision)
              : decisionQuestion(pending.rows[0], pending.decision)
        }
        consequence={pending?.decision === "remove" ? sentences.removing : sentences.keeping}
        details={
          pending === null || !pending.several ? undefined : (
            <ul className="m-0 flex list-disc flex-col gap-1 pl-5">
              {pending.rows.map((row) => (
                <li key={holdingKey(row)}>{decisionLine(row, pending.decision)}</li>
              ))}
            </ul>
          )
        }
        confirmLabel={
          pending === null
            ? ""
            : pending.several
              ? pending.decision === "keep"
                ? ACT_LABELS.keepSelected
                : ACT_LABELS.removeSelected
              : pending.decision === "keep"
                ? ACT_LABELS.keep
                : ACT_LABELS.remove
        }
        cancelLabel={ACT_LABELS.decideLater}
        busy={busy}
        onConfirm={() => {
          if (pending !== null) {
            send(pending);
          }
        }}
        onCancel={() => {
          setPending(null);
        }}
      />
    </>
  );

  return { decide, decideMany, busy, drawn };
}
