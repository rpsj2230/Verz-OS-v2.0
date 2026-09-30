/**
 * One approval as a card a phone can read and decide: what will happen, whose reach it runs under,
 * when it was raised and when it lapses, and Approve and Reject below all of that.
 *
 * **Cards, not a table.** An approval is an artefact of several lines and four facts, and a row of
 * columns holding one is either wider than a phone or truncates the artefact, which is the part a
 * person is approving. `styles/approvals.css` states the phone as the base case and
 * `tests/approvals-phone.test.tsx` holds its rules, so the card's markup and classes are kept as
 * they were when the page around it moved to the kit.
 *
 * **Runs as, by name.** The queue and the card carry the names of the people cards run as
 * (`brain.people_names`); the principal id is on the approval's own page, in Advanced.
 *
 * **A decision is claimed only when the API confirms it.** See
 * `A_DECISION_IS_CLAIMED_ONLY_WHEN_THE_API_CONFIRMS_IT`. A rejection needs one of the route's reasons
 * and its button stays disabled until one is chosen.
 *
 * **Take over, on an agent's prepared action only, and confirmed.** The card says whether it is
 * offered (`mayTakeOver`), which is the API's answer and never this console's. Taking over means the
 * agent does not do it and the approver does it by hand, and it counts against the agent's rung on
 * that action, so it asks for a reason and then asks once more, in words, before it is sent. See
 * `TAKING_OVER_IS_CONFIRMED_BECAUSE_IT_LOWERS_THE_AGENT`.
 *
 * Task ids: M35.3.1.2, M35.3.1.1, M40.6.1.5, M27.16.1, M33.6.1.3
 */

import { useCallback, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { ConfirmAction } from "../../components/ConfirmAction";
import { FailureNotice } from "../../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../../ui/FieldProblems";
import {
  approvalDecisionApiPath,
  decisionBody,
  readDecision,
  REJECTION_REASONS,
  TAKEOVER_REASONS,
  type ApprovalCardView,
  type Decision,
  type Verdict,
} from "../approvalsQuery";
import { nameOf } from "../review/parts";

/** Written down because a button that turns green on click is the easy version of this page. */
export const A_DECISION_IS_CLAIMED_ONLY_WHEN_THE_API_CONFIRMS_IT =
  "A decision is stored by the API, once, and refused alike for a card already decided and one " +
  "that never existed. So the page says approved or rejected only when the answer names this " +
  "approval and that verdict, and a refusal leaves the card and its buttons where they were " +
  "with the API's sentence beside them.";

export const RUNS_AS_LABEL = "Runs as";
export const RAISED_LABEL = "Raised";
export const LAPSES_LABEL = "Lapses";
export const OPEN_ON_ITS_OWN = "Open on its own";
export const APPROVE_LABEL = "Approve";
export const REJECT_LABEL = "Reject";
export const REASON_LABEL = "Reason for rejecting";
export const NO_REASON_CHOSEN = "Choose a reason";
export const APPROVED_SENTENCE = "Approved.";
export const REJECTED_SENTENCE = "Rejected.";
export const TAKE_OVER_LABEL = "Take over";
export const TAKE_OVER_REASON_LABEL = "Reason for taking it over";
export const TAKEN_OVER_SENTENCE = "Taken over. The agent will not do it; it is yours to do.";
export const TAKE_OVER_QUESTION = "Take this over and do it yourself?";
export const TAKE_OVER_CONSEQUENCE =
  "The agent will not do it, and nothing it prepared is sent or changed. It is recorded as taken " +
  "over, and three takeovers of the same kind of action inside a week hold this agent a step lower " +
  "on it, so a person sees more of its work first.";
export const KEEP_IT_LABEL = "Keep it waiting";

/** Written down because a take-over button that sends on one press is the easy version. */
export const TAKING_OVER_IS_CONFIRMED_BECAUSE_IT_LOWERS_THE_AGENT =
  "Taking over is recorded against the agent and three in a week lower its rung on that action, " +
  "which is more than one approval's worth of consequence. So it is offered only where the API says " +
  "it may be, asks why, and says what it does before anything is sent.";

/** The console address of the queue. */
export const APPROVALS_ADDRESS = "/approvals";

/** The console address of one approval. */
export function approvalAddress(suspensionId: string): string {
  return `${APPROVALS_ADDRESS}/${encodeURIComponent(suspensionId)}`;
}

export type { Verdict } from "../approvalsQuery";

export function said(verdict: Verdict): string {
  switch (verdict) {
    case "approved":
      return APPROVED_SENTENCE;
    case "rejected":
      return REJECTED_SENTENCE;
    case "taken_over":
      return TAKEN_OVER_SENTENCE;
  }
}

function When({ at }: { readonly at: string }) {
  return <time dateTime={at}>{new Date(at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}</time>;
}

export function ApprovalCard({
  card,
  people,
  linked,
  decision,
}: {
  readonly card: ApprovalCardView;
  readonly people: Readonly<Record<string, string>>;
  readonly linked: boolean;
  readonly decision?: ReactNode;
}) {
  return (
    <article className="approval-card">
      <pre className="approval-card__artefact">{card.artefact}</pre>
      <dl className="approval-card__facts">
        <dt className="approval-card__label">{RUNS_AS_LABEL}</dt>
        <dd className="approval-card__value">{nameOf(people, card.runsAs)}</dd>
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
 * Approve and reject for one card. A component of its own because it holds one decision in flight,
 * which the card does not.
 */
export function DecisionControls({
  suspensionId,
  mayTakeOver = false,
  onDecided,
}: {
  readonly suspensionId: string;
  readonly mayTakeOver?: boolean;
  readonly onDecided: (verdict: Verdict) => void;
}) {
  const [reason, setReason] = useState("");
  const [takeoverReason, setTakeoverReason] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const problems = failure?.problems ?? [];
  // One card per approval on the queue, so the list beside the reason is named for this one.
  const form = `approval-${suspensionId}`;

  const send = useCallback(
    (decision: Decision) => {
      const body = decisionBody(decision);
      if (body === null) {
        return;
      }
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(approvalDecisionApiPath(suspensionId), { method: "POST", body });
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
      <button type="button" className="button approval-card__action" disabled={busy} onClick={() => send({ verdict: "approved" })}>
        {APPROVE_LABEL}
      </button>
      <label className="approval-card__reason">
        <span>{REASON_LABEL}</span>
        <select
          className="form-control approval-card__choice"
          name="reason_code"
          value={reason}
          disabled={busy}
          {...problemAttributes(problems, form, "reason_code")}
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
      <FieldProblems problems={problems} form={form} names="reason_code" />
      <button
        type="button"
        className="button approval-card__action"
        disabled={busy || reason === ""}
        onClick={() => send({ verdict: "rejected", reasonCode: reason })}
      >
        {REJECT_LABEL}
      </button>
      {mayTakeOver ? (
        confirming ? (
          <ConfirmAction
            question={TAKE_OVER_QUESTION}
            consequence={TAKE_OVER_CONSEQUENCE}
            confirmLabel={TAKE_OVER_LABEL}
            cancelLabel={KEEP_IT_LABEL}
            busy={busy}
            onConfirm={() => send({ verdict: "taken_over", reasonCode: takeoverReason })}
            onCancel={() => setConfirming(false)}
          />
        ) : (
          <>
            <label className="approval-card__reason">
              <span>{TAKE_OVER_REASON_LABEL}</span>
              <select
                className="form-control approval-card__choice"
                name="takeover_reason"
                value={takeoverReason}
                disabled={busy}
                onChange={(event) => setTakeoverReason(event.target.value)}
              >
                <option value="">{NO_REASON_CHOSEN}</option>
                {Object.entries(TAKEOVER_REASONS).map(([code, words]) => (
                  <option key={code} value={code}>
                    {words}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="button approval-card__action"
              disabled={busy || takeoverReason === ""}
              onClick={() => setConfirming(true)}
            >
              {TAKE_OVER_LABEL}
            </button>
          </>
        )
      ) : null}
      {failure ? <FailureNotice failure={failure} fields={["reason_code"]} /> : null}
    </div>
  );
}
