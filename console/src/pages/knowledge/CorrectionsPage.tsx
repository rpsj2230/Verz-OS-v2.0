/**
 * Corrections, a tab of Knowledge: what somebody said the right answer is, held about the document
 * the answer cited, waiting for whoever may add a new version of it (M16.6.5, M16.6.6, M16.7.6).
 *
 * **The list names the document and how many corrections said the same, never who said it or what.**
 * The words are read only when one is opened, through `GET /knowledge/corrections/{id}`, which the
 * API answers only for somebody who may decide it; everyone else gets the one refusal a correction
 * that does not exist gets. So the list a reviewer scans carries no free text, which is the rule the
 * Approvals screen keeps after #381.
 *
 * **Opened, the words are shown beside who will read them**, in the API's own plain sentence, because
 * a person may have read more than the document's audience when they wrote them, and the reviewer is
 * the guard (`brain.knowledge.candidates.APPROVED_WORDS_ARE_READ_BY_EVERYONE_WHO_READS_THE_DOCUMENT`).
 *
 * **Approving makes a new version of the document**, which needs its review date as any new version
 * does, and is confirmed before it is sent. Rejecting needs a reason, which is kept. Nothing on the
 * page counts what the reader was not shown.
 *
 * Task ids: M16.6.5, M16.6.6, M16.7.6
 */

import { FileText } from "lucide-react";
import { useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { ConfirmDialog, EmptyState, Fact, FactList, FailureState, LoadingState, PageHeader, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";
import { FailureNotice } from "../../ui/FailureNotice";
import { CORRECTIONS_API_PATH, correctionDecisionPath, correctionReviewPath, defaultReviewDay, instantOf, LIFECYCLE_FIELDS } from "../knowledgeLifecycleQuery";
import { REVIEW_HINT, REVIEW_LABEL, reviewProblem } from "./formParts";
import { dayWords, KNOWLEDGE_HEADING, LIBRARY_ADDRESS } from "./knowledgeDocuments";

export const CORRECTIONS_HEADING = "Corrections";
export const CORRECTIONS_LEDE =
  "What somebody said the right answer is, about a document an answer cited. It changes nothing until you approve it as a new version of that document.";
export const LOADING_CORRECTIONS = "Loading corrections.";
export const NONE_WAITING = "No correction is waiting for your decision";
export const NONE_WAITING_DESCRIPTION =
  "When somebody corrects an answer that cited a document you look after, and says what is right, it appears here.";
export const OPEN = "Review";
export const APPROVE = "Approve as a new version";
export const REJECT = "Reject";
export const REASON_LABEL = "Why it is rejected";
export const REASON_MISSING = "Say why it is rejected.";
export const CONFIRM_QUESTION = "Approve these words as a new version of the document?";
export const CONFIRM_CONSEQUENCE =
  "The document gets a new version that keeps every passage it has and adds these words after them. Answers use it from now on.";
export const CANCEL = "Keep it waiting";

/** One correction in the list, as this console holds it. */
export interface CorrectionRow {
  readonly candidateId: string;
  readonly itemId: string;
  readonly title: string;
  readonly instances: number;
  readonly raisedAt?: string;
}

/** One correction opened for review: the row, the words and who would read them. */
export interface CorrectionReview extends CorrectionRow {
  readonly words: string;
  readonly audience: string;
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function readRow(value: unknown): CorrectionRow | null {
  const row = typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
  const candidateId = said(row?.["candidate_id"]);
  const itemId = said(row?.["item_id"]);
  if (row === null || candidateId === undefined || itemId === undefined) {
    return null;
  }
  const raisedAt = said(row["raised_at"]);
  const instances = typeof row["instances"] === "number" ? row["instances"] : 1;
  return { candidateId, itemId, title: said(row["title"]) ?? itemId, instances, ...(raisedAt === undefined ? {} : { raisedAt }) };
}

/** `CorrectionsView` as this console holds it. */
export function readCorrections(payload: unknown): readonly CorrectionRow[] {
  const body = typeof payload === "object" && payload !== null ? (payload as Record<string, unknown>) : {};
  return (Array.isArray(body["items"]) ? (body["items"] as readonly unknown[]) : []).flatMap((one) => {
    const row = readRow(one);
    return row === null ? [] : [row];
  });
}

/** `CorrectionReviewView` as this console holds it, or null for anything else. */
export function readReview(payload: unknown): CorrectionReview | null {
  const row = readRow(payload);
  const body = typeof payload === "object" && payload !== null ? (payload as Record<string, unknown>) : {};
  const words = said(body["words"]);
  const audience = said(body["audience"]);
  return row === null || words === undefined || audience === undefined ? null : { ...row, words, audience };
}

/** How many corrections said the same, in words. Only ever about this one correction. */
export function instancesWords(instances: number): string {
  return instances <= 1 ? "One correction" : `${instances} corrections said the same`;
}

function Decide({ review, onDone }: { readonly review: CorrectionReview; readonly onDone: () => void }) {
  const [day, setDay] = useState(defaultReviewDay());
  const [reason, setReason] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const send = (body: Record<string, unknown>) => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(correctionDecisionPath(review.candidateId), { method: "POST", body });
      setBusy(false);
      setConfirming(false);
      setFailure(result.ok ? null : result.failure);
      if (result.ok) {
        onDone();
      }
    })();
  };

  const onApprove = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const found = reviewProblem(day);
    setProblem(found);
    if (found === null && instantOf(day) !== null) {
      setConfirming(true);
    }
  };

  return (
    <form className="flex min-w-0 flex-col gap-3" aria-label={`Decide the correction to ${review.title}`} onSubmit={onApprove} noValidate>
      {failure === null ? null : <FailureNotice failure={failure} fields={LIFECYCLE_FIELDS} />}
      <div className="flex flex-col gap-1.5">
        <label htmlFor={`review-${review.candidateId}`} className="text-[13px] font-medium text-ink">
          {REVIEW_LABEL}
        </label>
        <Input id={`review-${review.candidateId}`} type="date" name="review_by" className="h-11 sm:h-9" value={day} onChange={(event) => setDay(event.target.value)} />
        <p className="m-0 text-[12px] text-dim">{REVIEW_HINT} Needed to approve.</p>
        {problem === null ? null : <p className="m-0 text-[12.5px] text-crit">{problem}</p>}
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor={`reason-${review.candidateId}`} className="text-[13px] font-medium text-ink">
          {REASON_LABEL}
        </label>
        <Textarea id={`reason-${review.candidateId}`} name="reason" maxLength={400} value={reason} onChange={(event) => setReason(event.target.value)} />
        <p className="m-0 text-[12px] text-dim">Needed to reject. Kept with the correction. Up to 400 characters.</p>
      </div>
      <div className="flex flex-wrap justify-end gap-2">
        <Button
          type="button"
          variant="outline"
          className="min-h-11 sm:min-h-9"
          disabled={busy}
          onClick={() => {
            if (reason.trim() === "") {
              setProblem(REASON_MISSING);
              return;
            }
            setProblem(null);
            send({ approve: false, reason: reason.trim() });
          }}
        >
          {REJECT}
        </Button>
        <Button type="submit" className="min-h-11 sm:min-h-9" disabled={busy}>
          {APPROVE}
        </Button>
      </div>
      <ConfirmDialog
        open={confirming}
        question={CONFIRM_QUESTION}
        consequence={CONFIRM_CONSEQUENCE}
        details={<p className="m-0 text-[13px] text-ink">{review.audience}</p>}
        confirmLabel={APPROVE}
        cancelLabel={CANCEL}
        busy={busy}
        onConfirm={() => {
          send({ approve: true, review_by: instantOf(day) });
        }}
        onCancel={() => {
          setConfirming(false);
        }}
      />
    </form>
  );
}

function Opened({ row, onDone }: { readonly row: CorrectionRow; readonly onDone: () => void }) {
  const answer = useResource<unknown>(correctionReviewPath(row.candidateId), 0);
  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  const review = answer.busy ? null : readReview(answer.data);
  if (review === null) {
    return <LoadingState label={LOADING_CORRECTIONS} />;
  }
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <FactList>
        <Fact label="What they say is right">
          <span className="whitespace-pre-wrap [overflow-wrap:anywhere]">{review.words}</span>
        </Fact>
        <Fact label="Who will see it">{review.audience}</Fact>
      </FactList>
      <Decide review={review} onDone={onDone} />
    </div>
  );
}

export function CorrectionsPage() {
  const [version, setVersion] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const answer = useResource<unknown>(CORRECTIONS_API_PATH, version);
  const rows = answer.failure === null && !answer.busy ? readCorrections(answer.data) : null;
  const changed = () => {
    setOpen(null);
    setVersion((was) => was + 1);
  };

  let body;
  if (answer.failure !== null) {
    body = <FailureState failure={answer.failure} />;
  } else if (rows === null) {
    body = <LoadingState label={LOADING_CORRECTIONS} />;
  } else if (rows.length === 0) {
    body = <EmptyState title={NONE_WAITING} description={NONE_WAITING_DESCRIPTION} icon={<FileText aria-hidden />} />;
  } else {
    body = (
      <ul className="m-0 flex list-none flex-col gap-4 p-0">
        {rows.map((row) => (
          <li key={row.candidateId} className="flex min-w-0 flex-col gap-3 border-b border-line pb-4 last:border-b-0 last:pb-0">
            <FactList>
              <Fact label="Document">{row.title}</Fact>
              <Fact label="Said by">{instancesWords(row.instances)}</Fact>
              <Fact label="First said">{dayWords(row.raisedAt) ?? "Not recorded"}</Fact>
            </FactList>
            {open === row.candidateId ? (
              <Opened row={row} onDone={changed} />
            ) : (
              <div className="flex justify-end">
                <Button
                  variant="outline"
                  className="min-h-11 sm:min-h-9"
                  onClick={() => {
                    setOpen(row.candidateId);
                  }}
                >
                  {OPEN}
                </Button>
              </div>
            )}
          </li>
        ))}
      </ul>
    );
  }

  return (
    <div data-slot="corrections-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={[{ label: KNOWLEDGE_HEADING, to: LIBRARY_ADDRESS }, { label: CORRECTIONS_HEADING }]} title={CORRECTIONS_HEADING} lede={CORRECTIONS_LEDE} />
      <SectionCard title={CORRECTIONS_HEADING}>{body}</SectionCard>
    </div>
  );
}
