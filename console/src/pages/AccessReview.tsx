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
 * **A write is followed by a fresh request**, keyed on a counter, for `People.tsx`' reason: the list
 * shows what the database holds, not what this page sent.
 *
 * Task ids: M27.7.9
 */

import { useCallback, useState, type ChangeEvent } from "react";
import { Link } from "react-router-dom";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { ConfirmAction } from "../components/ConfirmAction";
import { Notice } from "../ui/Notice";
import {
  DECISIONS,
  NO_REVIEW_FILTERS,
  RECENT_DAYS,
  REVIEW_DECISION_API_PATH,
  decisionBody,
  decisionQuestion,
  holdingName,
  narrowedReview,
  personAddress,
  readReview,
  reviewApiPath,
  reviewDepartments,
  reviewPeople,
  when,
  type ReviewDecisionWord,
  type ReviewFilters,
  type ReviewRow,
} from "./governPeopleQuery";
import { SOMETHING_DID_NOT_WORK } from "./Overview";
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
export const NONE_MATCH = "No grant on this page matches these filters.";
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
export const ALL_DEPARTMENTS = "All departments";
export const EVERYONE = "Everyone";
export const DECIDED_LABELS: Readonly<Record<ReviewFilters["decided"], string>> = Object.freeze({
  "": "Every grant",
  never: "Never reviewed",
  stale: `Not reviewed in ${String(RECENT_DAYS)} days`,
});

/** What a success says: what, whose, and the instant the database recorded. */
export function decidedSentence(row: ReviewRow, decision: ReviewDecisionWord, decidedAt: string): string {
  const who = row.display_name ?? row.principal_id;
  const verb = decision === "keep" ? "kept" : "removed";
  return `${holdingName(row)} for ${who} was ${verb} at ${when(decidedAt)}.`;
}

function Failure({ failure }: { readonly failure: ApiFailure }) {
  return (
    <Notice
      title={failure.status === 0 ? THE_BRAIN_COULD_NOT_BE_REACHED : SOMETHING_DID_NOT_WORK}
      traceId={failure.traceId}
    >
      <p>{failure.message}</p>
    </Notice>
  );
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

function ReviewList({ onDecided }: { readonly onDecided: (sentence: string) => void }) {
  const answer = useResource<unknown>(reviewApiPath());
  const [filters, setFilters] = useState<ReviewFilters>(NO_REVIEW_FILTERS);
  const [pending, setPending] = useState<Pending | null>(null);
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
        onDecided(decidedSentence(chosen.row, chosen.decision, readDecidedAt(result.data)));
      })();
    },
    [onDecided],
  );

  if (answer.failure) {
    return <Failure failure={answer.failure} />;
  }
  if (answer.busy) {
    return (
      <p className="note" role="status">
        {READING_REVIEW}
      </p>
    );
  }

  const review = readReview(answer.data);
  const shown = narrowedReview(review.rows, filters, new Date());
  const set = (name: "department" | "person") => (event: ChangeEvent<HTMLSelectElement>) => {
    setFilters({ ...filters, [name]: event.target.value });
  };

  return (
    <>
      {review.rows.length === 0 ? null : (
        <form className="form" aria-label={FILTERS_LABEL} onSubmit={(event) => event.preventDefault()}>
          <label className="control-label">
            Department{" "}
            <select className="form-control" value={filters.department} onChange={set("department")}>
              <option value="">{ALL_DEPARTMENTS}</option>
              {reviewDepartments(review.rows).map((one) => (
                <option key={one} value={one}>
                  {one}
                </option>
              ))}
            </select>
          </label>
          <label className="control-label">
            Person{" "}
            <select className="form-control" value={filters.person} onChange={set("person")}>
              <option value="">{EVERYONE}</option>
              {reviewPeople(review.rows).map((one) => (
                <option key={one.id} value={one.id}>
                  {one.name}
                </option>
              ))}
            </select>
          </label>
          <label className="control-label">
            Reviewed{" "}
            <select
              className="form-control"
              value={filters.decided}
              onChange={(event) => {
                setFilters({ ...filters, decided: event.target.value as ReviewFilters["decided"] });
              }}
            >
              {(Object.keys(DECIDED_LABELS) as ReviewFilters["decided"][]).map((one) => (
                <option key={one} value={one}>
                  {DECIDED_LABELS[one]}
                </option>
              ))}
            </select>
          </label>
        </form>
      )}

      {failure === null ? null : <Failure failure={failure} />}

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

      <section className="card">
        <h2>Grants to review</h2>
        {review.rows.length === 0 ? (
          <p className="note">{NOTHING_TO_REVIEW}</p>
        ) : shown.length === 0 ? (
          <p className="note">{NONE_MATCH}</p>
        ) : (
          <div className="grid__scroll">
            <table className="grid__table" aria-label={REVIEW_LABEL}>
              <thead>
                <tr>
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
                {shown.map((row) => (
                  <tr key={row.row_id}>
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
        )}
        {review.truncated ? <p className="note">{MORE_GRANTS}</p> : null}
        {review.shows === "" ? null : <p className="note">{review.shows}</p>}
      </section>
    </>
  );
}

export function AccessReview() {
  // A counter rather than a boolean, so two decisions in a row remount twice. Never rendered.
  const [generation, setGeneration] = useState(0);
  const [decided, setDecided] = useState<string | null>(null);
  const onDecided = useCallback((sentence: string) => {
    setDecided(sentence);
    setGeneration((current) => current + 1);
  }, []);

  return (
    <article className="page">
      <p className="note">{REVIEW_CRUMB}</p>
      <h1>{REVIEW_HEADING}</h1>
      <p className="lede">{REVIEW_LEDE}</p>
      {decided === null ? null : (
        <p className="note" role="status">
          {decided}
        </p>
      )}
      <ReviewList key={generation} onDecided={onDecided} />
    </article>
  );
}
