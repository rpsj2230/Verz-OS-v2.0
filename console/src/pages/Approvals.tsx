/**
 * The approvals waiting on this reader, as cards a phone can read and decide, and one approval on
 * its own.
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
 * **Every card can be approved or rejected where it is drawn, below what will happen.** The
 * artefact and its facts come first, so a thumb reaches the buttons only after the eye has passed
 * the action. A rejection needs one of the route's reasons and its button stays disabled until one
 * is chosen. The page claims a decision only when the API's answer confirms it: after a decision
 * in the queue the queue is asked again rather than edited in place, for the reason
 * `pages/Matrix.tsx` gives about a saved rung, and a refusal is the API's own sentence, which is
 * the same for an approval somebody else already decided and one that never existed. See
 * `A_DECISION_IS_CLAIMED_ONLY_WHEN_THE_API_CONFIRMS_IT`.
 *
 * **One component for the queue and for one card**, at `/approvals` and
 * `/approvals/:suspensionId`. The single card is where a link from a chat message lands, and its
 * refusal is the API's sentence, which is the same for an approval that is not the reader's and
 * one that does not exist.
 *
 * **A phone is the case this page is designed for, and the frame around it is held to the same
 * standard** (M40.6.1.5, M40.1.2.3). The card's rules are the phone's in `styles/approvals.css`;
 * the shell's navigation is a strip on a phone so the card is on the first screen, every control
 * in the frame is a thumb tall, a field is never small enough for a phone to zoom the page when it
 * takes focus, and a confirmed decision takes focus so its sentence is on the screen. Measured in
 * Chrome on 2026-09-16 with the console's own sheets: at 360 pixels the card began 1003 pixels
 * down before and 385 after. `tests/approvals-phone.test.tsx` holds the rules.
 *
 * Task ids: M35.3.1.2, M35.3.1.1, M40.6.1.5, M40.1.2.3, M27.8.6
 */

import "../styles/approvals.css";
import { useCallback, useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { Link, useParams } from "react-router-dom";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { ListControls, NOTHING_MATCHES, ShowMore } from "../components/ListControls";
import { narrows, type FilterChoice, type SortChoice } from "../components/listing";
import { useListing } from "../components/useListing";
import type { components } from "../api/schema";
import {
  approvalApiPath,
  approvalDecisionApiPath,
  APPROVALS_API_PATH,
  decisionBody,
  readApprovalCard,
  readApprovalQueue,
  readDecision,
  REJECTION_REASONS,
  type ApprovalCardView,
  type Decision,
} from "./approvalsQuery";
import { FailureNotice } from "../ui/FailureNotice";

/** Written down because a button that turns green on click is the easy version of this page. */
export const A_DECISION_IS_CLAIMED_ONLY_WHEN_THE_API_CONFIRMS_IT =
  "A decision is stored by the API, once, and refused alike for a card already decided and one " +
  "that never existed. So the page says approved or rejected only when the answer names this " +
  "approval and that verdict, and a refusal leaves the card and its buttons where they were " +
  "with the API's sentence beside them.";

/** Why the page moves focus to the sentence confirming a decision. */
export const A_CONFIRMATION_IS_DRAWN_WHERE_THE_THUMB_IS =
  "On a phone the decided card is scrolled to, and after a confirmed decision it is gone: the " +
  "queue is asked again and the card on its own loses its buttons, so the control somebody " +
  "pressed no longer exists and the sentence saying what happened is drawn at the top of a " +
  "page they are not looking at. Focus goes to that sentence, which scrolls it onto the " +
  "screen and has a screen reader read it, and only after the API has confirmed the decision.";

/** The page's heading. */
export const APPROVALS_HEADING = "Approvals";

/** Under the heading. Says what the list is, and nothing about what it is not. */
export const APPROVALS_LEDE = "Actions waiting for you to decide, soonest to lapse first.";

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

/** The two controls, and the field a rejection needs. */
export const APPROVE_LABEL = "Approve";
export const REJECT_LABEL = "Reject";
export const REASON_LABEL = "Reason for rejecting";
export const NO_REASON_CHOSEN = "Choose a reason";

/** What is said once the API has confirmed a decision. */
export const APPROVED_SENTENCE = "Approved.";
export const REJECTED_SENTENCE = "Rejected.";

/** The console address of the queue. */
export const APPROVALS_ADDRESS = "/approvals";

/** The console address of one approval. */
export function approvalAddress(suspensionId: string): string {
  return `${APPROVALS_ADDRESS}/${encodeURIComponent(suspensionId)}`;
}

type Verdict = "approved" | "rejected";

function said(verdict: Verdict): string {
  return verdict === "approved" ? APPROVED_SENTENCE : REJECTED_SENTENCE;
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
  decision,
}: {
  readonly card: ApprovalCardView;
  readonly linked: boolean;
  readonly decision?: ReactNode;
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
      {decision}
      {linked ? (
        <Link className="approval-card__link" to={approvalAddress(card.suspensionId)}>
          {OPEN_ON_ITS_OWN}
        </Link>
      ) : null}
    </article>
  );
}

/**
 * Approve and reject for one card.
 *
 * A component of its own because it holds one decision in flight, which the card does not. The
 * reason is chosen from the route's codes, and the reject button is disabled until one is.
 */
export function DecisionControls({
  suspensionId,
  onDecided,
}: {
  readonly suspensionId: string;
  readonly onDecided: (verdict: Verdict) => void;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const send = useCallback(
    (decision: Decision) => {
      const body = decisionBody(decision);
      if (body === null) {
        return;
      }
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(approvalDecisionApiPath(suspensionId), {
          method: "POST",
          body,
        });
        setBusy(false);
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setFailure(null);
        const confirmed = readDecision(result.data, suspensionId);
        if (confirmed !== null) {
          onDecided(confirmed);
        }
      })();
    },
    [suspensionId, onDecided],
  );

  return (
    <div className="approval-card__decision">
      <button
        type="button"
        className="button approval-card__action"
        disabled={busy}
        onClick={() => send({ verdict: "approved" })}
      >
        {APPROVE_LABEL}
      </button>
      <label className="approval-card__reason">
        <span>{REASON_LABEL}</span>
        <select
          className="form-control approval-card__choice"
          value={reason}
          disabled={busy}
          onChange={(event) => setReason(event.target.value)}
        >
          <option value="">{NO_REASON_CHOSEN}</option>
          {Object.entries(REJECTION_REASONS).map(([code, words]) => (
            <option key={code} value={code}>
              {words}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        className="button approval-card__action"
        disabled={busy || reason === ""}
        onClick={() => send({ verdict: "rejected", reasonCode: reason })}
      >
        {REJECT_LABEL}
      </button>
      {failure ? (
        <FailureNotice failure={failure} />
      ) : null}
    </div>
  );
}

function Busy() {
  return (
    <p className="note" role="status">
      Loading.
    </p>
  );
}

export const FILTERS_LABEL = "Narrow the approvals";
export const NONE_MATCH = NOTHING_MATCHES;

type QueueRow = components["schemas"]["ApprovalCardView"];

/** The filters the queue route declares that this screen offers, over values on cards drawn. */
export const QUEUE_FILTERS: readonly FilterChoice<QueueRow>[] = [
  { column: "runs_as", label: "Runs as", everything: "Anybody", read: (row) => row.runs_as },
];

export const QUEUE_SORTS: readonly SortChoice[] = [
  { value: "", label: "Soonest to lapse first" },
  { value: "-raised_at", label: "Most recently raised first" },
  { value: "runs_as", label: "By who it runs as" },
];

function QueueRows({ version, onDecided }: { readonly version: number; readonly onDecided: (verdict: Verdict) => void }) {
  const listing = useListing<QueueRow>(APPROVALS_API_PATH, { choices: QUEUE_FILTERS, version });
  const controls = (
    <ListControls label={FILTERS_LABEL} listing={listing} choices={QUEUE_FILTERS} sorts={QUEUE_SORTS} />
  );
  if (listing.failure) {
    return (
      <>
        {controls}
        <FailureNotice failure={listing.failure} />
      </>
    );
  }
  if (listing.busy) {
    return (
      <>
        {controls}
        <Busy />
      </>
    );
  }
  const read = readApprovalQueue(listing.body);
  if (read === null) {
    return controls;
  }
  return (
    <>
      {controls}
      {read.cards.length === 0 ? (
        <p className="note">{narrows(listing.question) ? NONE_MATCH : NO_APPROVALS}</p>
      ) : (
        <ul className="approval-list" aria-label={APPROVAL_LIST_LABEL}>
          {read.cards.map((card) => (
            <li key={card.suspensionId}>
              <ApprovalCard
                card={card}
                linked
                decision={<DecisionControls suspensionId={card.suspensionId} onDecided={onDecided} />}
              />
            </li>
          ))}
        </ul>
      )}
      <ShowMore listing={listing} />
      {read.truncated ? <p className="note">{MORE_APPROVALS}</p> : null}
    </>
  );
}

/**
 * The queue, asked again after every confirmed decision.
 *
 * The rows are remounted by key rather than edited, so the list on the screen is always one the
 * API sent. The last confirmed verdict is said above it, because the card it was about is gone.
 */
function QueueView() {
  const [round, setRound] = useState(0);
  const [last, setLast] = useState<Verdict | null>(null);
  const decided = useCallback((verdict: Verdict) => {
    setLast(verdict);
    setRound((one) => one + 1);
  }, []);
  const sentence = useRef<HTMLParagraphElement | null>(null);
  useConfirmationInView(sentence, round);
  return (
    <>
      {last === null ? null : (
        <p className="note" ref={sentence} tabIndex={-1}>
          {said(last)}
        </p>
      )}
      <QueueRows version={round} onDecided={decided} />
    </>
  );
}

/**
 * Put focus on the sentence confirming a decision, once, when the API has confirmed one.
 *
 * See `A_CONFIRMATION_IS_DRAWN_WHERE_THE_THUMB_IS`. `round` changes only when a decision is
 * confirmed, so the first render, a refusal and a queue that is merely read again move nothing.
 */
function useConfirmationInView(
  sentence: RefObject<HTMLParagraphElement | null>,
  round: number,
): void {
  useEffect(() => {
    if (round > 0) {
      sentence.current?.focus();
    }
  }, [sentence, round]);
}

function OneView({ suspensionId }: { readonly suspensionId: string }) {
  const answer = useResource<unknown>(approvalApiPath(suspensionId));
  const [decided, setDecided] = useState<Verdict | null>(null);
  const sentence = useRef<HTMLParagraphElement | null>(null);
  useConfirmationInView(sentence, decided === null ? 0 : 1);
  if (answer.failure) {
    return (
      <FailureNotice failure={answer.failure} />
    );
  }
  if (answer.busy) {
    return <Busy />;
  }
  const read = readApprovalCard(answer.data);
  if (read === null) {
    return null;
  }
  return (
    <>
      {decided === null ? null : (
        <p className="note" ref={sentence} tabIndex={-1}>
          {said(decided)}
        </p>
      )}
      <ApprovalCard
        card={read}
        linked={false}
        decision={
          decided === null ? (
            <DecisionControls suspensionId={read.suspensionId} onDecided={setDecided} />
          ) : null
        }
      />
    </>
  );
}

export function Approvals() {
  const { suspensionId } = useParams();
  return (
    <article className="page">
      <h1>{APPROVALS_HEADING}</h1>
      <p className="lede">{APPROVALS_LEDE}</p>
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
