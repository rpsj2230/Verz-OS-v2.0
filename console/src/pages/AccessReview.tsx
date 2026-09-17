/**
 * Access review: each department lead recertifies what their people hold.
 *
 * `docs/screens.html` SCREEN 10, People and Grants, draws a person's entitlement as a table of
 * Capability, Scope, By and Lapses, and says grants are "additive capability strings bound to a
 * scope, each carrying who granted it, when, why, and when it lapses", which is "why it can be
 * audited and reduced". This screen is that table across everybody a reviewer may decide, with the
 * person and the last decision beside each row and the two controls at its end. The crumb, the
 * filter bar, the card and the hint under it are the design's.
 *
 * **Keeping and removing are both confirmed, in the API's words.** The confirmation names the person
 * and the grant, and carries `brain.govern_people_routes`' sentence for that decision. A success says
 * what was decided and when the database recorded it; a failure is the API's sentence. A kept grant
 * changes nothing about what the person may do and a removed one is gone from their next request,
 * and a pack is decided whole, which the removal sentence says.
 *
 * **Nothing here decides who may see or decide a grant.** The rows are
 * `brain.console.govern.recertifiable`'s answer, and the route asks `govern.certify` again under the
 * row's lock whatever this page drew, so every row carries both controls and a refused press is the
 * API's refusal. There is no revocation by denial anywhere: removal retires the grant row, because
 * entitlements only add.
 *
 * **Keeping or removing several is one confirmation listing each grant and what happens to it**, and
 * one request the route runs as that many single decisions, each through `certify` under its own lock.
 * The page then says, per grant, whether it was decided, so a partial refusal is stated.
 *
 * **The search, the filters, the order and "Show more" are requests** (`components/useListing.ts`).
 * A write asks for the first page again with the same question, for `People.tsx`' reason: the list
 * shows what the database holds, not what this page sent.
 *
 * Task ids: M27.7.9, M27.8.6
 */

import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { ConfirmAction } from "../components/ConfirmAction";
import { ListControls, NOTHING_MATCHES, ShowMore } from "../components/ListControls";
import { narrows } from "../components/listing";
import { useListing } from "../components/useListing";
import { FailureNotice } from "../ui/FailureNotice";
import {
  DECISIONS,
  MOST_DECIDED_AT_ONCE,
  REVIEW_API_PATH,
  REVIEW_DECISIONS_API_PATH,
  REVIEW_DECISION_API_PATH,
  REVIEW_FILTERS,
  REVIEW_SORTS,
  decisionBody,
  decisionLine,
  decisionQuestion,
  decisionsBody,
  decisionsQuestion,
  holdingKey,
  holdingName,
  personAddress,
  readReview,
  readReviewOutcomes,
  reviewOutcomeLine,
  when,
  type ReviewDecisionWord,
  type ReviewRow,
} from "./governPeopleQuery";
import { scopeLines } from "./scopeText";

export const REVIEW_HEADING = "Access review";
export const REVIEW_CRUMB = "Govern › Access review";
export const REVIEW_LEDE =
  "What the people you review hold, who granted it and when it lapses. Keep what still belongs " +
  "and remove what does not; every decision is recorded with your name.";

/** The four states. */
export const READING_REVIEW = "Reading the grants you may review.";
export const NOTHING_TO_REVIEW = "There are no grants for you to review.";
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";
export const NONE_MATCH = NOTHING_MATCHES;
export const MORE_GRANTS = "This list came back full, so there are more grants than it shows.";
export const NEVER_DECIDED = "Never reviewed";
export const DOES_NOT_LAPSE = "Does not lapse";

export const DECISION_LABELS: Readonly<Record<ReviewDecisionWord, string>> = Object.freeze({
  keep: "Keep",
  remove: "Remove",
});
export const CANCEL_LABEL = "Decide later";

export const REVIEW_LABEL = "Grants to review";
export const FILTERS_LABEL = "Narrow the grants";
export const TICK_LABEL = "Tick to decide";
export const TICKED_LABELS: Readonly<Record<ReviewDecisionWord, string>> = Object.freeze({
  keep: "Keep the ticked grants",
  remove: "Remove the ticked grants",
});
/** Said when more are ticked than one request may carry. A bound, not a count of anything. */
export const TOO_MANY_TICKED =
  "One request decides at most fifty grants. Untick some and decide the rest afterwards.";

/** What a success says: what, whose, and the instant the database recorded. */
export function decidedSentence(row: ReviewRow, decision: ReviewDecisionWord, decidedAt: string): string {
  const who = row.display_name ?? row.principal_id;
  const verb = decision === "keep" ? "kept" : "removed";
  return `${holdingName(row)} for ${who} was ${verb} at ${when(decidedAt)}.`;
}

function readDecidedAt(payload: unknown): string {
  if (typeof payload !== "object" || payload === null) {
    return "";
  }
  const at = (payload as { decided_at?: unknown }).decided_at;
  return typeof at === "string" ? at : "";
}

interface Pending {
  readonly row: ReviewRow;
  readonly decision: ReviewDecisionWord;
}

function ReviewList({
  version,
  onDecided,
}: {
  readonly version: number;
  readonly onDecided: (sentences: readonly string[]) => void;
}) {
  const listing = useListing<ReviewRow>(REVIEW_API_PATH, { choices: REVIEW_FILTERS, version });
  const [pending, setPending] = useState<Pending | null>(null);
  const [pendingTicked, setPendingTicked] = useState<ReviewDecisionWord | null>(null);
  const [ticked, setTicked] = useState<ReadonlySet<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const decide = useCallback(
    (chosen: Pending) => {
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(REVIEW_DECISION_API_PATH, {
          method: "POST",
          body: decisionBody(chosen.row, chosen.decision),
        });
        setBusy(false);
        setPending(null);
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setFailure(null);
        onDecided([decidedSentence(chosen.row, chosen.decision, readDecidedAt(result.data))]);
      })();
    },
    [onDecided],
  );

  const decideTicked = useCallback(
    (rows: readonly ReviewRow[], decision: ReviewDecisionWord) => {
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(REVIEW_DECISIONS_API_PATH, {
          method: "POST",
          body: decisionsBody(rows, decision),
        });
        setBusy(false);
        setPendingTicked(null);
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setFailure(null);
        setTicked(new Set());
        const byKey = new Map(rows.map((row) => [holdingKey(row), row]));
        onDecided(
          readReviewOutcomes(result.data).map((one) =>
            reviewOutcomeLine(byKey.get(`${one.kind}:${one.row_id}`), one, decision),
          ),
        );
      })();
    },
    [onDecided],
  );

  const names = new Map(listing.rows.map((row) => [row.principal_id, row.display_name ?? row.principal_id]));
  const choices = REVIEW_FILTERS.map((choice) =>
    choice.column === "principal_id" ? { ...choice, describe: (value: string) => names.get(value) ?? value } : choice,
  );
  const review = readReview(listing.body);
  const tickedRows = review.rows.filter((row) => ticked.has(holdingKey(row)));
  const toggle = (row: ReviewRow) => {
    const next = new Set(ticked);
    const key = holdingKey(row);
    if (next.has(key)) {
      next.delete(key);
    } else {
      next.add(key);
    }
    setTicked(next);
  };

  return (
    <>
      <ListControls label={FILTERS_LABEL} listing={listing} choices={choices} sorts={REVIEW_SORTS} />

      {failure === null ? null : <FailureNotice failure={failure} />}

      {pending === null ? null : (
        <ConfirmAction
          question={decisionQuestion(pending.row, pending.decision)}
          consequence={pending.decision === "keep" ? review.keeping : review.removing}
          confirmLabel={DECISION_LABELS[pending.decision]}
          cancelLabel={CANCEL_LABEL}
          busy={busy}
          onConfirm={() => {
            decide(pending);
          }}
          onCancel={() => {
            setPending(null);
          }}
        />
      )}

      {pendingTicked === null ? null : (
        <ConfirmAction
          question={decisionsQuestion(pendingTicked)}
          consequence={pendingTicked === "keep" ? review.keeping : review.removing}
          details={
            <ul className="confirm__items">
              {tickedRows.map((row) => (
                <li key={holdingKey(row)}>{decisionLine(row, pendingTicked)}</li>
              ))}
            </ul>
          }
          confirmLabel={TICKED_LABELS[pendingTicked]}
          cancelLabel={CANCEL_LABEL}
          busy={busy}
          onConfirm={() => {
            decideTicked(tickedRows, pendingTicked);
          }}
          onCancel={() => {
            setPendingTicked(null);
          }}
        />
      )}

      <section className="card">
        <h2>Grants to review</h2>
        {listing.failure ? (
          <FailureNotice failure={listing.failure} />
        ) : listing.busy ? (
          <p className="note" role="status">
            {READING_REVIEW}
          </p>
        ) : review.rows.length === 0 ? (
          <p className="note">{narrows(listing.question) ? NONE_MATCH : NOTHING_TO_REVIEW}</p>
        ) : (
          <>
            <div className="grid__scroll">
              <table className="grid__table" aria-label={REVIEW_LABEL}>
                <thead>
                  <tr>
                    <th scope="col">{TICK_LABEL}</th>
                    <th scope="col">Person</th>
                    <th scope="col">Capability</th>
                    <th scope="col">Scope</th>
                    <th scope="col">By</th>
                    <th scope="col">Lapses</th>
                    <th scope="col">Last reviewed</th>
                    <th scope="col">Decision</th>
                  </tr>
                </thead>
                <tbody>
                  {review.rows.map((row) => (
                    <tr key={holdingKey(row)}>
                      <td>
                        <input
                          type="checkbox"
                          aria-label={`${TICK_LABEL}: ${holdingName(row)} for ${row.display_name ?? row.principal_id}`}
                          checked={ticked.has(holdingKey(row))}
                          disabled={busy}
                          onChange={() => {
                            toggle(row);
                          }}
                        />
                      </td>
                      <td>
                        <Link to={personAddress(row.principal_id)}>{row.display_name ?? row.principal_id}</Link>{" "}
                        <code>{row.principal_id}</code> {row.department === null ? null : <code>{row.department}</code>}
                      </td>
                      <td>
                        {row.pack === null ? null : <p className="note">{`Pack ${row.pack}`}</p>}
                        {row.capabilities.map((capability) => (
                          <code key={capability}>{capability} </code>
                        ))}
                      </td>
                      <td>
                        {scopeLines(row.scope).map((line) => (
                          <code key={line}>{line} </code>
                        ))}
                      </td>
                      <td>
                        <code>{row.granted_by}</code> {when(row.granted_at)}
                        <p className="note">{row.reason}</p>
                      </td>
                      <td>{row.lapses_at === null ? DOES_NOT_LAPSE : when(row.lapses_at)}</td>
                      <td>
                        {row.last_decision === null ? (
                          NEVER_DECIDED
                        ) : (
                          <>
                            {DECISION_LABELS[row.last_decision]} <code>{row.last_decided_by}</code>{" "}
                            {when(row.last_decided_at)}
                          </>
                        )}
                      </td>
                      <td>
                        {DECISIONS.map((decision) => (
                          <button
                            key={decision}
                            type="button"
                            className="button"
                            aria-label={`${DECISION_LABELS[decision]}: ${decisionQuestion(row, decision)}`}
                            disabled={busy}
                            onClick={() => {
                              setFailure(null);
                              setPending({ row, decision });
                            }}
                          >
                            {DECISION_LABELS[decision]}
                          </button>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {tickedRows.length > MOST_DECIDED_AT_ONCE ? <p className="note">{TOO_MANY_TICKED}</p> : null}
            <div className="form-actions">
              {DECISIONS.map((decision) => (
                <button
                  key={decision}
                  type="button"
                  className="button"
                  disabled={busy || tickedRows.length === 0 || tickedRows.length > MOST_DECIDED_AT_ONCE}
                  onClick={() => {
                    setFailure(null);
                    setPendingTicked(decision);
                  }}
                >
                  {TICKED_LABELS[decision]}
                </button>
              ))}
            </div>
            <ShowMore listing={listing} />
          </>
        )}
        {review.truncated ? <p className="note">{MORE_GRANTS}</p> : null}
        {review.shows === "" ? null : <p className="note">{review.shows}</p>}
      </section>
    </>
  );
}

export function AccessReview() {
  // A counter, so two decisions in a row ask twice. Never rendered.
  const [version, setVersion] = useState(0);
  const [decided, setDecided] = useState<readonly string[]>([]);
  const onDecided = useCallback((sentences: readonly string[]) => {
    setDecided(sentences);
    setVersion((current) => current + 1);
  }, []);

  return (
    <article className="page">
      <p className="note">{REVIEW_CRUMB}</p>
      <h1>{REVIEW_HEADING}</h1>
      <p className="lede">{REVIEW_LEDE}</p>
      {decided.length === 0 ? null : (
        <div role="status">
          {decided.map((sentence, index) => (
            <p className="note" key={`${String(index)}-${sentence}`}>
              {sentence}
            </p>
          ))}
        </div>
      )}
      <ReviewList version={version} onDecided={onDecided} />
    </article>
  );
}
