/**
 * Subscribers and notifications: who is told what, and how to stop it.
 *
 * `docs/screens.html` draws no subscriber screen; its Govern screens are cards holding a table with a
 * hint under it, and SCREEN 9's "What we copy, and what we never copy" card is the register for
 * saying what leaves the building. This page takes that layout: the crumb, the filter bar, the table
 * of subscribers, a card of findings, and the sentences about what is told and how it stops.
 *
 * **Who is told is `brain.console.subscribers`' answer.** A reader who may not manage subscribers is
 * sent what an install with none is sent, so this page says "there are no subscribers" to both and
 * cannot tell them apart. The vault path a subscriber's signature is read from is not on the answer
 * and is not drawn.
 *
 * **How to stop one is a sentence and not a button, and the sentence says why.** Switching a
 * subscriber off has no audit entry it could be recorded under yet, and a control whose press nobody
 * could later attribute is the control `docs/admin-console.md` refuses. The API sends that sentence,
 * so the day the control exists the sentence and this page change together.
 *
 * Task ids: M27.7.12
 */

import { useState } from "react";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { Notice } from "../ui/Notice";
import { SUBSCRIBERS_API_PATH, narrowedSubscribers, readSubscribers, when } from "./governPeopleQuery";
import { SOMETHING_DID_NOT_WORK } from "./Overview";

export const SUBSCRIBERS_HEADING = "Subscribers and notifications";
export const SUBSCRIBERS_CRUMB = "Govern › Subscribers and notifications";
export const SUBSCRIBERS_LEDE =
  "Every outside address this install tells when something happens here, what each is told about, " +
  "and when each was last told.";

/** The four states. */
export const READING_SUBSCRIBERS = "Reading who is told what.";
export const NO_SUBSCRIBERS = "There are no subscribers to show.";
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";
export const NONE_MATCH = "No subscriber matches these filters.";
export const NEVER_DELIVERED = "Never delivered";
export const NO_FINDINGS = "Nothing is wrong with how these subscriptions are set up.";

export const SUBSCRIBERS_LABEL = "Subscribers";
export const FILTERS_LABEL = "Narrow the subscribers";
export const EVERY_KIND = "Every kind";
export const STATE_LABELS: Readonly<Record<"" | "active" | "off", string>> = Object.freeze({
  "": "On and off",
  active: "On",
  off: "Switched off",
});

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

function SubscriberList() {
  const answer = useResource<unknown>(SUBSCRIBERS_API_PATH);
  const [kind, setKind] = useState("");
  const [state, setState] = useState<"" | "active" | "off">("");

  if (answer.failure) {
    return <Failure failure={answer.failure} />;
  }
  if (answer.busy) {
    return (
      <p className="note" role="status">
        {READING_SUBSCRIBERS}
      </p>
    );
  }

  const page = readSubscribers(answer.data);
  const shown = narrowedSubscribers(page.rows, kind, state);

  return (
    <>
      {page.rows.length === 0 ? null : (
        <form className="form" aria-label={FILTERS_LABEL} onSubmit={(event) => event.preventDefault()}>
          <label className="control-label">
            Told about{" "}
            <select
              className="form-control"
              value={kind}
              onChange={(event) => {
                setKind(event.target.value);
              }}
            >
              <option value="">{EVERY_KIND}</option>
              {page.kinds.map((one) => (
                <option key={one} value={one}>
                  {one}
                </option>
              ))}
            </select>
          </label>
          <label className="control-label">
            State{" "}
            <select
              className="form-control"
              value={state}
              onChange={(event) => {
                setState(event.target.value as "" | "active" | "off");
              }}
            >
              {(Object.keys(STATE_LABELS) as ("" | "active" | "off")[]).map((one) => (
                <option key={one} value={one}>
                  {STATE_LABELS[one]}
                </option>
              ))}
            </select>
          </label>
        </form>
      )}

      <section className="card">
        <h2>Who is told</h2>
        {page.rows.length === 0 ? (
          <p className="note">{NO_SUBSCRIBERS}</p>
        ) : shown.length === 0 ? (
          <p className="note">{NONE_MATCH}</p>
        ) : (
          <div className="grid__scroll">
            <table className="grid__table" aria-label={SUBSCRIBERS_LABEL}>
              <thead>
                <tr>
                  <th scope="col">Subscriber</th>
                  <th scope="col">Address</th>
                  <th scope="col">Told about</th>
                  <th scope="col">State</th>
                  <th scope="col">Set up by</th>
                  <th scope="col">Last delivered</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((row) => (
                  <tr key={row.subscriber_id}>
                    <td>
                      <code>{row.subscriber_id}</code>
                    </td>
                    <td>
                      <code>{row.endpoint}</code>
                    </td>
                    <td>
                      {row.kinds.map((one) => (
                        <code key={one}>{one} </code>
                      ))}
                    </td>
                    <td>{row.active ? STATE_LABELS.active : STATE_LABELS.off}</td>
                    <td>
                      <code>{row.created_by}</code>
                    </td>
                    <td>{row.last_delivered_at === null ? NEVER_DELIVERED : when(row.last_delivered_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {page.told === "" ? null : <p className="note">{page.told}</p>}
        {page.scope === "" ? null : <p className="note">{page.scope}</p>}
      </section>

      {page.rows.length === 0 ? null : (
        <section className="card" aria-labelledby="subscriber-findings">
          <h2 id="subscriber-findings">Findings</h2>
          {page.findings.length === 0 ? (
            <p className="note">{NO_FINDINGS}</p>
          ) : (
            <ul className="roster">
              {page.findings.map((finding) => (
                <li key={finding}>{finding}</li>
              ))}
            </ul>
          )}
        </section>
      )}

      <section className="card" aria-labelledby="subscriber-stopping">
        <h2 id="subscriber-stopping">How to stop one</h2>
        <p>{page.stopping}</p>
      </section>
    </>
  );
}

export function Subscribers() {
  return (
    <article className="page">
      <p className="note">{SUBSCRIBERS_CRUMB}</p>
      <h1>{SUBSCRIBERS_HEADING}</h1>
      <p className="lede">{SUBSCRIBERS_LEDE}</p>
      <SubscriberList />
    </article>
  );
}
