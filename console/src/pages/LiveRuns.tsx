/**
 * Live runs: what the install is running now, what is owed a run, and what nothing here can show.
 *
 * `docs/screens.html` SCREEN 1 draws Live runs in the Operate menu, between the overview and
 * Models and health, and draws no body for it, so this is built in the overview's register: a
 * card per list, a table in each, and the facts the lists cannot carry said in words beneath.
 * `liveRunsQuery.ts` holds the arguments and the sentences, and `brain.operate_routes` holds the
 * facts they are about.
 *
 * **The design's columns that have no source are absent, and one card says why.** The registry
 * describes this screen as what is executing with its lane, its agent and how long it has been
 * going. A scheduled control has no agent and no person and runs in no lane, so those columns are
 * not drawn empty on every row: the card headed "What this screen cannot show" says that the work
 * which does have an agent and a person is recorded when it finishes and not while it runs.
 *
 * **Four states, four different sentences.** Loading says so; a transport failure says the Brain
 * could not be reached; a refusal or a fault is the API's own sentence with its reference; and an
 * answer this console cannot read says that rather than drawing two empty lists, because two
 * empty lists would be the install reported idle on the strength of a parse failure. An empty
 * list is a fifth thing and is said in its own card.
 *
 * **No stop control.** `liveRunsQuery.A_STOP_BUTTON_THAT_REACHES_NOTHING_IS_WORSE_THAN_NONE`.
 *
 * Imported statically rather than split, which is `Roles.tsx`' rule: it mounts neither heavy
 * library and imports no stylesheet of its own, so a chunk for it would buy a round trip and save
 * no bytes.
 *
 * Task ids: M27.2.2, M27.2.6
 */

import { useResource } from "../api/useResource";
import { Chip } from "../ui/Chip";
import { FailureNotice } from "../ui/FailureNotice";
import {
  ACTING,
  CANNOT_SHOW_HEADING,
  durationWords,
  FIRST_RUN,
  LIVE_RUNS_API_PATH,
  LIVE_RUNS_LABEL,
  LIVE_RUNS_LEDE,
  NO_RUN_CAN_BE_STOPPED,
  NOTHING_RUNNING,
  NOTHING_WAITING,
  QUEUE_IS_NOT_READABLE,
  readLiveRuns,
  REPORT_ONLY,
  REQUESTS_IN_FLIGHT_ARE_NOT_RECORDED,
  RUNNING_CAPTION,
  RUNNING_HEADING,
  runningFor,
  stalledNote,
  UNREADABLE_ANSWER,
  WAITING_CAPTION,
  WAITING_HEADING,
  type LiveRunsBody,
} from "./liveRunsQuery";

function Running({ body }: { readonly body: LiveRunsBody }) {
  return (
    <section className="card" aria-labelledby="live-runs-running">
      <h2 id="live-runs-running">{RUNNING_HEADING}</h2>
      {body.running.length === 0 ? (
        <p className="note">{NOTHING_RUNNING}</p>
      ) : (
        // `.grid__scroll` is not decoration: `.grid__table` keeps an identifier whole, and
        // without a scrolling parent the overflow is taken by the document on a phone.
        <div className="grid__scroll">
          <table className="grid__table">
            <caption className="grid__caption">{RUNNING_CAPTION}</caption>
            <thead>
              <tr>
                <th scope="col">Control</th>
                <th scope="col">What it keeps true</th>
                <th scope="col">Started</th>
                <th scope="col">Running for</th>
                <th scope="col">Mode</th>
              </tr>
            </thead>
            <tbody>
              {body.running.map((run) => (
                <tr key={run.control}>
                  <td>
                    <code>{run.control}</code>
                  </td>
                  <td>{run.keeps_true}</td>
                  <td>{run.started_at}</td>
                  <td>
                    {runningFor(run.started_at, body.as_of)}
                    {run.stalled ? (
                      <p className="note">{stalledNote(body.stalled_after_seconds)}</p>
                    ) : null}
                  </td>
                  <td>
                    <Chip label={run.report_only ? REPORT_ONLY : ACTING} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function Waiting({ body }: { readonly body: LiveRunsBody }) {
  return (
    <section className="card" aria-labelledby="live-runs-waiting">
      <h2 id="live-runs-waiting">{WAITING_HEADING}</h2>
      {body.waiting.length === 0 ? (
        <p className="note">{NOTHING_WAITING}</p>
      ) : (
        <div className="grid__scroll">
          <table className="grid__table">
            <caption className="grid__caption">{WAITING_CAPTION}</caption>
            <thead>
              <tr>
                <th scope="col">Control</th>
                <th scope="col">What it keeps true</th>
                <th scope="col">Owed since</th>
                <th scope="col">Late by</th>
              </tr>
            </thead>
            <tbody>
              {body.waiting.map((owed) => (
                <tr key={owed.control}>
                  <td>
                    <code>{owed.control}</code>
                  </td>
                  <td>{owed.keeps_true}</td>
                  <td>{owed.due_since}</td>
                  <td>{owed.first_run ? FIRST_RUN : durationWords(owed.late_by_seconds)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function CannotShow({ body }: { readonly body: LiveRunsBody }) {
  const sentences = [
    body.requests_in_flight_are_not_recorded === false ? null : REQUESTS_IN_FLIGHT_ARE_NOT_RECORDED,
    body.queue_is_not_readable === false ? null : QUEUE_IS_NOT_READABLE,
    body.no_run_can_be_stopped === false ? null : NO_RUN_CAN_BE_STOPPED,
  ].filter((one): one is string => one !== null);
  if (sentences.length === 0) {
    return null;
  }
  return (
    <section className="card" aria-labelledby="live-runs-cannot-show">
      <h2 id="live-runs-cannot-show">{CANNOT_SHOW_HEADING}</h2>
      {sentences.map((one) => (
        <p key={one}>{one}</p>
      ))}
    </section>
  );
}

export function LiveRuns() {
  const answer = useResource<unknown>(LIVE_RUNS_API_PATH);
  const body = answer.data === null ? null : readLiveRuns(answer.data);

  return (
    <article className="page">
      <h1>{LIVE_RUNS_LABEL}</h1>
      <p className="lede">{LIVE_RUNS_LEDE}</p>

      {answer.busy ? (
        <p className="note" role="status">
          Loading.
        </p>
      ) : null}

      {answer.failure ? (
        <section className="card">
          <FailureNotice failure={answer.failure} />
        </section>
      ) : null}

      {!answer.busy && !answer.failure && body === null ? (
        <p className="note">{UNREADABLE_ANSWER}</p>
      ) : null}

      {body === null ? null : (
        <>
          <Running body={body} />
          <Waiting body={body} />
          <CannotShow body={body} />
        </>
      )}
    </article>
  );
}
