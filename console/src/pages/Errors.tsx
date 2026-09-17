/**
 * Errors: the failures this install keeps a record of, readable without a shell on the server, and
 * a sentence saying what it keeps no record of.
 *
 * Under Operate, after Scheduled jobs. Two tables, each with its own empty sentence and its own
 * sentence for a list that came back full, a window to choose, and the four states every screen
 * keeps apart. Nothing here is a control.
 *
 * Task ids: none
 */

import { useState } from "react";
import { Link } from "react-router-dom";
import { useResource } from "../api/useResource";
import { FailureNotice } from "../ui/FailureNotice";
import {
  DEFAULT_HOURS,
  ERRORS_CRUMB,
  ERRORS_LABEL,
  ERRORS_LEDE,
  errorsApiPath,
  FAILURE_MESSAGES_STAY_ON_THE_SERVER,
  FULL_LIST,
  JOBS_CAPTION,
  JOBS_HEADING,
  LOG_HEADING,
  LOG_IS_ON_THE_LOGS_SCREEN,
  LOGS_LINK,
  NO_JOB_FAILURES,
  NO_REQUEST_FAILURES,
  PROCESS_LOG_IS_NOT_KEPT,
  READING_ERRORS,
  readErrors,
  REQUESTS_CAPTION,
  REQUESTS_HEADING,
  STATUS_WORDS,
  UNREADABLE_ANSWER,
  WINDOWS,
} from "./errorsQuery";
import { LOGS_PATH } from "./logsQuery";
import { when } from "./sessionsQuery";

function Failures({ hours }: { readonly hours: number }) {
  const answer = useResource<unknown>(errorsApiPath(hours));

  if (answer.busy) {
    return (
      <p className="note" role="status">
        {READING_ERRORS}
      </p>
    );
  }
  if (answer.failure) {
    return <FailureNotice failure={answer.failure} />;
  }
  const body = readErrors(answer.data);
  if (body === null) {
    return <p className="note">{UNREADABLE_ANSWER}</p>;
  }

  return (
    <>
      <section className="card" aria-labelledby="errors-jobs">
        <h2 id="errors-jobs">{JOBS_HEADING}</h2>
        {body.jobs.length === 0 ? (
          <p className="note">{NO_JOB_FAILURES}</p>
        ) : (
          <div className="grid__scroll">
            <table className="grid__table">
              <caption className="grid__caption">{JOBS_CAPTION}</caption>
              <thead>
                <tr>
                  <th scope="col">Job</th>
                  <th scope="col">Started</th>
                  <th scope="col">Finished</th>
                  <th scope="col">Kind of failure</th>
                </tr>
              </thead>
              <tbody>
                {body.jobs.map((one) => (
                  <tr key={`${one.control}:${one.started_at}`}>
                    <td>
                      <code>{one.control}</code>
                    </td>
                    <td>{when(one.started_at)}</td>
                    <td>{one.finished_at ? when(one.finished_at) : ""}</td>
                    <td>{one.kind ? <code>{one.kind}</code> : "Not recorded"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {body.jobs_truncated ? <p className="note">{FULL_LIST}</p> : null}
      </section>
      <section className="card" aria-labelledby="errors-requests">
        <h2 id="errors-requests">{REQUESTS_HEADING}</h2>
        {body.requests.length === 0 ? (
          <p className="note">{NO_REQUEST_FAILURES}</p>
        ) : (
          <div className="grid__scroll">
            <table className="grid__table">
              <caption className="grid__caption">{REQUESTS_CAPTION}</caption>
              <thead>
                <tr>
                  <th scope="col">Reference</th>
                  <th scope="col">Arrived</th>
                  <th scope="col">Lane</th>
                  <th scope="col">Outcome</th>
                  <th scope="col">Took</th>
                </tr>
              </thead>
              <tbody>
                {body.requests.map((one) => (
                  <tr key={`${one.reference}:${one.received_at}`}>
                    <td>
                      <code>{one.reference}</code>
                    </td>
                    <td>{when(one.received_at)}</td>
                    <td>{one.lane}</td>
                    <td>{STATUS_WORDS[one.status] ?? one.status}</td>
                    <td>{`${String(Math.round(one.duration_ms))} ms`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {body.requests_truncated ? <p className="note">{FULL_LIST}</p> : null}
      </section>
      <section className="card" aria-labelledby="errors-log">
        <h2 id="errors-log">{LOG_HEADING}</h2>
        {body.process_log_is_not_kept === false ? (
          <p>
            {LOG_IS_ON_THE_LOGS_SCREEN} <Link to={LOGS_PATH}>{LOGS_LINK}</Link>
          </p>
        ) : (
          <p>{PROCESS_LOG_IS_NOT_KEPT}</p>
        )}
        {body.failure_messages_stay_on_the_server === false ? null : (
          <p>{FAILURE_MESSAGES_STAY_ON_THE_SERVER}</p>
        )}
      </section>
    </>
  );
}

export function Errors() {
  const [hours, setHours] = useState(DEFAULT_HOURS);

  return (
    <article className="page">
      <p className="note">{ERRORS_CRUMB}</p>
      <h1>{ERRORS_LABEL}</h1>
      <p className="lede">{ERRORS_LEDE}</p>
      <form className="form" aria-label="Choose a window" onSubmit={(event) => event.preventDefault()}>
        <label className="control-label">
          Window{" "}
          <select
            className="form-control"
            value={hours}
            onChange={(event) => {
              setHours(Number(event.target.value));
            }}
          >
            {WINDOWS.map((one) => (
              <option key={one.hours} value={one.hours}>
                {one.label}
              </option>
            ))}
          </select>
        </label>
      </form>
      <Failures key={hours} hours={hours} />
    </article>
  );
}
