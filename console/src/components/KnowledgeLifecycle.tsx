/**
 * The Knowledge page's lifecycle cards: your tasks, the documents you look after, and solutions.
 *
 * K1 made a document addable from this page and nothing could be done to it afterwards. These three
 * cards are the acts the owner asked for, each drawn from what `brain.knowledge_lifecycle_routes`
 * answers and each sending one request the API decides.
 *
 * **Your knowledge tasks.** What the database opened for this person: a document of theirs that
 * fell due for review, a document handed to them, a promotion or a solution of theirs decided. A
 * review is closed by verifying the document, so only the other three offer "Mark as read".
 *
 * **Documents you look after.** Every live document this person stewards or may add beside, with
 * its review date, its verification as they may be told it, and their own promotion. Opening one
 * shows its history, each version to a reader whose own place admits it, the text of any version
 * they may read, and the four acts the API offers on it: verify with the next review date, add a
 * newer version, ask for it to be readable by the whole company, and hand it to another steward.
 * Adding a newer version and handing over are confirmed first, in the page's own sentence about what
 * each will do, because each replaces something that exists; verifying and asking are not, because
 * each adds a fact and ends nothing.
 *
 * **Solutions.** A solution found in a conversation is captured here for a department, and waits
 * for a named person who may add documents there; the capturer cannot decide their own. Approving
 * one asks for the review date its document will carry.
 *
 * **Nothing here decides who may see or do anything.** An act the API does not offer is not drawn,
 * and an act it refuses is its own sentence, drawn beside the form.
 *
 * Task ids: M7.4.4, M7.4.5, M7.4.6, M7.6.2, M7.7.2
 */

import { useState, type FormEvent } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { ConfirmAction } from "./ConfirmAction";
import { FailureNotice } from "../ui/FailureNotice";
import {
  dayOf,
  defaultReviewDay,
  instantOf,
  isAfterToday,
  itemPath,
  ITEMS_API_PATH,
  LIFECYCLE_FIELDS,
  passagesPath,
  promotionPath,
  promotionWords,
  reachWords,
  SOLUTIONS_API_PATH,
  solutionDecisionPath,
  solutionWords,
  stateWords,
  stewardPath,
  taskDonePath,
  TASKS_API_PATH,
  verificationPath,
  verificationWords,
  newVersionPath,
  type DocumentDetail,
  type DocumentRow,
  type LookedAfter,
  type Passages,
  type SolutionRow,
  type Solutions,
  type Tasks,
} from "../pages/knowledgeLifecycleQuery";

// ------------------------------------------------------------------ the words
export const TASKS_HEADING = "Your knowledge tasks";
export const NO_TASKS = "Nothing about knowledge is waiting for you.";
export const ASKING_FOR_TASKS = "Asking what is waiting for you.";
export const MARK_READ = "Mark as read";

export const LOOKED_AFTER_HEADING = "Documents you look after";
export const LOOKED_AFTER_LEDE =
  "Documents you steward, and documents in departments where you may add knowledge. Open one to " +
  "see its history, verify it, add a newer version, ask for it to be readable by the whole " +
  "company, or hand it to another steward.";
export const NONE_LOOKED_AFTER = "You look after no documents.";
export const MORE_LOOKED_AFTER =
  "You look after more documents than one reading covers; the list shows the first part by title.";
export const ASKING_FOR_DOCUMENTS = "Asking which documents you look after.";
export const OPEN = "Open";

export const HISTORY_HEADING = "History";
export const READ_VERSION = "Read this version";
export const NO_PASSAGES = "Nothing in this version is yours to read.";

export const VERIFY_HEADING = "Verify it";
export const VERIFY_LABEL = "Verify";
export const NEW_VERSION_HEADING = "Add a newer version";
export const NEW_VERSION_LABEL = "Add as the newer version";
export const PROPOSE_HEADING = "Ask for the whole company";
export const PROPOSE_LABEL = "Ask for approval";
export const HAND_OVER_HEADING = "Hand to another steward";
export const HAND_OVER_LABEL = "Hand over";
export const REVIEW_LABEL = "Next review by";
export const STEWARD_LABEL = "The person's id";
export const REASON_LABEL = "Why the whole company should read it";
export const FILE_LABEL = "Document";

/** The sentence a newer version is confirmed with. */
export const NEW_VERSION_CONSEQUENCE =
  "The newer version is added where this one sits, stewarded as it is, and answers use it from " +
  "now on. This version stays in the history, readable by the people who could read it, and is " +
  "no longer answered from.";

/** The sentence a hand-over is confirmed with. */
export const HAND_OVER_CONSEQUENCE =
  "They become its steward, are told so, and are the person asked when it falls due for review. " +
  "The change is recorded in the audit trail.";

export const LIFECYCLE_PROBLEMS = {
  review: "Choose the next review date.",
  reviewAhead: "The review date has to be after today.",
  file: "Choose the newer version's file.",
  reason: "Say why the whole company should read it.",
  steward: "Enter the id of the person to hand it to.",
  problem: "Say what the solution solved.",
  answer: "Say what the solution is.",
  department: "Choose the department it is for.",
} as const;

export const SOLUTIONS_HEADING = "Solutions";
export const SOLUTIONS_LEDE =
  "A solution found in a conversation becomes company knowledge only when somebody who may add " +
  "documents to its department approves it. You cannot approve your own.";
export const CAPTURE_HEADING = "Capture a solution";
export const CAPTURE_LABEL = "Capture";
export const CAPTURE_NOT_OFFERED = "Capturing a solution is not offered to you.";
export const PROBLEM_LABEL = "What it solved";
export const ANSWER_LABEL = "The solution";
export const CONVERSATION_LABEL = "Conversation reference (optional)";
export const DEPARTMENT_LABEL = "Department";
export const WAITING_HEADING = "Waiting for your decision";
export const NONE_WAITING = "No solution is waiting for your decision.";
export const YOURS_HEADING = "Solutions you captured";
export const NONE_YOURS = "You have captured no solutions.";
export const DECIDE_HEADING = "Decide this solution";
export const APPROVE_LABEL = "Approve";
export const REFUSE_LABEL = "Refuse";
export const ASKING_FOR_SOLUTIONS = "Asking which solutions are yours to see.";

// ------------------------------------------------------------------ the tasks
export function KnowledgeTasks({ version, onChanged }: { readonly version: number; readonly onChanged: () => void }) {
  const tasks = useResource<Tasks>(TASKS_API_PATH, version);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const markRead = (taskId: string) => {
    void (async () => {
      const result = await request<unknown>(taskDonePath(taskId), { method: "POST" });
      setFailure(result.ok ? null : result.failure);
      onChanged();
    })();
  };

  let inside;
  if (tasks.busy) {
    inside = (
      <p className="note" role="status">
        {ASKING_FOR_TASKS}
      </p>
    );
  } else if (tasks.failure !== null) {
    inside = <FailureNotice failure={tasks.failure} />;
  } else if (tasks.data === null || tasks.data.items.length === 0) {
    inside = <p className="note">{NO_TASKS}</p>;
  } else {
    inside = (
      <ul aria-label={TASKS_HEADING}>
        {tasks.data.items.map((one) => (
          <li key={one.task_id}>
            <p>{one.says}</p>
            {one.closable ? (
              <button type="button" className="button" onClick={() => markRead(one.task_id)}>
                {MARK_READ}
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    );
  }
  return (
    <section className="card">
      <h2>{TASKS_HEADING}</h2>
      {failure === null ? null : <FailureNotice failure={failure} />}
      {inside}
    </section>
  );
}

// ------------------------------------------------------------------ one document's acts
function ReviewDay({ value, onChange }: { readonly value: string; readonly onChange: (day: string) => void }) {
  return (
    <label className="control-label">
      {REVIEW_LABEL}{" "}
      <input
        className="form-control"
        type="date"
        name="review_by"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

/** What is wrong with a picked review day, or null. Said before anything is sent. */
function reviewProblem(day: string): string | null {
  if (day === "") {
    return LIFECYCLE_PROBLEMS.review;
  }
  return isAfterToday(day) ? null : LIFECYCLE_PROBLEMS.reviewAhead;
}

function Said({ problems }: { readonly problems: readonly string[] }) {
  return (
    <>
      {problems.map((one) => (
        <p key={one} className="note">
          {one}
        </p>
      ))}
    </>
  );
}

function VerifyForm({ itemId, onDone }: { readonly itemId: string; readonly onDone: () => void }) {
  const [day, setDay] = useState(defaultReviewDay());
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const problem = reviewProblem(day);
    setProblems(problem === null ? [] : [problem]);
    const instant = instantOf(day);
    if (problem !== null || instant === null) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(verificationPath(itemId), {
        method: "POST",
        body: { review_by: instant },
      });
      setBusy(false);
      setFailure(result.ok ? null : result.failure);
      if (result.ok) {
        onDone();
      }
    })();
  };

  return (
    <form className="form" aria-label={VERIFY_HEADING} onSubmit={onSubmit} noValidate>
      <h3>{VERIFY_HEADING}</h3>
      {failure === null ? null : <FailureNotice failure={failure} fields={LIFECYCLE_FIELDS} />}
      <ReviewDay value={day} onChange={setDay} />
      <Said problems={problems} />
      <div className="form-actions">
        <button type="submit" className="button" disabled={busy}>
          {VERIFY_LABEL}
        </button>
      </div>
    </form>
  );
}

function NewVersionForm({
  document,
  onDone,
}: {
  readonly document: DocumentRow;
  readonly onDone: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [day, setDay] = useState(defaultReviewDay());
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const found = [
      ...(file === null ? [LIFECYCLE_PROBLEMS.file] : []),
      ...[reviewProblem(day)].filter((one): one is string => one !== null),
    ];
    setProblems(found);
    setConfirming(found.length === 0);
  };

  const send = () => {
    const instant = instantOf(day);
    if (file === null || instant === null) {
      return;
    }
    setBusy(true);
    void (async () => {
      const lower = file.name.toLowerCase();
      const type = lower.endsWith(".pdf")
        ? "application/pdf"
        : lower.endsWith(".docx")
          ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          : lower.endsWith(".txt")
            ? "text/plain"
            : "text/markdown";
      const result = await request<unknown>(newVersionPath(document.item_id, instant), {
        method: "POST",
        file: { body: file, type, name: file.name },
      });
      setBusy(false);
      setConfirming(false);
      setFailure(result.ok ? null : result.failure);
      if (result.ok) {
        onDone();
      }
    })();
  };

  return (
    <>
      <form className="form" aria-label={NEW_VERSION_HEADING} onSubmit={onSubmit} noValidate>
        <h3>{NEW_VERSION_HEADING}</h3>
        {failure === null ? null : <FailureNotice failure={failure} fields={LIFECYCLE_FIELDS} />}
        <label className="control-label">
          {FILE_LABEL}{" "}
          <input
            className="form-control"
            type="file"
            name="file"
            accept=".md,.markdown,.txt,.pdf,.docx"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </label>
        <ReviewDay value={day} onChange={setDay} />
        <Said problems={problems} />
        <div className="form-actions">
          <button type="submit" className="button" disabled={busy}>
            {NEW_VERSION_LABEL}
          </button>
        </div>
      </form>
      {confirming ? (
        <ConfirmAction
          question={`Replace ${document.title} with ${file?.name ?? "the chosen file"}?`}
          consequence={NEW_VERSION_CONSEQUENCE}
          confirmLabel={NEW_VERSION_LABEL}
          cancelLabel="Keep the current version"
          busy={busy}
          onConfirm={send}
          onCancel={() => setConfirming(false)}
        />
      ) : null}
    </>
  );
}

function ProposeForm({
  itemId,
  waits,
  onDone,
}: {
  readonly itemId: string;
  readonly waits: string;
  readonly onDone: () => void;
}) {
  const [reason, setReason] = useState("");
  const [day, setDay] = useState(defaultReviewDay());
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const found = [
      ...(reason.trim() === "" ? [LIFECYCLE_PROBLEMS.reason] : []),
      ...[reviewProblem(day)].filter((one): one is string => one !== null),
    ];
    setProblems(found);
    const instant = instantOf(day);
    if (found.length > 0 || instant === null) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(promotionPath(itemId), {
        method: "POST",
        body: { review_by: instant, reason: reason.trim() },
      });
      setBusy(false);
      setFailure(result.ok ? null : result.failure);
      if (result.ok) {
        onDone();
      }
    })();
  };

  return (
    <form className="form" aria-label={PROPOSE_HEADING} onSubmit={onSubmit} noValidate>
      <h3>{PROPOSE_HEADING}</h3>
      <p className="note">{waits}</p>
      {failure === null ? null : <FailureNotice failure={failure} fields={LIFECYCLE_FIELDS} />}
      <label className="control-label">
        {REASON_LABEL}{" "}
        <textarea
          className="form-control"
          name="reason"
          value={reason}
          maxLength={500}
          onChange={(event) => setReason(event.target.value)}
        />
      </label>
      <ReviewDay value={day} onChange={setDay} />
      <Said problems={problems} />
      <div className="form-actions">
        <button type="submit" className="button" disabled={busy}>
          {PROPOSE_LABEL}
        </button>
      </div>
    </form>
  );
}

function HandOverForm({ document, onDone }: { readonly document: DocumentRow; readonly onDone: () => void }) {
  const [to, setTo] = useState("");
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const found = to.trim() === "" ? [LIFECYCLE_PROBLEMS.steward] : [];
    setProblems(found);
    setConfirming(found.length === 0);
  };

  const send = () => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(stewardPath(document.item_id), {
        method: "POST",
        body: { steward_id: to.trim() },
      });
      setBusy(false);
      setConfirming(false);
      setFailure(result.ok ? null : result.failure);
      if (result.ok) {
        onDone();
      }
    })();
  };

  return (
    <>
      <form className="form" aria-label={HAND_OVER_HEADING} onSubmit={onSubmit} noValidate>
        <h3>{HAND_OVER_HEADING}</h3>
        {failure === null ? null : <FailureNotice failure={failure} fields={LIFECYCLE_FIELDS} />}
        <label className="control-label">
          {STEWARD_LABEL}{" "}
          <input
            className="form-control"
            type="text"
            name="steward_id"
            value={to}
            maxLength={128}
            onChange={(event) => setTo(event.target.value)}
          />
        </label>
        <Said problems={problems} />
        <div className="form-actions">
          <button type="submit" className="button" disabled={busy}>
            {HAND_OVER_LABEL}
          </button>
        </div>
      </form>
      {confirming ? (
        <ConfirmAction
          question={`Hand ${document.title} to ${to.trim()}?`}
          consequence={HAND_OVER_CONSEQUENCE}
          confirmLabel={HAND_OVER_LABEL}
          cancelLabel="Keep the current steward"
          busy={busy}
          onConfirm={send}
          onCancel={() => setConfirming(false)}
        />
      ) : null}
    </>
  );
}

function VersionText({ itemId }: { readonly itemId: string }) {
  const text = useResource<Passages>(passagesPath(itemId));
  if (text.busy) {
    return (
      <p className="note" role="status">
        Loading.
      </p>
    );
  }
  if (text.failure !== null) {
    return <FailureNotice failure={text.failure} />;
  }
  if (text.data === null || text.data.passages.length === 0) {
    return <p className="note">{NO_PASSAGES}</p>;
  }
  return (
    <div className="card">
      <h4>{text.data.title}</h4>
      {text.data.passages.map((one) => (
        <p key={one.ordinal}>{one.text}</p>
      ))}
    </div>
  );
}

function DocumentPanel({ itemId, onChanged }: { readonly itemId: string; readonly onChanged: () => void }) {
  const [version, setVersion] = useState(0);
  const [reading, setReading] = useState<string | null>(null);
  const detail = useResource<DocumentDetail>(itemPath(itemId), version);
  const done = () => {
    setVersion((was) => was + 1);
    onChanged();
  };

  if (detail.busy) {
    return (
      <p className="note" role="status">
        Loading.
      </p>
    );
  }
  if (detail.failure !== null || detail.data === null) {
    return detail.failure === null ? null : <FailureNotice failure={detail.failure} />;
  }
  const { document, versions, offered } = detail.data;
  return (
    <section className="card" aria-label={document.title}>
      <h3>{document.title}</h3>
      <dl className="fields">
        <div className="fields__row">
          <dt>Type</dt>
          <dd>{document.kind_label}</dd>
        </div>
        <div className="fields__row">
          <dt>Visible to</dt>
          <dd>{reachWords(document.level, document.department)}</dd>
        </div>
        <div className="fields__row">
          <dt>Steward</dt>
          <dd>
            <code>{document.steward_id}</code>
          </dd>
        </div>
        <div className="fields__row">
          <dt>Verified</dt>
          <dd>{verificationWords(document)}</dd>
        </div>
        <div className="fields__row">
          <dt>Review by</dt>
          <dd>{dayOf(document.review_by)}</dd>
        </div>
        {document.solves ? (
          <div className="fields__row">
            <dt>Solves</dt>
            <dd>{document.solves}</dd>
          </div>
        ) : null}
        <div className="fields__row">
          <dt>Company-wide</dt>
          <dd>{promotionWords(document.promotion)}</dd>
        </div>
      </dl>

      <h4>{HISTORY_HEADING}</h4>
      <ul aria-label={HISTORY_HEADING}>
        {versions.map((one) => (
          <li key={one.item_id}>
            <span>
              {one.title} ({stateWords(one.state)}, added {dayOf(one.added_at, "on an unrecorded day")})
            </span>{" "}
            {one.readable ? (
              <button type="button" className="button" onClick={() => setReading(one.item_id)}>
                {READ_VERSION}
              </button>
            ) : null}
          </li>
        ))}
      </ul>
      {reading === null ? null : <VersionText itemId={reading} />}

      {offered.verify ? <VerifyForm itemId={document.item_id} onDone={done} /> : null}
      {offered.new_version ? <NewVersionForm document={document} onDone={done} /> : null}
      {offered.propose ? (
        <ProposeForm itemId={document.item_id} waits={detail.data.promotion_waits} onDone={done} />
      ) : null}
      {offered.hand_over ? <HandOverForm document={document} onDone={done} /> : null}
    </section>
  );
}

// ------------------------------------------------------------------ the documents
export function LookedAfterCard({ version, onChanged }: { readonly version: number; readonly onChanged: () => void }) {
  const documents = useResource<LookedAfter>(ITEMS_API_PATH, version);
  const [open, setOpen] = useState<string | null>(null);

  let inside;
  if (documents.busy) {
    inside = (
      <p className="note" role="status">
        {ASKING_FOR_DOCUMENTS}
      </p>
    );
  } else if (documents.failure !== null) {
    inside = <FailureNotice failure={documents.failure} />;
  } else if (documents.data === null || documents.data.items.length === 0) {
    inside = <p className="note">{NONE_LOOKED_AFTER}</p>;
  } else {
    inside = (
      <>
        <div className="grid__scroll">
          <table className="grid__table">
            <caption className="grid__caption">{LOOKED_AFTER_HEADING}</caption>
            <thead>
              <tr>
                <th scope="col">Document</th>
                <th scope="col">Type</th>
                <th scope="col">Visible to</th>
                <th scope="col">Verified</th>
                <th scope="col">Review by</th>
                <th scope="col">Company-wide</th>
                <th scope="col">Open</th>
              </tr>
            </thead>
            <tbody>
              {documents.data.items.map((one) => (
                <tr key={one.item_id}>
                  <td>{one.title}</td>
                  <td>{one.kind_label}</td>
                  <td>{reachWords(one.level, one.department)}</td>
                  <td>{verificationWords(one)}</td>
                  <td>
                    {dayOf(one.review_by)}
                    {one.due ? " (due)" : ""}
                  </td>
                  <td>{promotionWords(one.promotion)}</td>
                  <td>
                    <button
                      type="button"
                      className="button"
                      aria-label={`${OPEN} ${one.title}`}
                      onClick={() => setOpen(one.item_id)}
                    >
                      {OPEN}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {documents.data.truncated ? <p className="note">{MORE_LOOKED_AFTER}</p> : null}
        {open === null ? null : <DocumentPanel key={open} itemId={open} onChanged={onChanged} />}
      </>
    );
  }
  return (
    <section className="card">
      <h2>{LOOKED_AFTER_HEADING}</h2>
      <p className="note">{LOOKED_AFTER_LEDE}</p>
      {inside}
    </section>
  );
}

// ------------------------------------------------------------------ solutions
function CaptureForm({ departments, onDone }: { readonly departments: readonly string[]; readonly onDone: () => void }) {
  const [problem, setProblem] = useState("");
  const [answer, setAnswer] = useState("");
  const [department, setDepartment] = useState(departments.length === 1 ? (departments[0] ?? "") : "");
  const [conversation, setConversation] = useState("");
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const found = [
      ...(problem.trim() === "" ? [LIFECYCLE_PROBLEMS.problem] : []),
      ...(answer.trim() === "" ? [LIFECYCLE_PROBLEMS.answer] : []),
      ...(department === "" ? [LIFECYCLE_PROBLEMS.department] : []),
    ];
    setProblems(found);
    if (found.length > 0) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(SOLUTIONS_API_PATH, {
        method: "POST",
        body: {
          problem: problem.trim(),
          answer: answer.trim(),
          department,
          conversation_ref: conversation.trim(),
        },
      });
      setBusy(false);
      setFailure(result.ok ? null : result.failure);
      if (result.ok) {
        setProblem("");
        setAnswer("");
        setConversation("");
        onDone();
      }
    })();
  };

  return (
    <form className="form" aria-label={CAPTURE_HEADING} onSubmit={onSubmit} noValidate>
      <h3>{CAPTURE_HEADING}</h3>
      {failure === null ? null : <FailureNotice failure={failure} fields={LIFECYCLE_FIELDS} />}
      <label className="control-label">
        {PROBLEM_LABEL}{" "}
        <textarea
          className="form-control"
          name="problem"
          value={problem}
          maxLength={2000}
          onChange={(event) => setProblem(event.target.value)}
        />
      </label>
      <label className="control-label">
        {ANSWER_LABEL}{" "}
        <textarea
          className="form-control"
          name="answer"
          value={answer}
          maxLength={20000}
          onChange={(event) => setAnswer(event.target.value)}
        />
      </label>
      <label className="control-label">
        {DEPARTMENT_LABEL}{" "}
        <select
          className="form-control"
          name="department"
          value={department}
          onChange={(event) => setDepartment(event.target.value)}
        >
          <option value="">Choose one</option>
          {departments.map((one) => (
            <option key={one} value={one}>
              {one}
            </option>
          ))}
        </select>
      </label>
      <label className="control-label">
        {CONVERSATION_LABEL}{" "}
        <input
          className="form-control"
          type="text"
          name="conversation_ref"
          value={conversation}
          maxLength={128}
          onChange={(event) => setConversation(event.target.value)}
        />
      </label>
      <Said problems={problems} />
      <div className="form-actions">
        <button type="submit" className="button" disabled={busy}>
          {CAPTURE_LABEL}
        </button>
      </div>
    </form>
  );
}

function SolutionFacts({ one }: { readonly one: SolutionRow }) {
  return (
    <dl className="fields">
      <div className="fields__row">
        <dt>{PROBLEM_LABEL}</dt>
        <dd>{one.problem}</dd>
      </div>
      <div className="fields__row">
        <dt>{ANSWER_LABEL}</dt>
        <dd>{one.answer}</dd>
      </div>
      <div className="fields__row">
        <dt>{DEPARTMENT_LABEL}</dt>
        <dd>{one.department}</dd>
      </div>
      <div className="fields__row">
        <dt>Captured by</dt>
        <dd>
          <code>{one.captured_by}</code> on {dayOf(one.captured_at)}
        </dd>
      </div>
      <div className="fields__row">
        <dt>State</dt>
        <dd>
          {solutionWords(one.state)}
          {one.decided_by ? `, decided by ${one.decided_by} on ${dayOf(one.decided_at)}` : ""}
        </dd>
      </div>
    </dl>
  );
}

function Decide({ one, onDone }: { readonly one: SolutionRow; readonly onDone: () => void }) {
  const [day, setDay] = useState(defaultReviewDay());
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);

  const decide = (verdict: "approved" | "rejected", reviewBy: string | null) => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(solutionDecisionPath(one.solution_id), {
        method: "POST",
        body: { verdict, review_by: reviewBy },
      });
      setBusy(false);
      setFailure(result.ok ? null : result.failure);
      if (result.ok) {
        onDone();
      }
    })();
  };

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const problem = reviewProblem(day);
    setProblems(problem === null ? [] : [problem]);
    const instant = instantOf(day);
    if (problem !== null || instant === null) {
      return;
    }
    decide("approved", instant);
  };

  return (
    <form className="form" aria-label={DECIDE_HEADING} onSubmit={onSubmit} noValidate>
      {failure === null ? null : <FailureNotice failure={failure} fields={LIFECYCLE_FIELDS} />}
      <ReviewDay value={day} onChange={setDay} />
      <Said problems={problems} />
      <div className="form-actions">
        <button type="submit" className="button" disabled={busy}>
          {APPROVE_LABEL}
        </button>
        <button type="button" className="button" disabled={busy} onClick={() => decide("rejected", null)}>
          {REFUSE_LABEL}
        </button>
      </div>
    </form>
  );
}

export function SolutionsCard({ version, onChanged }: { readonly version: number; readonly onChanged: () => void }) {
  const solutions = useResource<Solutions>(SOLUTIONS_API_PATH, version);

  let inside;
  if (solutions.busy) {
    inside = (
      <p className="note" role="status">
        {ASKING_FOR_SOLUTIONS}
      </p>
    );
  } else if (solutions.failure !== null || solutions.data === null) {
    inside = solutions.failure === null ? null : <FailureNotice failure={solutions.failure} />;
  } else {
    const { waiting, yours, departments } = solutions.data;
    inside = (
      <>
        {departments.length === 0 ? (
          <p className="note">{CAPTURE_NOT_OFFERED}</p>
        ) : (
          <CaptureForm departments={departments} onDone={onChanged} />
        )}
        <h3>{WAITING_HEADING}</h3>
        {waiting.length === 0 ? (
          <p className="note">{NONE_WAITING}</p>
        ) : (
          <ul aria-label={WAITING_HEADING}>
            {waiting.map((one) => (
              <li key={one.solution_id}>
                <SolutionFacts one={one} />
                <Decide one={one} onDone={onChanged} />
              </li>
            ))}
          </ul>
        )}
        <h3>{YOURS_HEADING}</h3>
        {yours.length === 0 ? (
          <p className="note">{NONE_YOURS}</p>
        ) : (
          <ul aria-label={YOURS_HEADING}>
            {yours.map((one) => (
              <li key={one.solution_id}>
                <SolutionFacts one={one} />
              </li>
            ))}
          </ul>
        )}
      </>
    );
  }
  return (
    <section className="card">
      <h2>{SOLUTIONS_HEADING}</h2>
      <p className="note">{SOLUTIONS_LEDE}</p>
      {inside}
    </section>
  );
}
