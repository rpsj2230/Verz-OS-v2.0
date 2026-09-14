/**
 * The approvals waiting on this reader, as cards a phone can read, and one approval on its own.
 *
 * **Cards, not a table.** An approval is an artefact of several lines and four facts, and a row
 * of columns holding one is either wider than a phone or truncates the artefact, which is the
 * part a person is approving. So each approval is a card in one column, every long value
 * breaks where it has to, and `styles/approvals.css` states the phone as its base case.
 *
 * **Nothing on this page decides who is offered what.** The API builds each card at the
 * reader's reach and filters before it bounds, and this page draws what arrived, in the order it
 * arrived. There is no count above the list and no card drawn for an approval the reader may not
 * decide. See `AN_APPROVAL_CARD_DRAWS_WHAT_WILL_HAPPEN_AND_COUNTS_NOTHING`.
 *
 * **Deciding is not on this page, and the page says so.** `brain.approval_routes` serves reads
 * only, because nothing stores a suspension yet and a verdict with nowhere to be kept is one
 * that can be given twice. A page of approvals with no buttons and no sentence would read as a
 * page that is broken; `DECIDING_IS_NOT_HERE` is the sentence.
 *
 * **One component for the queue and for one card**, at `/approvals` and
 * `/approvals/:suspensionId`. The single card is where a link from a chat message lands, and its
 * refusal is the API's sentence, which is the same for an approval that is not the reader's and
 * one that does not exist.
 *
 * Task ids: M35.3.1.2
 */

import "../styles/approvals.css";
import { Link, useParams } from "react-router-dom";
import { useResource } from "../api/useResource";
import { Notice } from "../ui/Notice";
import {
  approvalApiPath,
  APPROVALS_API_PATH,
  readApprovalCard,
  readApprovalQueue,
  type ApprovalCardView,
} from "./approvalsQuery";
import { SOMETHING_DID_NOT_WORK } from "./Overview";

/** The page's heading. */
export const APPROVALS_HEADING = "Approvals";

/** Under the heading. Says what the list is, and nothing about what it is not. */
export const APPROVALS_LEDE = "Actions waiting for you to decide, soonest to lapse first.";

/** Under the lede, until a store exists to keep a decision. */
export const DECIDING_IS_NOT_HERE = "Approving and rejecting are not available on this page yet.";

/** An empty queue, whichever of the reasons it is empty. */
export const NO_APPROVALS = "Nothing is waiting for you.";

/** A truncated queue. A fact about there being more, and never a figure. */
export const MORE_APPROVALS = "There are more approvals than this page shows.";

/** The accessible name of the list. */
export const APPROVAL_LIST_LABEL = "Approvals waiting for you";

/** The labels of a card's facts. */
export const RUNS_AS_LABEL = "Runs as";
export const RAISED_LABEL = "Raised";
export const LAPSES_LABEL = "Lapses";

/** The link from a card in the queue to the same card on its own. */
export const OPEN_ON_ITS_OWN = "Open on its own";

/** The console address of the queue. */
export const APPROVALS_ADDRESS = "/approvals";

/** The console address of one approval. */
export function approvalAddress(suspensionId: string): string {
  return `${APPROVALS_ADDRESS}/${encodeURIComponent(suspensionId)}`;
}

function When({ at }: { readonly at: string }) {
  return (
    <time dateTime={at}>
      {new Date(at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}
    </time>
  );
}

export function ApprovalCard({
  card,
  linked,
}: {
  readonly card: ApprovalCardView;
  readonly linked: boolean;
}) {
  return (
    <article className="approval-card">
      <pre className="approval-card__artefact">{card.artefact}</pre>
      <dl className="approval-card__facts">
        <dt className="approval-card__label">{RUNS_AS_LABEL}</dt>
        <dd className="approval-card__value">{card.runsAs}</dd>
        <dt className="approval-card__label">{RAISED_LABEL}</dt>
        <dd className="approval-card__value">
          <When at={card.raisedAt} />
        </dd>
        <dt className="approval-card__label">{LAPSES_LABEL}</dt>
        <dd className="approval-card__value">
          <When at={card.expiresAt} />
        </dd>
      </dl>
      {linked ? (
        <Link className="approval-card__link" to={approvalAddress(card.suspensionId)}>
          {OPEN_ON_ITS_OWN}
        </Link>
      ) : null}
    </article>
  );
}

function Busy() {
  return (
    <p className="note" role="status">
      Loading.
    </p>
  );
}

function QueueView() {
  const answer = useResource<unknown>(APPROVALS_API_PATH);
  if (answer.failure) {
    return (
      <Notice title={SOMETHING_DID_NOT_WORK} traceId={answer.failure.traceId}>
        <p>{answer.failure.message}</p>
      </Notice>
    );
  }
  if (answer.busy) {
    return <Busy />;
  }
  const read = readApprovalQueue(answer.data);
  if (read === null) {
    return null;
  }
  return (
    <>
      {read.cards.length === 0 ? (
        <p className="note">{NO_APPROVALS}</p>
      ) : (
        <ul className="approval-list" aria-label={APPROVAL_LIST_LABEL}>
          {read.cards.map((card) => (
            <li key={card.suspensionId}>
              <ApprovalCard card={card} linked />
            </li>
          ))}
        </ul>
      )}
      {read.truncated ? <p className="note">{MORE_APPROVALS}</p> : null}
    </>
  );
}

function OneView({ suspensionId }: { readonly suspensionId: string }) {
  const answer = useResource<unknown>(approvalApiPath(suspensionId));
  if (answer.failure) {
    return (
      <Notice title={SOMETHING_DID_NOT_WORK} traceId={answer.failure.traceId}>
        <p>{answer.failure.message}</p>
      </Notice>
    );
  }
  if (answer.busy) {
    return <Busy />;
  }
  const read = readApprovalCard(answer.data);
  return read === null ? null : <ApprovalCard card={read} linked={false} />;
}

export function Approvals() {
  const { suspensionId } = useParams();
  return (
    <article className="page">
      <h1>{APPROVALS_HEADING}</h1>
      <p className="lede">{APPROVALS_LEDE}</p>
      <p className="note">{DECIDING_IS_NOT_HERE}</p>
      {suspensionId === undefined ? (
        <QueueView />
      ) : (
        <>
          <p>
            <Link className="approval-card__link" to={APPROVALS_ADDRESS}>
              {APPROVALS_HEADING}
            </Link>
          </p>
          <OneView suspensionId={suspensionId} />
        </>
      )}
    </article>
  );
}
