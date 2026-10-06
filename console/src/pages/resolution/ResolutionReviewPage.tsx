/**
 * Possible duplicates on the shared page kit: every pair of records the Brain could not settle on
 * its own, with the two records by name, why the pair is here and what matches, and a decision for
 * each, "These are the same" or "These are different", confirmed with a reason in a sentence.
 *
 * **Nothing here decides who may decide, or which pairs a reader is shown.** The route asks for
 * `admin:entity_merge` over everything and shows a pair only to a reader who sees both of its
 * records; anybody else gets the API's one refusal, drawn as the API sent it. A pair is never
 * filtered or reordered here, because a second filter in the browser is a second answer to who
 * may see a record, and the copy an attacker edits.
 *
 * **One card per pair rather than a table.** A decision is about two records side by side and the
 * lines of evidence under them, which is a block of several lines; a row of columns holding it is
 * either wider than a phone or cuts off the evidence, which is the part being judged. The Approvals
 * card is shaped the same way for the same reason.
 *
 * **A decision asks why before it is sent, and the reason is the person's own.** The route takes a
 * sentence of one to four hundred characters and records it as the merge's reason in their name,
 * so the confirmation holds a text box and a blank one is said beside the box rather than sent.
 * Rejected: a fixed list of reasons, which is what Approvals uses for a rejection. Whether two
 * records are one company is decided on what the person checked (a registration number, an
 * address, a phone call), and that is the sentence an auditor reading the merge later needs.
 *
 * **After a decision the queue is read again**, so the page shows what the database holds; a pair
 * somebody else decided first answers 409, and its sentence is shown and the queue re-read too.
 *
 * **What was put in Advanced rather than on the card**: the item's identifier, each record's
 * connector and kind as the system names them, the matcher's own reason (the card says why in
 * plain words, see `resolutionReviewQuery.WHY_BY_ORIGIN`), and which weight table produced the
 * evidence. Whether that table was measured is said on the page in words, because it is a fact
 * about the evidence somebody is acting on (`brain.resolution.review.
 * A_READER_JUDGING_EVIDENCE_IS_TOLD_WHETHER_ANYTHING_MEASURED_IT`).
 *
 * **Under the queue, how pairs are weighed** (`WeightsSection`): the weights that produced the
 * evidence above, and the weekly fit waiting for the same reviewers to approve it. It is read on
 * its own, so a queue that fails to load still leaves the weights readable and the other way round.
 *
 * Task ids: M14.6.4, M14.8.5, M14.4.4, M14.8.3
 */

import { useId, useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import {
  Advanced,
  ConfirmDialog,
  EmptyState,
  Fact,
  FactList,
  FailureState,
  LoadingState,
  Note,
  PageHeader,
  SectionCard,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Label } from "../../components/ui/label";
import { Textarea } from "../../components/ui/textarea";
import {
  confirmLabelFor,
  consequenceFor,
  decidedSentence,
  decisionApiPath,
  decisionBody,
  DIFFERENT,
  DUPLICATES_LABEL,
  DUPLICATES_LEDE,
  EVIDENCE_LABEL,
  FROM_LABEL,
  KEEP_WAITING,
  NO_EVIDENCE,
  NOT_DECIDED,
  NOTHING_WAITING,
  NOTHING_WAITING_TITLE,
  questionFor,
  READING_PAIRS,
  readDecided,
  readNotChanged,
  readQueue,
  REASON_HINT,
  REASON_LABEL,
  reasonProblem,
  REVIEW_API_PATH,
  SAME,
  sentence,
  strengthSummary,
  UNMEASURED,
  UNREADABLE_ANSWER,
  WAITING_SINCE,
  waitingSentence,
  whereFrom,
  whyWords,
  type Decision,
  type ReviewCard,
  type ReviewQueueBody,
  type ReviewRecord,
} from "../resolutionReviewQuery";
import { when } from "../sessionsQuery";
import { WeightsSection } from "./WeightsSection";

/** What the page was told after a decision: done, or somebody else's decision in the API's words. */
interface Told {
  readonly sentence: string;
  readonly done: boolean;
}

interface Asking {
  readonly card: ReviewCard;
  readonly decision: Decision;
}

function pairName(card: ReviewCard): string {
  return `${card.left.label} and ${card.right.label}`;
}

function RecordBlock({ record }: { readonly record: ReviewRecord }) {
  return (
    <div data-slot="pair-record" className="min-w-0 rounded-md border border-line bg-sunk px-3 py-2">
      <p className="m-0 text-[13.5px] font-semibold text-ink [overflow-wrap:anywhere]">{record.label}</p>
      <p className="m-0 mt-0.5 text-[12px] text-dim">
        {FROM_LABEL} {whereFrom(record)}
      </p>
    </div>
  );
}

function PairCard({ card, busy, onAsk }: { readonly card: ReviewCard; readonly busy: boolean; readonly onAsk: (asking: Asking) => void }) {
  const name = pairName(card);
  return (
    <SectionCard
      title={name}
      headingLevel="h2"
      lede={whyWords(card)}
      footer={
        <p data-slot="pair-waiting" className="m-0 text-[12px] text-dim">
          {WAITING_SINCE} {when(card.raised_at)}.
        </p>
      }
    >
      <div className="grid min-w-0 grid-cols-1 gap-2 sm:grid-cols-2">
        <RecordBlock record={card.left} />
        <RecordBlock record={card.right} />
      </div>
      <h3 className="m-0 mt-3 text-[12.5px] font-semibold text-ink">{EVIDENCE_LABEL}</h3>
      {card.lines.length === 0 ? (
        <p className="m-0 mt-1 text-[13px] text-body">{NO_EVIDENCE}</p>
      ) : (
        <ul data-slot="pair-evidence" className="m-0 mt-1 flex list-disc flex-col gap-0.5 pl-5 text-[13px] text-body">
          {card.lines.map((line) => (
            <li key={line}>{sentence(line)}</li>
          ))}
        </ul>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          size="sm"
          className="min-h-11 sm:min-h-8"
          disabled={busy}
          aria-label={`${SAME}: ${name}`}
          onClick={() => {
            onAsk({ card, decision: "merge" });
          }}
        >
          {SAME}
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="min-h-11 sm:min-h-8"
          disabled={busy}
          aria-label={`${DIFFERENT}: ${name}`}
          onClick={() => {
            onAsk({ card, decision: "reject" });
          }}
        >
          {DIFFERENT}
        </Button>
      </div>
    </SectionCard>
  );
}

function PairList({ body, onDecided }: { readonly body: ReviewQueueBody; readonly onDecided: (told: Told) => void }) {
  const [asking, setAsking] = useState<Asking | null>(null);
  const [reason, setReason] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const fieldId = useId();

  function decide(chosen: Asking): void {
    const wrong = reasonProblem(reason);
    if (wrong !== null) {
      setProblem(wrong);
      return;
    }
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(decisionApiPath(chosen.card.item_id), {
        method: "POST",
        body: decisionBody(chosen.decision, reason),
      });
      setBusy(false);
      if (!result.ok) {
        const notChanged = result.failure.status === 409 ? readNotChanged(result.body) : null;
        if (notChanged === null) {
          setFailure(result.failure);
          return;
        }
        setAsking(null);
        onDecided({ sentence: notChanged.sentence, done: false });
        return;
      }
      const decided = readDecided(result.data, chosen.card.item_id);
      setAsking(null);
      onDecided({ sentence: decidedSentence(chosen.decision, decided?.merged ?? false), done: true });
    })();
  }

  if (body.cards.length === 0) {
    return <EmptyState title={NOTHING_WAITING_TITLE} description={NOTHING_WAITING} />;
  }
  const summary = strengthSummary(body.by_strongest);
  const unmeasured = body.cards.some((card) => !card.calibrated);
  return (
    <>
      <p data-slot="pairs-summary" className="m-0 text-[13px] text-body">
        {waitingSentence(body.cards.length)}
        {summary === null ? null : ` ${summary}`}
      </p>
      {unmeasured ? <Note>{UNMEASURED}</Note> : null}
      {body.cards.map((card) => (
        <PairCard
          key={card.item_id}
          card={card}
          busy={busy}
          onAsk={(chosen) => {
            setFailure(null);
            setProblem(null);
            setReason("");
            setAsking(chosen);
          }}
        />
      ))}
      <Advanced>
        <FactList>
          {body.cards.map((card) => (
            <Fact key={card.item_id} label={pairName(card)}>
              <span className="font-mono text-[11.5px]">{card.item_id}</span>
              <span className="block font-mono text-[11px] text-dim">
                {card.left.source}/{card.left.entity} and {card.right.source}/{card.right.entity}
              </span>
              <span className="block text-[11.5px] text-dim">
                {card.origin}: {card.why}
              </span>
              <span className="block font-mono text-[11px] text-dim">
                {card.weight_version}
                {card.calibrated ? "" : " (not calibrated)"}
              </span>
            </Fact>
          ))}
        </FactList>
      </Advanced>
      <ConfirmDialog
        open={asking !== null}
        question={asking === null ? "" : questionFor(asking.decision)}
        consequence={asking === null ? "" : consequenceFor(asking.decision)}
        details={
          asking === null ? undefined : (
            <div className="flex min-w-0 flex-col gap-1.5">
              <p className="m-0 text-[13px] font-medium text-ink">{pairName(asking.card)}</p>
              <Label htmlFor={fieldId}>{REASON_LABEL}</Label>
              <p id={`${fieldId}-hint`} className="m-0 text-[12px] leading-snug text-dim">
                {REASON_HINT}
              </p>
              <Textarea
                id={fieldId}
                name="reason"
                value={reason}
                aria-invalid={problem !== null || undefined}
                aria-describedby={problem === null ? `${fieldId}-hint` : `${fieldId}-hint ${fieldId}-problem`}
                onChange={(event) => {
                  setReason(event.target.value);
                  setProblem(null);
                }}
              />
              {problem === null ? null : (
                <p id={`${fieldId}-problem`} className="m-0 text-[12px] text-crit">
                  {problem}
                </p>
              )}
              {failure === null ? null : <FailureState failure={failure} title={NOT_DECIDED} />}
            </div>
          )
        }
        confirmLabel={asking === null ? SAME : confirmLabelFor(asking.decision)}
        cancelLabel={KEEP_WAITING}
        danger={false}
        busy={busy}
        onConfirm={() => {
          if (asking !== null) {
            decide(asking);
          }
        }}
        onCancel={() => {
          setAsking(null);
        }}
      />
    </>
  );
}

export function ResolutionReviewPage() {
  const [version, setVersion] = useState(0);
  const [told, setTold] = useState<Told | null>(null);
  const answer = useResource<unknown>(REVIEW_API_PATH, version);

  let content;
  if (answer.busy) {
    content = <LoadingState label={READING_PAIRS} />;
  } else if (answer.failure !== null) {
    content = <FailureState failure={answer.failure} />;
  } else {
    const body = readQueue(answer.data);
    content =
      body === null ? (
        <Note>{UNREADABLE_ANSWER}</Note>
      ) : (
        <PairList
          body={body}
          onDecided={(next) => {
            setTold(next);
            setVersion((count) => count + 1);
          }}
        />
      );
  }
  return (
    <div data-slot="duplicates-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={[{ label: DUPLICATES_LABEL }]} title={DUPLICATES_LABEL} lede={DUPLICATES_LEDE} />
      {told === null ? null : (
        <div role="status">
          <Note kind={told.done ? "done" : "info"}>{told.sentence}</Note>
        </div>
      )}
      {content}
      <WeightsSection />
    </div>
  );
}
