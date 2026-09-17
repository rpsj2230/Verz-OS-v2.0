/**
 * Elevation requests: who asked for more, what they were given, and when it lapses.
 *
 * `docs/screens.html` draws no elevation screen of its own; SCREEN 10 is where the design talks
 * about reach being a set of grants that "can be audited and reduced", and this page takes that
 * screen's layout: the crumb, cards of labelled facts and a table, and the hint under them. It sits
 * in Govern beside People and grants.
 *
 * **Anybody may ask, for themselves, and somebody else decides.** The ask form takes the capability,
 * the scope as the Scopes screen spells it, a reason from the product's closed list, what it is for,
 * and the hours; blank fields are said beside the form before anything is sent, and the rest is the
 * API's to judge. Asking, approving and denying each open a confirmation naming the capability, the
 * scope, the hours and the person, with the API's own sentence about what an elevation is. An
 * approval is a grant that lapses on its own, so nothing here ends one.
 *
 * **Nothing lists what an elevation could confer.** That is the catalogue handed to somebody holding
 * nothing, which `brain.console.elevation.A_LANDING_THAT_LISTS_WHAT_YOU_COULD_ELEVATE_TO_IS_THE_
 * CATALOGUE` refuses, and the response has no field one could arrive in. A requester types the
 * capability they were told they need.
 *
 * **Nothing here decides who may see or decide a request.** The rows are
 * `brain.console.elevation.requests_shown`'s answer, a decision control is drawn only where the API
 * said the row is decidable, and the route asks `may_approve` or `may_decide` again whatever this
 * page drew. A write is followed by a fresh request, keyed on a counter.
 *
 * Task ids: M27.7.8, M27.8.6
 */

import { useCallback, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { ListControls, NOTHING_MATCHES, ShowMore } from "../components/ListControls";
import { narrows } from "../components/listing";
import { useListing } from "../components/useListing";
import { ConfirmAction } from "../components/ConfirmAction";
import { FailureNotice } from "../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../ui/FieldProblems";
import {
  ASK_BLANKS,
  ELEVATION_DECISIONS,
  ELEVATION_REQUESTS_API_PATH,
  STATE_WORDS,
  askBlanks,
  askQuestion,
  ELEVATION_API_PATH,
  ELEVATION_FILTERS,
  ELEVATION_SORTS,
  elevationDecisionApiPath,
  elevationQuestion,
  personAddress,
  readElevation,
  reasonWords,
  when,
  type ElevationAsk,
  type ElevationDecisionWord,
  type ElevationRequestRow,
} from "./governPeopleQuery";

export const ELEVATION_HEADING = "Elevation requests";
export const ELEVATION_CRUMB = "Govern › Elevation requests";
export const ELEVATION_LEDE =
  "Who asked for more access than they hold, what they were given, and when it lapses. Ask for " +
  "what you need here, and decide what others asked for if you may.";

export const READING_ELEVATION = "Reading the elevation requests you may see.";
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";
/** A body that is not the page. The fourth state, and a different sentence from the other three. */
export const NOT_A_LANDING = "The answer about elevations could not be read.";
export const YOU_HOLD_THE_AUTHORITY = "You hold that authority.";
/** No reason is accepted, so the row says that rather than standing empty. */
export const NO_REASON_IS_ACCEPTED = "No reason is accepted, so no elevation can be asked for.";
export const NO_REQUESTS = "There are no elevation requests for you to see.";
export const MORE_REQUESTS = "This list came back full, so there are more requests than it shows.";
export const NONE_MATCH = NOTHING_MATCHES;
export const FILTERS_LABEL = "Narrow the requests";

export const ASK_LABEL = "Ask for this";
export const CANCEL_LABEL = "Not now";
export const DECISION_LABELS: Readonly<Record<ElevationDecisionWord, string>> = Object.freeze({
  approved: "Approve",
  denied: "Deny",
});
export const REQUESTS_LABEL = "Elevation requests";

/** What a success says, and the instant the database recorded. */
export function askedSentence(ask: ElevationAsk, at: string): string {
  return `Your request for ${ask.capability} was recorded at ${when(at)}.`;
}

export function decidedSentence(row: ElevationRequestRow, decision: ElevationDecisionWord, at: string): string {
  const who = row.display_name ?? row.principal_id;
  return `${row.capability} for ${who} was ${decision} at ${when(at)}.`;
}

function stamp(payload: unknown, key: "requested_at" | "decided_at"): string {
  if (typeof payload !== "object" || payload === null) {
    return "";
  }
  const at = (payload as Record<string, unknown>)[key];
  return typeof at === "string" ? at : "";
}

type Pending =
  | { readonly kind: "ask"; readonly ask: ElevationAsk }
  | { readonly kind: "decide"; readonly row: ElevationRequestRow; readonly decision: ElevationDecisionWord };

const EMPTY_ASK: ElevationAsk = Object.freeze({
  capability: "",
  scope_slug: "",
  reason: "",
  explanation: "",
  hours: 1,
});

/** The names a request's inputs are sent under, which are `ElevationAsked`'s five keys. */
const ASK_FIELDS: readonly string[] = ["capability", "scope_slug", "reason", "explanation", "hours"];
const ASK_FORM = "elevation-ask";

function Requests({
  version,
  onChanged,
}: {
  readonly version: number;
  readonly onChanged: (sentence: string) => void;
}) {
  const listing = useListing<ElevationRequestRow>(ELEVATION_API_PATH, {
    listKey: "requests",
    choices: ELEVATION_FILTERS,
    version,
  });
  const [ask, setAsk] = useState<ElevationAsk>(EMPTY_ASK);
  const [blanks, setBlanks] = useState<readonly (keyof typeof ASK_BLANKS)[]>([]);
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  // The refusal, and whether it was of a request, whose problems are drawn beside the form, or of a
  // decision, which has no input and whose problems are all listed under the notice.
  const [failure, setFailure] = useState<{ readonly failure: ApiFailure; readonly asked: boolean } | null>(null);
  const problems = failure !== null && failure.asked ? failure.failure.problems : [];

  const send = useCallback(
    (chosen: Pending) => {
      setBusy(true);
      void (async () => {
        const result =
          chosen.kind === "ask"
            ? await request<unknown>(ELEVATION_REQUESTS_API_PATH, { method: "POST", body: chosen.ask })
            : await request<unknown>(elevationDecisionApiPath(chosen.row.request_id), {
                method: "POST",
                body: { decision: chosen.decision },
              });
        setBusy(false);
        setPending(null);
        if (!result.ok) {
          setFailure({ failure: result.failure, asked: chosen.kind === "ask" });
          return;
        }
        setFailure(null);
        onChanged(
          chosen.kind === "ask"
            ? askedSentence(chosen.ask, stamp(result.data, "requested_at"))
            : decidedSentence(chosen.row, chosen.decision, stamp(result.data, "decided_at")),
        );
      })();
    },
    [onChanged],
  );

  // The landing is the first page's body, and it stays drawn while a search is answered, so the
  // form somebody is filling in is not taken away by a keystroke in the search box.
  if (listing.body === null) {
    if (listing.failure) {
      return <FailureNotice failure={listing.failure} />;
    }
    return (
      <p className="note" role="status">
        {READING_ELEVATION}
      </p>
    );
  }
  const page = readElevation(listing.body);
  if (page === null) {
    return <p className="note">{NOT_A_LANDING}</p>;
  }
  const rows = page.requests ?? [];

  const onAsk = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const missing = askBlanks(ask);
    setBlanks(missing);
    if (missing.length > 0) {
      return;
    }
    setFailure(null);
    setPending({ kind: "ask", ask: { ...ask, capability: ask.capability.trim(), scope_slug: ask.scope_slug.trim() } });
  };
  const field = (name: "capability" | "scope_slug" | "explanation") => (value: string) => {
    setAsk({ ...ask, [name]: value });
  };

  return (
    <>
      <section className="card" aria-labelledby="elevation-standing">
        <h2 id="elevation-standing">Your standing</h2>
        <p>{page.prompt}</p>
      </section>

      {failure === null ? null : (
        <FailureNotice failure={failure.failure} {...(failure.asked ? { fields: ASK_FIELDS } : {})} />
      )}

      {pending === null ? null : (
        <ConfirmAction
          question={
            pending.kind === "ask" ? askQuestion(pending.ask) : elevationQuestion(pending.row, pending.decision)
          }
          consequence={pending.kind === "decide" && pending.decision === "denied" ? page.recorded : page.what}
          confirmLabel={pending.kind === "ask" ? ASK_LABEL : DECISION_LABELS[pending.decision]}
          cancelLabel={CANCEL_LABEL}
          busy={busy}
          onConfirm={() => {
            send(pending);
          }}
          onCancel={() => {
            setPending(null);
          }}
        />
      )}

      <section className="card" aria-labelledby="elevation-ask">
        <h2 id="elevation-ask">Ask for more</h2>
        {page.reasons.length === 0 ? (
          <p className="note">{NO_REASON_IS_ACCEPTED}</p>
        ) : (
          <form className="form" aria-label="Ask for an elevation" onSubmit={onAsk} noValidate>
            <label className="control-label">
              Capability{" "}
              <input
                className="form-control"
                name="capability"
                value={ask.capability}
                {...problemAttributes(problems, ASK_FORM, "capability")}
                onChange={(event) => {
                  field("capability")(event.target.value);
                }}
              />
            </label>
            {blanks.includes("capability") ? <p className="note">{ASK_BLANKS.capability}</p> : null}
            <FieldProblems problems={problems} form={ASK_FORM} names="capability" />
            <label className="control-label">
              Scope{" "}
              <input
                className="form-control"
                name="scope_slug"
                value={ask.scope_slug}
                {...problemAttributes(problems, ASK_FORM, "scope_slug")}
                onChange={(event) => {
                  field("scope_slug")(event.target.value);
                }}
              />
            </label>
            {blanks.includes("scope_slug") ? <p className="note">{ASK_BLANKS.scope_slug}</p> : null}
            <FieldProblems problems={problems} form={ASK_FORM} names="scope_slug" />
            <label className="control-label">
              Why{" "}
              <select
                className="form-control"
                name="reason"
                value={ask.reason}
                {...problemAttributes(problems, ASK_FORM, "reason")}
                onChange={(event) => {
                  setAsk({ ...ask, reason: event.target.value });
                }}
              >
                <option value="">Choose a reason</option>
                {page.reasons.map((one) => (
                  <option key={one} value={one}>
                    {reasonWords(one)}
                  </option>
                ))}
              </select>
            </label>
            {blanks.includes("reason") ? <p className="note">{ASK_BLANKS.reason}</p> : null}
            <FieldProblems problems={problems} form={ASK_FORM} names="reason" />
            <label className="control-label">
              What it is for{" "}
              <textarea
                className="form-control"
                name="explanation"
                value={ask.explanation}
                {...problemAttributes(problems, ASK_FORM, "explanation")}
                onChange={(event) => {
                  field("explanation")(event.target.value);
                }}
              />
            </label>
            {blanks.includes("explanation") ? <p className="note">{ASK_BLANKS.explanation}</p> : null}
            <FieldProblems problems={problems} form={ASK_FORM} names="explanation" />
            <label className="control-label">
              Hours{" "}
              <select
                className="form-control"
                name="hours"
                value={String(ask.hours)}
                {...problemAttributes(problems, ASK_FORM, "hours")}
                onChange={(event) => {
                  setAsk({ ...ask, hours: Number(event.target.value) });
                }}
              >
                {Array.from({ length: Math.max(page.longest_hours, 1) }, (_, index) => index + 1).map((hours) => (
                  <option key={hours} value={String(hours)}>
                    {String(hours)}
                  </option>
                ))}
              </select>
            </label>
            <FieldProblems problems={problems} form={ASK_FORM} names="hours" />
            <div className="form-actions">
              <button type="submit" className="button" disabled={busy}>
                {ASK_LABEL}
              </button>
            </div>
          </form>
        )}
      </section>

      <section className="card" aria-labelledby="elevation-requests">
        <h2 id="elevation-requests">Requests</h2>
        <ListControls label={FILTERS_LABEL} listing={listing} choices={ELEVATION_FILTERS} sorts={ELEVATION_SORTS} />
        {listing.failure ? (
          <FailureNotice failure={listing.failure} />
        ) : listing.busy ? (
          <p className="note" role="status">
            {READING_ELEVATION}
          </p>
        ) : rows.length === 0 ? (
          <p className="note">{narrows(listing.question) ? NONE_MATCH : NO_REQUESTS}</p>
        ) : (
          <>
            <div className="grid__scroll">
              <table className="grid__table" aria-label={REQUESTS_LABEL}>
                <thead>
                  <tr>
                    <th scope="col">Person</th>
                    <th scope="col">Asked for</th>
                    <th scope="col">Why</th>
                    <th scope="col">Asked</th>
                    <th scope="col">Where it stands</th>
                    <th scope="col">Decision</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.request_id}>
                      <td>
                        <Link to={personAddress(row.principal_id)}>{row.display_name ?? row.principal_id}</Link>{" "}
                        <code>{row.principal_id}</code> {row.department === null ? null : <code>{row.department}</code>}
                      </td>
                      <td>
                        <code>{row.capability}</code> over <code>{row.scope_slug}</code> for {`${String(row.hours)} hours`}
                      </td>
                      <td>
                        {reasonWords(row.reason)}
                        <p className="note">{row.explanation}</p>
                      </td>
                      <td>{when(row.requested_at)}</td>
                      <td>
                        {STATE_WORDS[row.state]}
                        {row.lapses_at === null ? null : <p className="note">{`Lapses ${when(row.lapses_at)}`}</p>}
                        {row.decided_by === null ? null : (
                          <p className="note">
                            <code>{row.decided_by}</code> {when(row.decided_at)}
                          </p>
                        )}
                      </td>
                      <td>
                        {row.decidable
                          ? ELEVATION_DECISIONS.map((decision) => (
                              <button
                                key={decision}
                                type="button"
                                className="button"
                                disabled={busy}
                                aria-label={`${DECISION_LABELS[decision]}: ${elevationQuestion(row, decision)}`}
                                onClick={() => {
                                  setFailure(null);
                                  setPending({ kind: "decide", row, decision });
                                }}
                              >
                                {DECISION_LABELS[decision]}
                              </button>
                            ))
                          : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ShowMore listing={listing} />
          </>
        )}
        {page.truncated === true ? <p className="note">{MORE_REQUESTS}</p> : null}
      </section>

      <section className="card" aria-labelledby="elevation-rules">
        <h2 id="elevation-rules">What an elevation is</h2>
        <p>{page.what}</p>
        <dl className="fields" aria-label="The rules an elevation is held to">
          <div className="fields__row">
            <dt>Reasons it may be asked for</dt>
            <dd>{page.reasons.length === 0 ? NO_REASON_IS_ACCEPTED : page.reasons.map(reasonWords).join(", ")}</dd>
          </div>
          <div className="fields__row">
            <dt>Longest it may run</dt>
            <dd>{`${String(page.longest_hours)} hours`}</dd>
          </div>
        </dl>
        {[page.recorded, page.notified].map((sentence) =>
          sentence === undefined || sentence === "" ? null : (
            <p className="note" key={sentence}>
              {sentence}
            </p>
          ),
        )}
        <p className="note">
          {page.authorising}
          {page.may_authorise ? ` ${YOU_HOLD_THE_AUTHORITY}` : ""}
        </p>
      </section>
    </>
  );
}

export function Elevation() {
  // A counter, so two changes in a row ask twice. Never rendered.
  const [version, setVersion] = useState(0);
  const [changed, setChanged] = useState<string | null>(null);
  const onChanged = useCallback((sentence: string) => {
    setChanged(sentence);
    setVersion((current) => current + 1);
  }, []);

  return (
    <article className="page">
      <p className="note">{ELEVATION_CRUMB}</p>
      <h1>{ELEVATION_HEADING}</h1>
      <p className="lede">{ELEVATION_LEDE}</p>
      {changed === null ? null : (
        <p className="note" role="status">
          {changed}
        </p>
      )}
      <Requests version={version} onChanged={onChanged} />
    </article>
  );
}
