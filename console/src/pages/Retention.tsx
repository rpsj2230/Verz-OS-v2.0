/**
 * Retention and erasure: what the sweep found and whether it may act, the legal holds that stop
 * it, how long each kind of thing is kept, and the export log and deletion queue this install
 * does not record.
 *
 * `docs/screens.html` does not draw this screen; `brain.console.screens` registers it under Govern
 * as "how long each kind of thing is kept, what is due for deletion, and the queue of erasure
 * requests", and M27.7.24 adds exports. So the layout is the console's Govern layout, the crumb,
 * the heading and one card per question, in the order a person deciding about a deletion reads
 * them: what the sweep found, what stops it, what the windows are, and what is not recorded.
 *
 * **Releasing the sweep and placing or lifting a hold are confirmed, and each confirmation says
 * what will happen in the API's words.** A release names the counts from the report on the page
 * and then `brain.erasure_routes.RELEASING`; a hold names who it covers and then `HOLDING`. A
 * success says what the database recorded and when, and the page reads the report again, so what
 * is drawn is what is stored rather than what was sent.
 *
 * **Nothing here decides who may act.** `may_release` and `may_hold` came from the retention
 * module's own functions on the server and only decide whether a control is drawn; the write route
 * decides again. A reader shown no report is shown no release, because a release is the record that
 * somebody read the report it names.
 *
 * **The export log and the erasure queue are lists, each under the sentence saying what it cannot
 * show.** `ops.data_export` records every export taken from the console and `ops.erasure_request`
 * every request filed, and the API decides which rows this reader is shown. A reader who may open
 * the screen and may not read exports is told so rather than shown an empty table, which would read
 * as nothing having left the building.
 *
 * **Filing an erasure request is checked, confirmed and then sent, and the confirmation is the API's
 * sentence**, `brain.erasure_routes.ERASING`, which says what is removed, what is retired and still
 * stored, what is kept and what is never reached. A finished request is drawn store by store in the
 * same four terms, so a request that finished as incomplete names what still holds the person's data.
 *
 * Imported statically rather than split: it mounts neither heavy library and no stylesheet.
 *
 * Task ids: M27.7.24
 */

import { useCallback, useState, type ReactNode } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { ConfirmAction } from "../components/ConfirmAction";
import { Notice } from "../ui/Notice";
import { when } from "./artifactsQuery";
import {
  CONTROLS_API_PATH,
  EMPTY_ERASURE,
  EMPTY_HOLD,
  ERASURES_API_PATH,
  EXPORT_LOG_API_PATH,
  HOLD_API_PATH,
  LIFT_API_PATH,
  RELEASE_API_PATH,
  RETENTION_API_PATH,
  WITHDRAWAL_API_PATH,
  erasureBody,
  erasureProblems,
  erasureState,
  holdBody,
  holdProblems,
  holdQuestion,
  liftProblems,
  releasable,
  releaseCounts,
  reportOf,
  storeLines,
  type Controls,
  type ErasureBody,
  type ErasureForm,
  type ErasureQueue,
  type ExportLog,
  type HoldBody,
  type HoldForm,
  type Report,
  type RetentionAnswer,
} from "./retentionQuery";
import { SOMETHING_DID_NOT_WORK } from "./Overview";

export const RETENTION_HEADING = "Retention and erasure";
export const RETENTION_CRUMB = "Govern › Retention and erasure";
export const RETENTION_LEDE =
  "How long each kind of thing is kept, what the sweep found past its window, what a legal hold " +
  "is keeping, and whether anybody asked for their data to be erased or taken out.";

/** The states. */
export const READING_RETENTION = "Reading what is kept and what is due.";
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";
export const NO_REPORT =
  "There is no retention report to show. Either the sweep has not reported on this install, or " +
  "its report covers more than you may see.";

export const RELEASE_LABEL = "Release the sweep";
export const KEEP_REPORTING = "Keep it reporting";
export const WITHDRAW_LABEL = "Put the sweep back to reporting";
export const LEAVE_RELEASED = "Leave it released";
export const PLACE_LABEL = "Place hold";
export const DO_NOT_PLACE = "Do not place it";
export const LIFT_LABEL = "Lift hold";
export const KEEP_HOLD = "Keep the hold";

/** What a reader who may not act is told instead of a control. */
export const RELEASE_NOT_YOURS =
  "Releasing the sweep, or putting it back to reporting, needs the retention authority over the " +
  "whole company.";
export const HOLD_NOT_YOURS =
  "Placing or lifting a legal hold needs the legal hold authority over the whole company.";

/** Which holds are listed, said beside them. */
export const HOLDS_AS_CITED =
  "Holds are listed as the newest report cites them. A hold placed since that report is not " +
  "listed until the sweep reports again, and lifting one by its reference works either way.";
export const NO_HOLDS_CITED = "The newest report was under no legal hold.";
export const NO_REPORT_NO_HOLDS = "No report lists the holds in force.";

export const STORES_CAPTION = "What the sweep found in each store";
export const KEPT_CAPTION = "How long each kind of thing is kept";
export const HOLD_FORM_LABEL = "Place a legal hold";
export const LIFT_FORM_LABEL = "Lift a legal hold";

export function releasedSentence(at: string): string {
  return `The sweep was released at ${when(at)}. Its next run removes what is past its window.`;
}
export function withdrawnSentence(at: string): string {
  return `The sweep was put back to reporting at ${when(at)}. Its next run removes nothing.`;
}
export function placedSentence(holdId: string, at: string): string {
  return `Legal hold ${holdId} was placed at ${when(at)}. The sweep keeps what it covers from now.`;
}
export function liftedSentence(holdId: string, at: string): string {
  return `Legal hold ${holdId} was lifted at ${when(at)}.`;
}

export const ERASURE_FORM_LABEL = "Ask for somebody's data to be erased";
export const FILE_ERASURE_LABEL = "File the erasure request";
export const DO_NOT_FILE = "Do not file it";
export const ERASE_NOT_YOURS =
  "Filing a request to erase somebody's data needs the erasure authority over the whole company.";
export const NO_ERASURE_REQUESTS = "No request to erase anybody's data has been filed that you may see.";
export const ERASURES_CAPTION = "Requests to erase somebody's data";
export const READING_EXPORTS = "Reading the export log.";
export const NO_EXPORTS = "No export has been taken on this install that you may see.";
export const EXPORTS_CAPTION = "Exports taken from this install";

export function erasureQuestion(body: ErasureBody): string {
  return `Erase the data this install holds about ${body.subject_id}, under ${body.reason_reference}?`;
}
export function filedSentence(subject: string, at: string): string {
  return (
    `The request to erase the data held about ${subject} was filed at ${when(at)}. The queue ` +
    "carries it out on its next run, every quarter of an hour, and this page shows how it finished."
  );
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

function stamp(payload: unknown, key: string): string {
  if (typeof payload !== "object" || payload === null) {
    return "";
  }
  const found = (payload as Record<string, unknown>)[key];
  return typeof found === "string" ? found : "";
}

/** One write, its busy flag and its failure, so every control reports the same way. */
function useWrite(onDone: (sentence: string) => void) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const send = useCallback(
    (path: string, body: unknown, sentence: (payload: unknown) => string, after: () => void) => {
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(path, { method: "POST", body });
        setBusy(false);
        after();
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setFailure(null);
        onDone(sentence(result.data));
      })();
    },
    [onDone],
  );
  return { busy, failure, setFailure, send };
}

function Row({ label, children }: { readonly label: string; readonly children: ReactNode }) {
  return (
    <div className="fields__row">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function Sweep({
  report,
  controls,
  onDone,
}: {
  readonly report: Report | null;
  readonly controls: Controls;
  readonly onDone: (sentence: string) => void;
}) {
  const [confirming, setConfirming] = useState<"release" | "withdraw" | null>(null);
  const write = useWrite(onDone);

  if (report === null) {
    return (
      <section className="card">
        <h2>The retention sweep</h2>
        <p className="note">{NO_REPORT}</p>
      </section>
    );
  }

  return (
    <section className="card">
      <h2>The retention sweep</h2>
      <dl className="fields" aria-label="The newest retention report">
        <Row label="Report of">{when(report.at)}</Row>
        <Row label="What that run did">
          {report.report_only
            ? "Reported only, and removed nothing."
            : `Acted, and removed ${String(report.removed)} items.`}
        </Row>
        <Row label="Whether it counted every store it reaches">
          {report.complete ? "Yes." : "No: some stores it reaches were not counted."}
        </Row>
        {report.failure === null ? null : (
          <Row label="It failed">{`It removed nothing: ${report.failure}`}</Row>
        )}
        <Row label="The next run">
          {report.released
            ? "Released: it removes what is past its window."
            : "Not released: it reports again and removes nothing."}
        </Row>
      </dl>

      <div className="grid__scroll">
        <table className="grid__table" aria-label={STORES_CAPTION}>
          <thead>
            <tr>
              <th scope="col">Store</th>
              <th scope="col">Kept as</th>
              <th scope="col">Past its window</th>
              <th scope="col">Held</th>
              <th scope="col">Due</th>
              <th scope="col">Removed</th>
              <th scope="col">Queued</th>
              <th scope="col">Oldest, in days</th>
            </tr>
          </thead>
          <tbody>
            {report.stores.map((line) => (
              <tr key={line.store}>
                <td>
                  <code>{line.store}</code>
                  {line.reached ? null : <p className="note">{line.unreached_because}</p>}
                </td>
                <td>
                  {line.data_class}, {line.days === null ? line.lifetime : `${String(line.days)} days`}
                </td>
                <td>{line.reached ? String(line.beyond_horizon) : ""}</td>
                <td>{line.reached ? String(line.held) : ""}</td>
                <td>{line.reached ? String(line.due) : ""}</td>
                <td>{line.reached ? String(line.removed) : ""}</td>
                <td>
                  {line.reached ? String(line.queued) : ""}
                  {line.queued_because === "" ? null : (
                    <p className="note">{line.queued_because}</p>
                  )}
                </td>
                <td>{line.oldest_days === null ? "" : String(line.oldest_days)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {report.findings.length === 0 ? null : (
        <ul aria-label="What the sweep found wrong">
          {report.findings.map((one) => (
            <li key={one}>{one}</li>
          ))}
        </ul>
      )}

      {write.failure === null ? null : <Failure failure={write.failure} />}

      {confirming === "release" ? (
        <ConfirmAction
          question={`Release the sweep after the report of ${when(report.at)}?`}
          consequence={`${releaseCounts(report, when(report.at))} ${controls.releasing}`}
          confirmLabel={RELEASE_LABEL}
          cancelLabel={KEEP_REPORTING}
          busy={write.busy}
          onConfirm={() => {
            write.send(
              RELEASE_API_PATH,
              { after_report: report.report_id },
              (payload) => releasedSentence(stamp(payload, "released_at")),
              () => {
                setConfirming(null);
              },
            );
          }}
          onCancel={() => {
            setConfirming(null);
          }}
        />
      ) : null}
      {confirming === "withdraw" ? (
        <ConfirmAction
          question="Put the sweep back to reporting?"
          consequence={controls.withdrawing}
          confirmLabel={WITHDRAW_LABEL}
          cancelLabel={LEAVE_RELEASED}
          busy={write.busy}
          onConfirm={() => {
            write.send(
              WITHDRAWAL_API_PATH,
              undefined,
              (payload) => withdrawnSentence(stamp(payload, "withdrawn_at")),
              () => {
                setConfirming(null);
              },
            );
          }}
          onCancel={() => {
            setConfirming(null);
          }}
        />
      ) : null}

      {confirming !== null ? null : !controls.may_release ? (
        <p className="note">{RELEASE_NOT_YOURS}</p>
      ) : report.released ? (
        <div className="form-actions">
          <button
            type="button"
            className="button"
            disabled={write.busy}
            onClick={() => {
              write.setFailure(null);
              setConfirming("withdraw");
            }}
          >
            {WITHDRAW_LABEL}
          </button>
        </div>
      ) : releasable(report) ? (
        <div className="form-actions">
          <button
            type="button"
            className="button"
            disabled={write.busy}
            onClick={() => {
              write.setFailure(null);
              setConfirming("release");
            }}
          >
            {RELEASE_LABEL}
          </button>
        </div>
      ) : null}
    </section>
  );
}

function Holds({
  report,
  controls,
  onDone,
}: {
  readonly report: Report | null;
  readonly controls: Controls;
  readonly onDone: (sentence: string) => void;
}) {
  const [form, setForm] = useState<HoldForm>(EMPTY_HOLD);
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [placing, setPlacing] = useState<HoldBody | null>(null);
  const [lifting, setLifting] = useState("");
  const [liftTrouble, setLiftTrouble] = useState<readonly string[]>([]);
  const [liftingNow, setLiftingNow] = useState<string | null>(null);
  const write = useWrite(onDone);
  const set = (name: keyof HoldForm) => (value: string | boolean) => {
    setForm({ ...form, [name]: value });
  };

  return (
    <section className="card">
      <h2>Legal holds</h2>
      <p>{controls.holding}</p>
      {report === null ? (
        <p className="note">{NO_REPORT_NO_HOLDS}</p>
      ) : report.holds.length === 0 ? (
        <p className="note">{NO_HOLDS_CITED}</p>
      ) : (
        <ul aria-label="Holds the newest report was under">
          {report.holds.map((one) => (
            <li key={one.hold_id}>
              <code>{one.hold_id}</code> {one.reason_code}
              {one.company_wide ? ", over everybody" : ""}
            </li>
          ))}
        </ul>
      )}
      <p className="note">{HOLDS_AS_CITED}</p>

      {write.failure === null ? null : <Failure failure={write.failure} />}

      {!controls.may_hold ? (
        <p className="note">{HOLD_NOT_YOURS}</p>
      ) : (
        <>
          {placing === null ? (
            <form
              className="form"
              aria-label={HOLD_FORM_LABEL}
              onSubmit={(event) => {
                event.preventDefault();
                const found = holdProblems(form);
                setProblems(found);
                if (found.length === 0) {
                  write.setFailure(null);
                  setPlacing(holdBody(form));
                }
              }}
            >
              <h3>{HOLD_FORM_LABEL}</h3>
              <label className="control-label">
                Reference{" "}
                <input
                  className="form-control"
                  value={form.holdId}
                  onChange={(event) => {
                    set("holdId")(event.target.value);
                  }}
                />
              </label>
              <label className="control-label">
                Reason code{" "}
                <input
                  className="form-control"
                  value={form.reasonCode}
                  onChange={(event) => {
                    set("reasonCode")(event.target.value);
                  }}
                />
              </label>
              <label className="control-label">
                People it covers, by reference{" "}
                <textarea
                  className="form-control"
                  value={form.subjects}
                  onChange={(event) => {
                    set("subjects")(event.target.value);
                  }}
                />
              </label>
              <label className="control-label">
                People whose actions it covers, by reference{" "}
                <textarea
                  className="form-control"
                  value={form.actors}
                  onChange={(event) => {
                    set("actors")(event.target.value);
                  }}
                />
              </label>
              <label className="control-label">
                <input
                  type="checkbox"
                  checked={form.everybody}
                  onChange={(event) => {
                    set("everybody")(event.target.checked);
                  }}
                />{" "}
                Hold everybody
              </label>
              {problems.length === 0 ? null : (
                <ul role="alert" aria-label="What to change before placing the hold">
                  {problems.map((one) => (
                    <li key={one}>{one}</li>
                  ))}
                </ul>
              )}
              <div className="form-actions">
                <button type="submit" className="button" disabled={write.busy}>
                  {PLACE_LABEL}
                </button>
              </div>
            </form>
          ) : (
            <ConfirmAction
              question={holdQuestion(placing)}
              consequence={controls.holding}
              confirmLabel={PLACE_LABEL}
              cancelLabel={DO_NOT_PLACE}
              busy={write.busy}
              onConfirm={() => {
                const body = placing;
                write.send(
                  HOLD_API_PATH,
                  body,
                  (payload) => placedSentence(body.hold_id, stamp(payload, "placed_at")),
                  () => {
                    setPlacing(null);
                  },
                );
              }}
              onCancel={() => {
                setPlacing(null);
              }}
            />
          )}

          {liftingNow === null ? (
            <form
              className="form"
              aria-label={LIFT_FORM_LABEL}
              onSubmit={(event) => {
                event.preventDefault();
                const found = liftProblems(lifting);
                setLiftTrouble(found);
                if (found.length === 0) {
                  write.setFailure(null);
                  setLiftingNow(lifting);
                }
              }}
            >
              <h3>{LIFT_FORM_LABEL}</h3>
              <label className="control-label">
                Reference of the hold{" "}
                <input
                  className="form-control"
                  list="cited-holds"
                  value={lifting}
                  onChange={(event) => {
                    setLifting(event.target.value);
                  }}
                />
              </label>
              <datalist id="cited-holds">
                {(report?.holds ?? []).map((one) => (
                  <option key={one.hold_id} value={one.hold_id} />
                ))}
              </datalist>
              {liftTrouble.length === 0 ? null : (
                <ul role="alert" aria-label="What to change before lifting the hold">
                  {liftTrouble.map((one) => (
                    <li key={one}>{one}</li>
                  ))}
                </ul>
              )}
              <div className="form-actions">
                <button type="submit" className="button" disabled={write.busy}>
                  {LIFT_LABEL}
                </button>
              </div>
            </form>
          ) : (
            <ConfirmAction
              question={`Lift legal hold ${liftingNow}?`}
              consequence={controls.lifting}
              confirmLabel={LIFT_LABEL}
              cancelLabel={KEEP_HOLD}
              busy={write.busy}
              onConfirm={() => {
                const holdId = liftingNow;
                write.send(
                  LIFT_API_PATH,
                  { hold_id: holdId },
                  (payload) => liftedSentence(holdId, stamp(payload, "lifted_at")),
                  () => {
                    setLiftingNow(null);
                  },
                );
              }}
              onCancel={() => {
                setLiftingNow(null);
              }}
            />
          )}
        </>
      )}
    </section>
  );
}

function ExportsTaken() {
  const log = useResource<ExportLog>(EXPORT_LOG_API_PATH);

  if (log.failure !== null) {
    return <Failure failure={log.failure} />;
  }
  if (log.busy || log.data === null) {
    return (
      <p className="note" role="status">
        {READING_EXPORTS}
      </p>
    );
  }
  if (log.data.exports.length === 0) {
    return <p className="note">{NO_EXPORTS}</p>;
  }
  return (
    <div className="grid__scroll">
      <table className="grid__table" aria-label={EXPORTS_CAPTION}>
        <thead>
          <tr>
            <th scope="col">Taken</th>
            <th scope="col">By</th>
            <th scope="col">Why</th>
            <th scope="col">Entries</th>
            <th scope="col">Chain verified</th>
            <th scope="col">Document digest</th>
          </tr>
        </thead>
        <tbody>
          {log.data.exports.map((one) => (
            <tr key={one.export_id}>
              <td>{when(one.produced_at)}</td>
              <td>
                <code>{one.requested_by}</code>
              </td>
              <td>
                {one.reason}, <code>{one.reason_reference}</code>
              </td>
              <td>
                {one.first_seq === null
                  ? "none"
                  : `${String(one.entries)}, from ${String(one.first_seq)} to ${String(one.last_seq)}`}
              </td>
              <td>{one.verified ? "Yes" : "No"}</td>
              <td>
                <code>{one.document_digest}</code>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Erasures({
  queue,
  controls,
  onDone,
}: {
  readonly queue: ErasureQueue;
  readonly controls: Controls;
  readonly onDone: (sentence: string) => void;
}) {
  const [form, setForm] = useState<ErasureForm>(EMPTY_ERASURE);
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [filing, setFiling] = useState<ErasureBody | null>(null);
  const write = useWrite(onDone);

  return (
    <section className="card">
      <h2>Erasure requests</h2>
      <p>{controls.erasures}</p>
      {queue.requests.length === 0 ? (
        <p className="note">{NO_ERASURE_REQUESTS}</p>
      ) : (
        <div className="grid__scroll">
          <table className="grid__table" aria-label={ERASURES_CAPTION}>
            <thead>
              <tr>
                <th scope="col">Filed</th>
                <th scope="col">Person</th>
                <th scope="col">Reference</th>
                <th scope="col">Filed by</th>
                <th scope="col">Where it stands</th>
                <th scope="col">What it did</th>
              </tr>
            </thead>
            <tbody>
              {queue.requests.map((one) => (
                <tr key={one.request_id}>
                  <td>{when(one.requested_at)}</td>
                  <td>
                    <code>{one.subject_id}</code>
                  </td>
                  <td>
                    <code>{one.reason_reference}</code>
                  </td>
                  <td>
                    <code>{one.requested_by}</code>
                  </td>
                  <td>{erasureState(one, when)}</td>
                  <td>
                    {storeLines(one).length === 0 ? null : (
                      <ul aria-label={`What the request ${one.request_id} did`}>
                        {storeLines(one).map((line) => (
                          <li key={line}>{line}</li>
                        ))}
                      </ul>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {write.failure === null ? null : <Failure failure={write.failure} />}

      {!controls.may_erase ? (
        <p className="note">{ERASE_NOT_YOURS}</p>
      ) : filing === null ? (
        <form
          className="form"
          aria-label={ERASURE_FORM_LABEL}
          onSubmit={(event) => {
            event.preventDefault();
            const found = erasureProblems(form);
            setProblems(found);
            if (found.length === 0) {
              write.setFailure(null);
              setFiling(erasureBody(form));
            }
          }}
        >
          <h3>{ERASURE_FORM_LABEL}</h3>
          <label className="control-label">
            Person, by reference{" "}
            <input
              className="form-control"
              value={form.subject}
              onChange={(event) => {
                setForm({ ...form, subject: event.target.value });
              }}
            />
          </label>
          <label className="control-label">
            Matter or ticket reference{" "}
            <input
              className="form-control"
              value={form.reference}
              onChange={(event) => {
                setForm({ ...form, reference: event.target.value });
              }}
            />
          </label>
          {problems.length === 0 ? null : (
            <ul role="alert" aria-label="What to change before filing the request">
              {problems.map((one) => (
                <li key={one}>{one}</li>
              ))}
            </ul>
          )}
          <div className="form-actions">
            <button type="submit" className="button" disabled={write.busy}>
              {FILE_ERASURE_LABEL}
            </button>
          </div>
        </form>
      ) : (
        <ConfirmAction
          question={erasureQuestion(filing)}
          consequence={controls.erasing}
          confirmLabel={FILE_ERASURE_LABEL}
          cancelLabel={DO_NOT_FILE}
          busy={write.busy}
          onConfirm={() => {
            const body = filing;
            write.send(
              ERASURES_API_PATH,
              body,
              (payload) => filedSentence(body.subject_id, stamp(payload, "requested_at")),
              () => {
                setFiling(null);
                setForm(EMPTY_ERASURE);
              },
            );
          }}
          onCancel={() => {
            setFiling(null);
          }}
        />
      )}
    </section>
  );
}

function RetentionBody({ onDone }: { readonly onDone: (sentence: string) => void }) {
  const answer = useResource<RetentionAnswer>(RETENTION_API_PATH);
  const controls = useResource<Controls>(CONTROLS_API_PATH);
  const queue = useResource<ErasureQueue>(ERASURES_API_PATH);

  const failure = answer.failure ?? controls.failure ?? queue.failure;
  if (failure) {
    return (
      <section className="card">
        <Failure failure={failure} />
      </section>
    );
  }
  if (answer.busy || controls.busy || queue.busy || controls.data === null || queue.data === null) {
    return (
      <p className="note" role="status">
        {READING_RETENTION}
      </p>
    );
  }
  const report = reportOf(answer.data);
  const said = controls.data;

  return (
    <>
      <Sweep report={report} controls={said} onDone={onDone} />
      <Holds report={report} controls={said} onDone={onDone} />
      <section className="card">
        <h2>{KEPT_CAPTION}</h2>
        <div className="grid__scroll">
          <table className="grid__table" aria-label={KEPT_CAPTION}>
            <thead>
              <tr>
                <th scope="col">Kind of thing</th>
                <th scope="col">How long</th>
                <th scope="col">Why</th>
              </tr>
            </thead>
            <tbody>
              {said.kept.map((one) => (
                <tr key={one.data_class}>
                  <td>
                    <code>{one.data_class}</code>
                  </td>
                  <td>{one.days === null ? one.lifetime : `${String(one.days)} days`}</td>
                  <td>{one.because}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="card">
        <h2>Exports</h2>
        <p>{said.exports}</p>
        {said.may_read_exports ? <ExportsTaken /> : <p className="note">{said.exports_not_yours}</p>}
      </section>
      <Erasures queue={queue.data} controls={said} onDone={onDone} />
    </>
  );
}

export function Retention() {
  // A counter rather than a boolean, so two writes in a row read the report twice. Never drawn.
  const [generation, setGeneration] = useState(0);
  const [done, setDone] = useState<string | null>(null);
  const onDone = useCallback((sentence: string) => {
    setDone(sentence);
    setGeneration((current) => current + 1);
  }, []);

  return (
    <article className="page">
      <p className="note">{RETENTION_CRUMB}</p>
      <h1>{RETENTION_HEADING}</h1>
      <p className="lede">{RETENTION_LEDE}</p>
      {done === null ? null : (
        <p className="note" role="status">
          {done}
        </p>
      )}
      <RetentionBody key={generation} onDone={onDone} />
    </article>
  );
}
