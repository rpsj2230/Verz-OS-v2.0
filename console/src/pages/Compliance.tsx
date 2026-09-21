/**
 * Compliance: who a sensitive question is routed to, what each connected source reads, and the
 * breach cases with the clock each one is on.
 *
 * Three owner sentences had modules and no screen (M24.2.2, M24.2.3, M24.2.4), and
 * `brain.compliance_routes` answers all three under one authority, `admin:compliance`, so they are
 * one page in Govern rather than three: the person who names the handler for grievances is the same
 * person who records a breach, and splitting them would be three screens with one reader.
 *
 * **Every write here is confirmed, and every one is a record that cannot be taken back.** Naming a
 * person replaces whoever was named; opening a case starts a statutory clock in the ledger; an
 * assessment, a notification and an exception are each a claim the Commission may later ask about;
 * closing ends the case. Each form is judged before anything is asked, in `complianceQuery.ts`, so a
 * confirmation is only ever about a write the route will accept the shape of.
 *
 * **The clock and the findings are the server's, and drawn as served.** `clock_starts_at`, each
 * obligation's deadline and whether it is overdue come from `brain.audit.compliance`; a page that
 * recomputed them would be a second opinion on a legal deadline, and the wrong copy would be the one
 * somebody read. Close is drawn disabled unless the case says it is closable, with the route's own
 * sentence saying why.
 *
 * **The tally is drawn as the API released it.** A suppressed month says it is suppressed and draws
 * no number, because a small count of intercepted questions points at the people who asked.
 *
 * Imported statically rather than split: it mounts neither heavy library and no stylesheet.
 *
 * Task ids: M24.2.2, M24.2.3, M24.2.4
 */

import { useCallback, useState, type ReactNode } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { ConfirmAction } from "../components/ConfirmAction";
import { FailureNotice } from "../ui/FailureNotice";
import { when } from "./artifactsQuery";
import {
  AWARENESS_SOURCES,
  BREACHES_API_PATH,
  EMPTY_ASSESS,
  EMPTY_EXCEPTION,
  EMPTY_NAME,
  EMPTY_OPEN,
  EXCEPTION_GROUNDS,
  GROUND_LABELS,
  REGISTER_API_PATH,
  SOURCE_LABELS,
  TOPICS_API_PATH,
  assessBody,
  assessProblems,
  breachStepApiPath,
  exceptionBody,
  exceptionProblems,
  isOpen,
  labelOf,
  nameBody,
  nameProblems,
  notifiedBody,
  notifiedProblems,
  obligationSentence,
  openBody,
  openProblems,
  tallySentence,
  topicApiPath,
  type AssessBody,
  type AssessForm,
  type Breach,
  type BreachesAnswer,
  type ExceptionBody,
  type ExceptionForm,
  type NameBody,
  type NameForm,
  type NotifiedBody,
  type OpenBody,
  type OpenForm,
  type RegisterAnswer,
  type RegisterRow,
  type TopicsAnswer,
} from "./complianceQuery";

export const COMPLIANCE_HEADING = "Compliance";
export const COMPLIANCE_CRUMB = "Govern › Compliance";
export const COMPLIANCE_LEDE =
  "Who a sensitive question is routed to, what each connected source reads and keeps, and every " +
  "data breach case with the clock it is on.";

/** The states. */
export const READING_COMPLIANCE = "Reading the topics, the register and the breach cases.";
export const NO_TOPICS = "This install declares no sensitive topic, so there is nobody to name.";
export const NOBODY_NAMED = "Nobody is named. Its notes wait for whoever is named next.";
export const NOTHING_CONNECTED =
  "Nothing is connected, so the register is empty. A source appears here once it is connected.";
export const NO_CASES = "No breach case has been opened.";

/** The section headings, which the tests find the sections by. */
export const TOPICS_HEADING = "Sensitive topics";
export const REGISTER_HEADING = "Processing register";
export const BREACHES_HEADING = "Breach cases";

export const NAME_FORM_LABEL = "Name the person a topic is routed to";
export const NAME_LABEL = "Name this person";
export const KEEP_NAMED = "Keep it as it is";
export const OPEN_FORM_LABEL = "Open a breach case";
export const OPEN_LABEL = "Open the case";
export const DO_NOT_OPEN = "Do not open it";
export const ASSESS_FORM_LABEL = "Record the assessment";
export const ASSESS_LABEL = "Record the assessment";
export const COMMISSION_FORM_LABEL = "Record the Commission notified";
export const COMMISSION_LABEL = "Record the Commission notified";
export const INDIVIDUALS_FORM_LABEL = "Record the individuals notified";
export const INDIVIDUALS_LABEL = "Record the individuals notified";
export const EXCEPTION_FORM_LABEL = "Record a decision not to notify the individuals";
export const EXCEPTION_LABEL = "Record the decision";
export const CLOSE_LABEL = "Close the case";
export const DO_NOT_RECORD = "Do not record it";
export const KEEP_OPEN = "Keep it open";

export const TOPICS_CAPTION = "Who each sensitive topic is routed to";

export function openQuestion(body: OpenBody): string {
  return `Open a breach case from awareness at ${when(body.became_aware_at)}, evidence ${body.evidence_reference}?`;
}
export const OPENING =
  "The case is recorded with you as its recorder and now as the moment it was recorded, and every " +
  "deadline runs from the earliest moment of awareness, not from now. A case is never removed.";

function stamp(payload: unknown, key: string): string {
  if (typeof payload !== "object" || payload === null) {
    return "";
  }
  const found = (payload as Record<string, unknown>)[key];
  return typeof found === "string" ? found : "";
}

/**
 * One breach write, its busy flag and its failure, so every control on a case reports the same way.
 * Every breach route answers with the case as it now stands, so the sentence is built from that.
 */
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

function Problems({ problems, label }: { readonly problems: readonly string[]; readonly label: string }) {
  if (problems.length === 0) {
    return null;
  }
  return (
    <ul role="alert" aria-label={label}>
      {problems.map((one) => (
        <li key={one}>{one}</li>
      ))}
    </ul>
  );
}

// ------------------------------------------------------------------------ sensitive topics
function Topics({ answer, onDone }: { readonly answer: TopicsAnswer; readonly onDone: (sentence: string) => void }) {
  const [form, setForm] = useState<NameForm>(EMPTY_NAME);
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [naming, setNaming] = useState<{ readonly topic: string; readonly body: NameBody } | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const label = (topic: string) => answer.topics.find((one) => one.topic === topic)?.label ?? topic;
  const current = naming === null ? null : (answer.topics.find((one) => one.topic === naming.topic)?.named ?? null);

  return (
    <section className="card">
      <h2>{TOPICS_HEADING}</h2>
      <p>{answer.routing}</p>
      {answer.topics.length === 0 ? (
        <p className="note">{NO_TOPICS}</p>
      ) : (
        <div className="grid__scroll">
          <table className="grid__table" aria-label={TOPICS_CAPTION}>
            <thead>
              <tr>
                <th scope="col">Topic</th>
                <th scope="col">Routed to</th>
                <th scope="col">Named by</th>
              </tr>
            </thead>
            <tbody>
              {answer.topics.map((one) => (
                <tr key={one.topic}>
                  <td>{one.label}</td>
                  <td>{one.named === null ? NOBODY_NAMED : <code>{one.named.principal_id}</code>}</td>
                  <td>
                    {one.named === null ? null : (
                      <>
                        <code>{one.named.named_by}</code>, {when(one.named.named_at)}
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p>{tallySentence(answer.tally, label)}</p>
      <p className="note">What the person asking is told, whatever the topic: {answer.referral}</p>

      {failure === null ? null : <FailureNotice failure={failure} />}

      {naming === null ? (
        <form
          className="form"
          aria-label={NAME_FORM_LABEL}
          onSubmit={(event) => {
            event.preventDefault();
            const found = nameProblems(
              form,
              answer.topics.map((one) => one.topic),
            );
            setProblems(found);
            if (found.length === 0) {
              setFailure(null);
              setNaming({ topic: form.topic, body: nameBody(form) });
            }
          }}
        >
          <h3>{NAME_FORM_LABEL}</h3>
          <label className="control-label">
            Topic{" "}
            <select
              className="form-control"
              name="topic"
              value={form.topic}
              onChange={(event) => {
                setForm({ ...form, topic: event.target.value });
              }}
            >
              <option value="">Choose a topic</option>
              {answer.topics.map((one) => (
                <option key={one.topic} value={one.topic}>
                  {one.label}
                </option>
              ))}
            </select>
          </label>
          <label className="control-label">
            Person, by reference{" "}
            <input
              className="form-control"
              name="principal_id"
              value={form.principalId}
              onChange={(event) => {
                setForm({ ...form, principalId: event.target.value });
              }}
            />
          </label>
          <Problems problems={problems} label="What to change before naming the person" />
          <div className="form-actions">
            <button type="submit" className="button" disabled={busy}>
              {NAME_LABEL}
            </button>
          </div>
        </form>
      ) : (
        <ConfirmAction
          question={`Route ${label(naming.topic)} questions to ${naming.body.principal_id}?`}
          consequence={
            `From now, a note that somebody asked about ${label(naming.topic)}, without what they ` +
            `wrote, goes to ${naming.body.principal_id}` +
            (current === null ? "." : `, in place of ${current.principal_id}.`)
          }
          confirmLabel={NAME_LABEL}
          cancelLabel={KEEP_NAMED}
          busy={busy}
          onConfirm={() => {
            const asked = naming;
            setBusy(true);
            void (async () => {
              const result = await request<unknown>(topicApiPath(asked.topic), { method: "PUT", body: asked.body });
              setBusy(false);
              setNaming(null);
              if (!result.ok) {
                setFailure(result.failure);
                return;
              }
              setFailure(null);
              setForm(EMPTY_NAME);
              onDone(
                `${stamp(result.data, "principal_id")} was named for ${label(asked.topic)} at ` +
                  `${when(stamp(result.data, "named_at"))}.`,
              );
            })();
          }}
          onCancel={() => {
            setNaming(null);
          }}
        />
      )}
    </section>
  );
}

// --------------------------------------------------------------------- processing register
function Connector({ row }: { readonly row: RegisterRow }) {
  return (
    <div>
      <h3>{row.label}</h3>
      <dl className="fields" aria-label={`What ${row.label} reads`}>
        <Row label="Connector">
          <code>{row.connector}</code>
          {row.transport === null ? "" : `, over ${row.transport}`}
          {row.version === null ? "" : `, version ${row.version}`}
        </Row>
        <Row label="Connected">
          by <code>{row.connected_by}</code>, {when(row.connected_at)}
        </Row>
        <Row label="Categories of data">{row.categories.length === 0 ? "None declared." : row.categories.join(", ")}</Row>
        <Row label="Can it write to the source">{row.write_capable ? "Yes." : "No, it only reads."}</Row>
        <Row label="Records read">{row.records_read === null ? "Not read yet." : String(row.records_read)}</Row>
        <Row label="Documents read">{row.documents_read === null ? "Not read yet." : String(row.documents_read)}</Row>
        <Row label="Last read">{row.last_read_at === null ? "Never." : when(row.last_read_at)}</Row>
        {row.problem === "" ? null : <Row label="Problem">{row.problem}</Row>}
      </dl>
      {row.entities.length === 0 ? null : (
        <div className="grid__scroll">
          <table className="grid__table" aria-label={`What ${row.label} reads, by entity`}>
            <thead>
              <tr>
                <th scope="col">Entity</th>
                <th scope="col">Kept as</th>
                <th scope="col">Fields</th>
                <th scope="col">Classes</th>
              </tr>
            </thead>
            <tbody>
              {row.entities.map((one) => (
                <tr key={one.entity}>
                  <td>
                    <code>{one.entity}</code>
                  </td>
                  <td>{one.tier}</td>
                  <td>{one.fields.join(", ")}</td>
                  <td>{one.classes.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Register({ answer }: { readonly answer: RegisterAnswer }) {
  return (
    <section className="card">
      <h2>{REGISTER_HEADING}</h2>
      <p>{answer.counts}</p>
      {answer.connectors.length === 0 ? (
        <p className="note">{NOTHING_CONNECTED}</p>
      ) : (
        answer.connectors.map((row) => <Connector key={row.connector} row={row} />)
      )}
    </section>
  );
}

// -------------------------------------------------------------------------- breach cases
type Pending =
  | { readonly step: "assessment"; readonly body: AssessBody }
  | { readonly step: "commission" | "individuals"; readonly body: NotifiedBody }
  | { readonly step: "exception"; readonly body: ExceptionBody }
  | { readonly step: "close"; readonly body: undefined };

/** What each step's confirmation asks, says and is pressed as. */
function confirmationOf(pending: Pending, caseId: string): { question: string; consequence: string; label: string } {
  switch (pending.step) {
    case "assessment":
      return {
        question: `Record that breach case ${caseId} is ${pending.body.significant_harm ? "" : "not "}likely to result in significant harm?`,
        consequence:
          `The judgement is recorded as yours, with its reasoning at ${pending.body.rationale_reference}` +
          (pending.body.affected_count === null || pending.body.affected_count === undefined
            ? ", and the number affected as not yet established."
            : `, and ${String(pending.body.affected_count)} people affected.`) +
          " The deadlines to notify follow from it.",
        label: ASSESS_LABEL,
      };
    case "commission":
      return {
        question: `Record that the Commission was notified of breach case ${caseId} at ${when(pending.body.at ?? "")}?`,
        consequence: "The case records the notification at that moment, and the deadline shows whether it was in time.",
        label: COMMISSION_LABEL,
      };
    case "individuals":
      return {
        question: `Record that the individuals affected by breach case ${caseId} were notified at ${when(pending.body.at ?? "")}?`,
        consequence: "The case records the notification at that moment, and the deadline shows whether it was in time.",
        label: INDIVIDUALS_LABEL,
      };
    case "exception":
      return {
        question: `Record a decision not to notify the individuals affected by breach case ${caseId}?`,
        consequence:
          `It is filed under "${labelOf(GROUND_LABELS, pending.body.ground)}" as your decision, with its ` +
          `reasoning at ${pending.body.rationale_reference}.`,
        label: EXCEPTION_LABEL,
      };
    case "close":
      return {
        question: `Close breach case ${caseId}?`,
        consequence: "A closed case takes no further steps and stays on record as it stands.",
        label: CLOSE_LABEL,
      };
  }
}

function Case({
  one,
  closing,
  onDone,
}: {
  readonly one: Breach;
  readonly closing: string;
  readonly onDone: (sentence: string) => void;
}) {
  const [assess, setAssess] = useState<AssessForm>(EMPTY_ASSESS);
  const [commission, setCommission] = useState("");
  const [individuals, setIndividuals] = useState("");
  const [exception, setException] = useState<ExceptionForm>(EMPTY_EXCEPTION);
  const [problems, setProblems] = useState<{ readonly form: string; readonly found: readonly string[] }>({
    form: "",
    found: [],
  });
  const [pending, setPending] = useState<Pending | null>(null);
  const write = useWrite(onDone);
  const open = isOpen(one);
  const excused = one.exception_ground !== null;
  const problemsOf = (form: string) => (problems.form === form ? problems.found : []);

  /** Judge one form, and ask for its confirmation only when nothing is wrong with it. */
  const judge = (form: string, found: readonly string[], next: () => Pending) => {
    setProblems({ form, found });
    if (found.length === 0) {
      write.setFailure(null);
      setPending(next());
    }
  };

  return (
    <section className="card" aria-label={`Breach case ${one.case_id}`}>
      <h3>
        Breach case <code>{one.case_id}</code>
        {open ? "" : ", closed"}
      </h3>
      <dl className="fields">
        <Row label="The clock starts">{when(one.clock_starts_at)}</Row>
        <Row label="Became aware">
          {when(one.became_aware_at)}, {one.awareness_basis === "estimated" ? "an estimate" : "observed"}, from{" "}
          {labelOf(SOURCE_LABELS, one.awareness_source).toLowerCase()}
        </Row>
        <Row label="Recorded by">
          <code>{one.recorded_by}</code>
        </Row>
        <Row label="Evidence">
          <code>{one.evidence_reference}</code>
        </Row>
        <Row label="Assessment">
          {one.assessed_at === null
            ? "Not yet made."
            : `${when(one.assessed_at)}: ${one.significant_harm === true ? "likely" : "not likely"} to result in significant harm; ` +
              `${one.affected_count === null ? "the number affected is not yet established" : `${String(one.affected_count)} affected`}` +
              `${one.outcome === null ? "" : `; ${one.outcome.replace(/_/g, " ")}`}.`}
        </Row>
        <Row label="Commission notified">
          {one.commission_notified_at === null ? "Not recorded." : when(one.commission_notified_at)}
        </Row>
        <Row label="Individuals notified">
          {one.individuals_notified_at === null ? "Not recorded." : when(one.individuals_notified_at)}
        </Row>
        {one.exception_ground === null ? null : (
          <Row label="Not notifying the individuals">{labelOf(GROUND_LABELS, one.exception_ground)}</Row>
        )}
        {one.closed_at === null ? null : (
          <Row label="Closed">
            {when(one.closed_at)}
            {one.closed_by === null ? "" : ", by "}
            {one.closed_by === null ? null : <code>{one.closed_by}</code>}
          </Row>
        )}
      </dl>
      {one.obligations.length === 0 ? null : (
        <ul aria-label={`What breach case ${one.case_id} owes`}>
          {one.obligations.map((duty) => (
            <li key={duty.kind}>
              {obligationSentence(duty, when)}
            </li>
          ))}
        </ul>
      )}
      {one.findings.length === 0 ? null : (
        <ul aria-label={`What is wrong with breach case ${one.case_id}`}>
          {one.findings.map((finding) => (
            <li key={finding}>{finding}</li>
          ))}
        </ul>
      )}

      {write.failure === null ? null : <FailureNotice failure={write.failure} />}

      {!open ? null : pending !== null ? (
        <ConfirmAction
          question={confirmationOf(pending, one.case_id).question}
          consequence={confirmationOf(pending, one.case_id).consequence}
          confirmLabel={confirmationOf(pending, one.case_id).label}
          cancelLabel={pending.step === "close" ? KEEP_OPEN : DO_NOT_RECORD}
          busy={write.busy}
          onConfirm={() => {
            const asked = pending;
            write.send(
              breachStepApiPath(one.case_id, asked.step),
              asked.body,
              () => `Breach case ${one.case_id}: ${confirmationOf(asked, one.case_id).label.toLowerCase()}, done.`,
              () => {
                setPending(null);
              },
            );
          }}
          onCancel={() => {
            setPending(null);
          }}
        />
      ) : (
        <>
          {one.assessed_at !== null ? null : (
            <form
              className="form"
              aria-label={ASSESS_FORM_LABEL}
              onSubmit={(event) => {
                event.preventDefault();
                judge("assess", assessProblems(assess), () => ({ step: "assessment", body: assessBody(assess) }));
              }}
            >
              <h4>{ASSESS_FORM_LABEL}</h4>
              <label className="control-label">
                Likely to result in significant harm{" "}
                <select
                  className="form-control"
                  name="significant_harm"
                  value={assess.harm}
                  onChange={(event) => {
                    setAssess({ ...assess, harm: event.target.value });
                  }}
                >
                  <option value="">Choose</option>
                  <option value="yes">Yes</option>
                  <option value="no">No</option>
                </select>
              </label>
              <label className="control-label">
                Where the reasoning is written, by reference{" "}
                <input
                  className="form-control"
                  name="rationale_reference"
                  value={assess.rationaleReference}
                  onChange={(event) => {
                    setAssess({ ...assess, rationaleReference: event.target.value });
                  }}
                />
              </label>
              <label className="control-label">
                How many people are affected, if known{" "}
                <input
                  className="form-control"
                  name="affected_count"
                  inputMode="numeric"
                  value={assess.affectedCount}
                  onChange={(event) => {
                    setAssess({ ...assess, affectedCount: event.target.value });
                  }}
                />
              </label>
              <Problems problems={problemsOf("assess")} label="What to change before recording the assessment" />
              <div className="form-actions">
                <button type="submit" className="button" disabled={write.busy}>
                  {ASSESS_LABEL}
                </button>
              </div>
            </form>
          )}

          {one.commission_notified_at !== null ? null : (
            <form
              className="form"
              aria-label={COMMISSION_FORM_LABEL}
              onSubmit={(event) => {
                event.preventDefault();
                judge("commission", notifiedProblems(commission, new Date()), () => ({
                  step: "commission",
                  body: notifiedBody(commission),
                }));
              }}
            >
              <h4>{COMMISSION_FORM_LABEL}</h4>
              <label className="control-label">
                When the Commission was notified{" "}
                <input
                  className="form-control"
                  type="datetime-local"
                  name="at"
                  value={commission}
                  onChange={(event) => {
                    setCommission(event.target.value);
                  }}
                />
              </label>
              <Problems problems={problemsOf("commission")} label="What to change before recording the notification" />
              <div className="form-actions">
                <button type="submit" className="button" disabled={write.busy}>
                  {COMMISSION_LABEL}
                </button>
              </div>
            </form>
          )}

          {one.individuals_notified_at !== null || excused ? null : (
            <form
              className="form"
              aria-label={INDIVIDUALS_FORM_LABEL}
              onSubmit={(event) => {
                event.preventDefault();
                judge("individuals", notifiedProblems(individuals, new Date()), () => ({
                  step: "individuals",
                  body: notifiedBody(individuals),
                }));
              }}
            >
              <h4>{INDIVIDUALS_FORM_LABEL}</h4>
              <label className="control-label">
                When the individuals were notified{" "}
                <input
                  className="form-control"
                  type="datetime-local"
                  name="at"
                  value={individuals}
                  onChange={(event) => {
                    setIndividuals(event.target.value);
                  }}
                />
              </label>
              <Problems problems={problemsOf("individuals")} label="What to change before recording the notification" />
              <div className="form-actions">
                <button type="submit" className="button" disabled={write.busy}>
                  {INDIVIDUALS_LABEL}
                </button>
              </div>
            </form>
          )}

          {one.individuals_notified_at !== null || excused ? null : (
            <form
              className="form"
              aria-label={EXCEPTION_FORM_LABEL}
              onSubmit={(event) => {
                event.preventDefault();
                judge("exception", exceptionProblems(exception), () => ({
                  step: "exception",
                  body: exceptionBody(exception),
                }));
              }}
            >
              <h4>{EXCEPTION_FORM_LABEL}</h4>
              <label className="control-label">
                Ground{" "}
                <select
                  className="form-control"
                  name="ground"
                  value={exception.ground}
                  onChange={(event) => {
                    setException({ ...exception, ground: event.target.value });
                  }}
                >
                  <option value="">Choose a ground</option>
                  {EXCEPTION_GROUNDS.map((ground) => (
                    <option key={ground} value={ground}>
                      {labelOf(GROUND_LABELS, ground)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="control-label">
                Where the decision is reasoned, by reference{" "}
                <input
                  className="form-control"
                  name="rationale_reference"
                  value={exception.rationaleReference}
                  onChange={(event) => {
                    setException({ ...exception, rationaleReference: event.target.value });
                  }}
                />
              </label>
              <Problems problems={problemsOf("exception")} label="What to change before recording the decision" />
              <div className="form-actions">
                <button type="submit" className="button" disabled={write.busy}>
                  {EXCEPTION_LABEL}
                </button>
              </div>
            </form>
          )}

          <div className="form-actions">
            <button
              type="button"
              className="button"
              disabled={write.busy || !one.closable}
              onClick={() => {
                write.setFailure(null);
                setPending({ step: "close", body: undefined });
              }}
            >
              {CLOSE_LABEL}
            </button>
          </div>
          {one.closable ? null : <p className="note">{closing}</p>}
        </>
      )}
    </section>
  );
}

function OpenCase({ onDone }: { readonly onDone: (sentence: string) => void }) {
  const [form, setForm] = useState<OpenForm>(EMPTY_OPEN);
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [opening, setOpening] = useState<OpenBody | null>(null);
  const write = useWrite(onDone);
  const set = (name: keyof OpenForm) => (value: string) => {
    setForm({ ...form, [name]: value });
  };

  return (
    <section className="card">
      <h3>{OPEN_FORM_LABEL}</h3>
      {write.failure === null ? null : <FailureNotice failure={write.failure} />}
      {opening === null ? (
        <form
          className="form"
          aria-label={OPEN_FORM_LABEL}
          onSubmit={(event) => {
            event.preventDefault();
            const found = openProblems(form, new Date());
            setProblems(found);
            if (found.length === 0) {
              write.setFailure(null);
              setOpening(openBody(form));
            }
          }}
        >
          <label className="control-label">
            When there was first reason to believe it{" "}
            <input
              className="form-control"
              type="datetime-local"
              name="became_aware_at"
              value={form.becameAwareAt}
              onChange={(event) => {
                set("becameAwareAt")(event.target.value);
              }}
            />
          </label>
          <label className="control-label">
            How that moment is known{" "}
            <select
              className="form-control"
              name="basis"
              value={form.basis}
              onChange={(event) => {
                set("basis")(event.target.value);
              }}
            >
              <option value="">Choose</option>
              <option value="observed">Observed from a record</option>
              <option value="estimated">An estimate</option>
            </select>
          </label>
          {form.basis !== "estimated" ? null : (
            <label className="control-label">
              The earliest it could have been{" "}
              <input
                className="form-control"
                type="datetime-local"
                name="earliest_possible_at"
                value={form.earliestPossibleAt}
                onChange={(event) => {
                  set("earliestPossibleAt")(event.target.value);
                }}
              />
            </label>
          )}
          <label className="control-label">
            Where the reason to believe came from{" "}
            <select
              className="form-control"
              name="source"
              value={form.source}
              onChange={(event) => {
                set("source")(event.target.value);
              }}
            >
              <option value="">Choose</option>
              {AWARENESS_SOURCES.map((source) => (
                <option key={source} value={source}>
                  {labelOf(SOURCE_LABELS, source)}
                </option>
              ))}
            </select>
          </label>
          <label className="control-label">
            Where the evidence is, by reference{" "}
            <input
              className="form-control"
              name="evidence_reference"
              value={form.evidenceReference}
              onChange={(event) => {
                set("evidenceReference")(event.target.value);
              }}
            />
          </label>
          <Problems problems={problems} label="What to change before opening the case" />
          <div className="form-actions">
            <button type="submit" className="button" disabled={write.busy}>
              {OPEN_LABEL}
            </button>
          </div>
        </form>
      ) : (
        <ConfirmAction
          question={openQuestion(opening)}
          consequence={OPENING}
          confirmLabel={OPEN_LABEL}
          cancelLabel={DO_NOT_OPEN}
          busy={write.busy}
          onConfirm={() => {
            const body = opening;
            write.send(
              BREACHES_API_PATH,
              body,
              (payload) =>
                `Breach case ${stamp(payload, "case_id")} was opened. Its clock starts at ` +
                `${when(stamp(payload, "clock_starts_at"))}.`,
              () => {
                setOpening(null);
                setForm(EMPTY_OPEN);
              },
            );
          }}
          onCancel={() => {
            setOpening(null);
          }}
        />
      )}
    </section>
  );
}

function Breaches({ answer, onDone }: { readonly answer: BreachesAnswer; readonly onDone: (sentence: string) => void }) {
  return (
    <>
      <section className="card">
        <h2>{BREACHES_HEADING}</h2>
        <p>{answer.closing}</p>
        {answer.cases.length === 0 ? <p className="note">{NO_CASES}</p> : null}
      </section>
      {answer.cases.map((one) => (
        <Case key={one.case_id} one={one} closing={answer.closing} onDone={onDone} />
      ))}
      <OpenCase onDone={onDone} />
    </>
  );
}

function ComplianceBody({ onDone }: { readonly onDone: (sentence: string) => void }) {
  const topics = useResource<TopicsAnswer>(TOPICS_API_PATH);
  const register = useResource<RegisterAnswer>(REGISTER_API_PATH);
  const breaches = useResource<BreachesAnswer>(BREACHES_API_PATH);

  const failure = topics.failure ?? register.failure ?? breaches.failure;
  if (failure) {
    return (
      <section className="card">
        <FailureNotice failure={failure} />
      </section>
    );
  }
  if (topics.data === null || register.data === null || breaches.data === null) {
    return (
      <p className="note" role="status">
        {READING_COMPLIANCE}
      </p>
    );
  }
  return (
    <>
      <Topics answer={topics.data} onDone={onDone} />
      <Register answer={register.data} />
      <Breaches answer={breaches.data} onDone={onDone} />
    </>
  );
}

export function Compliance() {
  // A counter rather than a boolean, so two writes in a row read everything twice. Never drawn.
  const [generation, setGeneration] = useState(0);
  const [done, setDone] = useState<string | null>(null);
  const onDone = useCallback((sentence: string) => {
    setDone(sentence);
    setGeneration((current) => current + 1);
  }, []);

  return (
    <article className="page">
      <p className="note">{COMPLIANCE_CRUMB}</p>
      <h1>{COMPLIANCE_HEADING}</h1>
      <p className="lede">{COMPLIANCE_LEDE}</p>
      {done === null ? null : (
        <p className="note" role="status">
          {done}
        </p>
      )}
      <ComplianceBody key={generation} onDone={onDone} />
    </article>
  );
}
