/**
 * Access requests: ask for a field or a department, and read the requests sent to you.
 *
 * `accessRequestsQuery.ts` holds the arguments and the sentences, and `brain.access_request_routes`
 * the decisions. **What the asker is told after sending is the API's one sentence**, drawn as it
 * came back, whether a request was stored or not; the page adds nothing that could tell the two
 * apart. **The list is the reader's own**: the API returns only what was addressed to them.
 *
 * No confirmation before sending: a request ends and replaces nothing, and the owner decides it on
 * the Roles screen, which is where anything changes.
 *
 * Task ids: M4.3.4, M2.2.4
 */

import { useState, type FormEvent } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { ListControls, ShowMore } from "../components/ListControls";
import { narrows } from "../components/listing";
import { useListing } from "../components/useListing";
import { FailureNotice } from "../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../ui/FieldProblems";
import {
  ACCESS_REQUESTS_API_PATH,
  ACCESS_REQUESTS_CRUMB,
  ACCESS_REQUESTS_LABEL,
  ACCESS_REQUESTS_LEDE,
  acknowledgement,
  ASK_BLANKS,
  ASK_HEADING,
  ASK_LABEL,
  askBlanks,
  askBody,
  EMPTY_ASK,
  FILTERS_LABEL,
  FULL_LIST,
  NONE_MATCH,
  NOTHING_SENT,
  READING_REQUESTS,
  readAccessRequests,
  REQUEST_FILTERS,
  REQUEST_SORTS,
  SENT_CAPTION,
  SENT_HEADING,
  subjectWords,
  UNREADABLE_ANSWER,
  type AccessAsk,
  type AccessRequestRow,
} from "./accessRequestsQuery";
import { when } from "./sessionsQuery";

const ASK_FORM = "access-ask";
const ASK_FIELDS: readonly string[] = [
  "department",
  "entity",
  "field",
  "question",
];

function Ask() {
  const [ask, setAsk] = useState<AccessAsk>(EMPTY_ASK);
  const [blanks, setBlanks] = useState<readonly (keyof typeof ASK_BLANKS)[]>(
    [],
  );
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [told, setTold] = useState<string | null>(null);
  const problems = failure === null ? [] : failure.problems;

  const onSend = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const missing = askBlanks(ask);
    setBlanks(missing);
    if (missing.length > 0) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(ACCESS_REQUESTS_API_PATH, {
        method: "POST",
        body: askBody(ask),
      });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setAsk(EMPTY_ASK);
      setTold(acknowledgement(result.data));
    })();
  };
  const field =
    (name: "department" | "entity" | "field" | "question") =>
    (value: string) => {
      setAsk({ ...ask, [name]: value });
    };

  return (
    <section className="card" aria-labelledby="access-ask">
      <h2 id="access-ask">{ASK_HEADING}</h2>
      {failure === null ? null : (
        <FailureNotice failure={failure} fields={ASK_FIELDS} />
      )}
      {told === null ? null : (
        <p className="note" role="status">
          {told}
        </p>
      )}
      <form
        className="form"
        aria-label="Ask for access"
        onSubmit={onSend}
        noValidate
      >
        <label className="control-label">
          About{" "}
          <select
            className="form-control"
            name="kind"
            value={ask.kind}
            onChange={(event) => {
              setAsk({
                ...ask,
                kind: event.target.value === "field" ? "field" : "department",
              });
            }}
          >
            <option value="department">A department</option>
            <option value="field">A locked field</option>
          </select>
        </label>
        {ask.kind === "department" ? (
          <>
            <label className="control-label">
              Department{" "}
              <input
                className="form-control"
                name="department"
                value={ask.department}
                {...problemAttributes(problems, ASK_FORM, "department")}
                onChange={(event) => {
                  field("department")(event.target.value);
                }}
              />
            </label>
            {blanks.includes("department") ? (
              <p className="note">{ASK_BLANKS.department}</p>
            ) : null}
            <FieldProblems
              problems={problems}
              form={ASK_FORM}
              names="department"
            />
          </>
        ) : (
          <>
            <label className="control-label">
              Kind of record{" "}
              <input
                className="form-control"
                name="entity"
                value={ask.entity}
                {...problemAttributes(problems, ASK_FORM, "entity")}
                onChange={(event) => {
                  field("entity")(event.target.value);
                }}
              />
            </label>
            {blanks.includes("entity") ? (
              <p className="note">{ASK_BLANKS.entity}</p>
            ) : null}
            <FieldProblems problems={problems} form={ASK_FORM} names="entity" />
            <label className="control-label">
              Field{" "}
              <input
                className="form-control"
                name="field"
                value={ask.field}
                {...problemAttributes(problems, ASK_FORM, "field")}
                onChange={(event) => {
                  field("field")(event.target.value);
                }}
              />
            </label>
            {blanks.includes("field") ? (
              <p className="note">{ASK_BLANKS.field}</p>
            ) : null}
            <FieldProblems problems={problems} form={ASK_FORM} names="field" />
          </>
        )}
        <label className="control-label">
          What you need it for{" "}
          <textarea
            className="form-control"
            name="question"
            value={ask.question}
            {...problemAttributes(problems, ASK_FORM, "question")}
            onChange={(event) => {
              field("question")(event.target.value);
            }}
          />
        </label>
        {blanks.includes("question") ? (
          <p className="note">{ASK_BLANKS.question}</p>
        ) : null}
        <FieldProblems problems={problems} form={ASK_FORM} names="question" />
        <div className="form-actions">
          <button type="submit" className="button" disabled={busy}>
            {ASK_LABEL}
          </button>
        </div>
      </form>
    </section>
  );
}

function Sent() {
  const listing = useListing<AccessRequestRow>(ACCESS_REQUESTS_API_PATH, {
    choices: REQUEST_FILTERS,
  });

  // The landing stays drawn while a search is answered, so the controls are not taken away.
  if (listing.body === null) {
    if (listing.failure) {
      return <FailureNotice failure={listing.failure} />;
    }
    return (
      <p className="note" role="status">
        {READING_REQUESTS}
      </p>
    );
  }
  const body = readAccessRequests(listing.body);
  if (body === null) {
    return <p className="note">{UNREADABLE_ANSWER}</p>;
  }
  const rows = listing.rows;

  return (
    <section className="card" aria-labelledby="access-sent">
      <h2 id="access-sent">{SENT_HEADING}</h2>
      <ListControls
        label={FILTERS_LABEL}
        listing={listing}
        choices={REQUEST_FILTERS}
        sorts={REQUEST_SORTS}
      />
      {listing.failure ? (
        <FailureNotice failure={listing.failure} />
      ) : listing.busy ? (
        <p className="note" role="status">
          {READING_REQUESTS}
        </p>
      ) : rows.length === 0 ? (
        <p className="note">
          {narrows(listing.question) ? NONE_MATCH : NOTHING_SENT}
        </p>
      ) : (
        <>
          <div className="grid__scroll">
            <table className="grid__table">
              <caption className="grid__caption">{SENT_CAPTION}</caption>
              <thead>
                <tr>
                  <th scope="col">Asked</th>
                  <th scope="col">By</th>
                  <th scope="col">About</th>
                  <th scope="col">Would need</th>
                  <th scope="col">Their question</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((one) => (
                  <tr key={one.request_id}>
                    <td>{when(one.requested_at)}</td>
                    <td>
                      <code>{one.asker_id}</code>
                    </td>
                    <td>{subjectWords(one.subject)}</td>
                    <td>
                      <code>{one.requested_capability}</code>
                    </td>
                    <td>{one.question}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ShowMore listing={listing} />
        </>
      )}
      {body.truncated === true ? <p className="note">{FULL_LIST}</p> : null}
    </section>
  );
}

export function AccessRequests() {
  return (
    <article className="page">
      <p className="note">{ACCESS_REQUESTS_CRUMB}</p>
      <h1>{ACCESS_REQUESTS_LABEL}</h1>
      <p className="lede">{ACCESS_REQUESTS_LEDE}</p>
      <Ask />
      <Sent />
    </article>
  );
}
