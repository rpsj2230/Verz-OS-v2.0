/**
 * Scheduled jobs: every job the worker runs on a schedule, how it last went, and pause, resume and
 * run now.
 *
 * Beside Live runs under Operate. Live runs answers what is running this minute; this answers how
 * each job has been going and lets an administrator stop the schedule starting one or ask for one
 * run. Every control is confirmed with what the worker will do and what stops being kept true, and
 * a success says what will happen and when rather than that it has.
 *
 * **Four states, four sentences.** Loading, a transport failure, a refusal with its reference, and
 * an answer this console cannot read are each said, and an empty list is a fifth sentence.
 *
 * **No stop control**, for `liveRunsQuery.A_STOP_BUTTON_THAT_REACHES_NOTHING_IS_WORSE_THAN_NONE`,
 * and the page says so.
 *
 * Task ids: M27.8.13
 */

import { useCallback, useState } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { ConfirmAction } from "../components/ConfirmAction";
import { FailureNotice } from "../ui/FailureNotice";
import {
  ACTION_LABELS,
  actionConsequence,
  actionPath,
  actionQuestion,
  actionWarning,
  CANNOT_HEADING,
  CONTROLS_SWITCHED_OFF,
  doneSentence,
  JOBS_API_PATH,
  JOBS_CAPTION,
  JOBS_CRUMB,
  JOBS_LABEL,
  JOBS_LEDE,
  KEEP_IT,
  lastRunWords,
  MESSAGE_KEPT_ON_THE_SERVER,
  NEVER_SUCCEEDED,
  NO_JOBS,
  NO_RUN_CAN_BE_STOPPED,
  EVERY_CHANGE_IS_IN_THE_AUDIT_TRAIL,
  READING_JOBS,
  readJobs,
  stateWords,
  UNREADABLE_ANSWER,
  type JobAction,
  type JobRow,
} from "./jobsQuery";
import { when } from "./sessionsQuery";

interface Pending {
  readonly action: JobAction;
  readonly row: JobRow;
}

/** The controls a row offers, in the order they are drawn. Presentation only. */
function actionsFor(row: JobRow, switchedOn: boolean): JobAction[] {
  const actions: JobAction[] = [];
  if (row.paused) {
    actions.push("resume");
  } else if (switchedOn && row.runnable) {
    actions.push("pause");
  }
  if (switchedOn && row.runnable) {
    actions.push("run");
  }
  return actions;
}

function JobList({ onDone }: { readonly onDone: (sentence: string) => void }) {
  const answer = useResource<unknown>(JOBS_API_PATH);
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const act = useCallback(
    (asked: Pending) => {
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(actionPath(asked.action, asked.row.control), {
          method: "POST",
          body: {},
        });
        setBusy(false);
        setPending(null);
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setFailure(null);
        onDone(doneSentence(asked.action, asked.row));
      })();
    },
    [onDone],
  );

  if (answer.busy) {
    return (
      <p className="note" role="status">
        {READING_JOBS}
      </p>
    );
  }
  if (answer.failure) {
    return <FailureNotice failure={answer.failure} />;
  }
  const body = readJobs(answer.data);
  if (body === null) {
    return <p className="note">{UNREADABLE_ANSWER}</p>;
  }
  const switchedOn = body.controls_switched_on;
  const anyFailed = body.jobs.some((row) => row.last_outcome === "failed");

  return (
    <>
      {failure === null ? null : <FailureNotice failure={failure} />}
      {pending === null ? null : (
        <ConfirmAction
          question={actionQuestion(pending.action, pending.row)}
          consequence={actionConsequence(pending.action, pending.row)}
          {...(actionWarning(pending.action, pending.row) === undefined
            ? {}
            : { warning: actionWarning(pending.action, pending.row) ?? "" })}
          confirmLabel={ACTION_LABELS[pending.action]}
          cancelLabel={KEEP_IT}
          busy={busy}
          onConfirm={() => {
            act(pending);
          }}
          onCancel={() => {
            setPending(null);
          }}
        />
      )}
      <section className="card" aria-labelledby="jobs-heading">
        <h2 id="jobs-heading">{JOBS_LABEL}</h2>
        {body.may_control && !switchedOn ? <p className="note">{CONTROLS_SWITCHED_OFF}</p> : null}
        {body.jobs.length === 0 ? (
          <p className="note">{NO_JOBS}</p>
        ) : (
          <div className="grid__scroll">
            <table className="grid__table">
              <caption className="grid__caption">{JOBS_CAPTION}</caption>
              <thead>
                <tr>
                  <th scope="col">Job</th>
                  <th scope="col">Last run</th>
                  <th scope="col">Last success</th>
                  <th scope="col">State</th>
                  <th scope="col">Control</th>
                </tr>
              </thead>
              <tbody>
                {body.jobs.map((row) => (
                  <tr key={row.control}>
                    <td>
                      <code>{row.control}</code>
                      <p className="note">{row.keeps_true}</p>
                    </td>
                    <td>
                      {lastRunWords(row)}
                      {row.last_started_at ? <p className="note">{when(row.last_started_at)}</p> : null}
                    </td>
                    <td>{row.last_succeeded_at ? when(row.last_succeeded_at) : NEVER_SUCCEEDED}</td>
                    <td>
                      {stateWords(row).map((word) => (
                        <p key={word}>{word}</p>
                      ))}
                    </td>
                    <td>
                      {!row.runnable && row.needs ? <p className="note">{row.needs}</p> : null}
                      {body.may_control
                        ? actionsFor(row, switchedOn).map((action) => (
                            <button
                              key={action}
                              type="button"
                              className="button"
                              disabled={busy}
                              aria-label={`${ACTION_LABELS[action]}: ${row.control}`}
                              onClick={() => {
                                setFailure(null);
                                setPending({ action, row });
                              }}
                            >
                              {ACTION_LABELS[action]}
                            </button>
                          ))
                        : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {anyFailed ? <p className="note">{MESSAGE_KEPT_ON_THE_SERVER}</p> : null}
      </section>
      <section className="card" aria-labelledby="jobs-cannot">
        <h2 id="jobs-cannot">{CANNOT_HEADING}</h2>
        {body.no_run_can_be_stopped === false ? null : <p>{NO_RUN_CAN_BE_STOPPED}</p>}
        {body.every_change_is_in_the_audit_trail === false ? null : (
          <p>{EVERY_CHANGE_IS_IN_THE_AUDIT_TRAIL}</p>
        )}
      </section>
    </>
  );
}

export function Jobs() {
  // A counter rather than a boolean, so two controls in a row remount twice. Never rendered.
  const [generation, setGeneration] = useState(0);
  const [done, setDone] = useState<string | null>(null);
  const onDone = useCallback((sentence: string) => {
    setDone(sentence);
    setGeneration((current) => current + 1);
  }, []);

  return (
    <article className="page">
      <p className="note">{JOBS_CRUMB}</p>
      <h1>{JOBS_LABEL}</h1>
      <p className="lede">{JOBS_LEDE}</p>
      {done === null ? null : (
        <p className="note" role="status">
          {done}
        </p>
      )}
      <JobList key={generation} onDone={onDone} />
    </article>
  );
}
