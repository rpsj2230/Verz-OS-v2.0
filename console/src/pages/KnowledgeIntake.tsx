/**
 * Two cards beside Add a document: a web page added by its link, and many documents at once.
 *
 * **Add a web page by its link** (M7.1.2). An administrator pastes an address and chooses the kind
 * and the department, as for a file. The page is fetched once, now, through the API's address check,
 * kept as the company's own document with its address as its first line, and answered from like an
 * uploaded file. It is not a connector: nothing re-reads the site. The answer is the API's own
 * sentence, whether it was added or why not, a page that needs a browser to show its words included.
 *
 * **Add many documents** (M7.1.5, M22.2.4). Each chosen file is judged here against what the API
 * offered, then sent on its own to the queued route, which checks it at the door and hands it to the
 * background worker; the worker reads the files one at a time, so questions asked meanwhile are not
 * slowed. A full queue answers 429 and the rest are not sent, with a sentence saying so. What became
 * of each queued file is asked of its ticket when the person presses Check again, because the worker
 * reads it after the request has ended; a refusal names its cause in the API's words.
 *
 * Both are drawn from `GET /knowledge/uploads/options`, the answer the Add a document card is drawn
 * from, so they offer exactly the kinds, departments and levels that card does. Somebody offered
 * nothing is shown nothing here; the Add a document card already says so in one sentence.
 *
 * Task ids: M7.1.2, M7.1.5, M22.2.4
 */

import { useState, type FormEvent } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { FailureNotice } from "../ui/FailureNotice";
import {
  acceptOf,
  addedSentence,
  readUploaded,
  readUploadOptions,
  typeOf,
  UPLOAD_OPTIONS_API_PATH,
  type UploadLevel,
  type UploadOptions,
} from "./knowledgeQuery";
import {
  LINK_PROBLEMS,
  LINKS_API_PATH,
  linkBody,
  linkProblems,
  queuedPath,
  queuedTicketPath,
  readQueued,
  type LinkDraft,
  type LinkProblem,
  type Queued,
} from "./knowledgeIntakeQuery";

export const LINK_HEADING = "Add a web page by its link";
export const LINK_LEDE =
  "The page is fetched once, now, and kept as your company's own document for one department or " +
  "for you only, with its address as its first line. Nothing re-reads the site afterwards; add the " +
  "link again to take a newer copy.";
export const LINK_LABEL = "Address";
export const ADD_LINK = "Add this page";
export const FETCHING = "Fetching and reading the page.";

export const BULK_HEADING = "Add many documents";
export const BULK_LEDE =
  "Each file is checked here and read by the background worker one at a time, so questions asked " +
  "meanwhile are not slowed. Files larger than an ordinary document are added one at a time above.";
export const FILES_LABEL = "Documents";
export const QUEUE_FILES = "Queue these documents";
export const CHECK_AGAIN = "Check again";
export const QUEUEING = "Sending the files to the queue.";

/** Said beside the file input when nothing is chosen. */
export const NO_FILES = "Choose the documents to add.";

/** Said for a file this form can already tell the API would refuse, before it is sent. */
export const NOT_SENT_TYPE = "not sent: it is not a plain text, Markdown, PDF or Word document.";
export const NOT_SENT_SIZE = "not sent: it is larger than this install accepts for its type.";

/** Said for the files left once the queue said it was full. */
export const NOT_SENT_QUEUE_FULL = "not sent, because the queue was full. Send it again later.";

const FIELDS = ["url", "file", "kind", "level", "department"];

/** One file's line in the bulk card: what the API said about it, or why it was not sent. */
interface Line {
  readonly name: string;
  readonly said: string;
  readonly queued: Queued | null;
}

function levelsOf(options: UploadOptions): UploadLevel[] {
  return [
    ...(options.departments.length > 0 ? (["department"] as const) : []),
    ...(options.personal ? (["personal"] as const) : []),
  ];
}

/** The kind, the level and the department, shared by both cards and drawn from the options. */
function Placement({
  options,
  draft,
  onChange,
  problems,
}: {
  readonly options: UploadOptions;
  readonly draft: { readonly kind: string; readonly level: UploadLevel; readonly department: string };
  readonly onChange: (next: { kind: string; level: UploadLevel; department: string }) => void;
  readonly problems: readonly string[];
}) {
  const levels = levelsOf(options);
  return (
    <>
      <label className="control-label">
        Kind{" "}
        <select
          className="form-control"
          name="kind"
          value={draft.kind}
          onChange={(event) => onChange({ ...draft, kind: event.target.value })}
        >
          <option value="">Choose one</option>
          {options.kinds.map((one) => (
            <option key={one.value} value={one.value}>
              {one.label}
            </option>
          ))}
        </select>
      </label>
      {problems.includes("kind") ? <p className="note">{LINK_PROBLEMS.kind}</p> : null}
      <label className="control-label">
        Visible to{" "}
        <select
          className="form-control"
          name="level"
          value={draft.level}
          onChange={(event) =>
            onChange({ ...draft, level: event.target.value === "personal" ? "personal" : "department" })
          }
        >
          {levels.map((one) => (
            <option key={one} value={one}>
              {one === "department" ? "One department" : "You only"}
            </option>
          ))}
        </select>
      </label>
      {draft.level === "department" ? (
        <label className="control-label">
          Department{" "}
          <select
            className="form-control"
            name="department"
            value={draft.department}
            onChange={(event) => onChange({ ...draft, department: event.target.value })}
          >
            <option value="">Choose one</option>
            {options.departments.map((one) => (
              <option key={one} value={one}>
                {one}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {problems.includes("department") ? <p className="note">{LINK_PROBLEMS.department}</p> : null}
    </>
  );
}

function firstPlace(options: UploadOptions): { kind: string; level: UploadLevel; department: string } {
  return {
    kind: "",
    level: levelsOf(options)[0] ?? "department",
    department: options.departments.length === 1 ? (options.departments[0] ?? "") : "",
  };
}

// ------------------------------------------------------------------ a link (M7.1.2)
function LinkForm({ options, onAdded }: { readonly options: UploadOptions; readonly onAdded: () => void }) {
  const [draft, setDraft] = useState<LinkDraft>({ url: "", ...firstPlace(options) });
  const [problems, setProblems] = useState<readonly LinkProblem[]>([]);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [said, setSaid] = useState("");

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const found = linkProblems(draft);
    setProblems(found);
    setSaid("");
    if (found.length > 0) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(LINKS_API_PATH, { method: "POST", body: linkBody(draft) });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      const added = readUploaded(result.data);
      setSaid(added === null ? "" : addedSentence(added));
      onAdded();
    })();
  };

  return (
    <>
      {failure === null ? null : <FailureNotice failure={failure} fields={FIELDS} />}
      {said === "" ? null : (
        <p className="note" role="status">
          {said}
        </p>
      )}
      {busy ? (
        <p className="note" role="status">
          {FETCHING}
        </p>
      ) : null}
      <form className="form" aria-label={LINK_HEADING} onSubmit={onSubmit} noValidate>
        <label className="control-label">
          {LINK_LABEL}{" "}
          <input
            className="form-control"
            type="url"
            name="url"
            value={draft.url}
            placeholder="https://"
            onChange={(event) => setDraft({ ...draft, url: event.target.value })}
          />
        </label>
        {problems.includes("url") ? <p className="note">{LINK_PROBLEMS.url}</p> : null}
        <Placement
          options={options}
          draft={draft}
          problems={problems}
          onChange={(next) => setDraft({ ...draft, ...next })}
        />
        <p className="note">Checked before it is read by the {options.checkedBy}.</p>
        <div className="form-actions">
          <button type="submit" className="button" disabled={busy}>
            {ADD_LINK}
          </button>
        </div>
      </form>
    </>
  );
}

// ------------------------------------------------------------------ many files (M7.1.5)
function BulkForm({ options, onAdded }: { readonly options: UploadOptions; readonly onAdded: () => void }) {
  const [files, setFiles] = useState<readonly File[]>([]);
  const [place, setPlace] = useState(firstPlace(options));
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [busy, setBusy] = useState(false);
  const [lines, setLines] = useState<readonly Line[]>([]);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const found = [
      ...(files.length === 0 ? ["file"] : []),
      ...(place.kind === "" ? ["kind"] : []),
      ...(place.level === "department" && place.department === "" ? ["department"] : []),
    ];
    setProblems(found);
    if (found.length > 0) {
      return;
    }
    setBusy(true);
    void (async () => {
      const told: Line[] = [];
      let full = false;
      for (const file of files) {
        const type = typeOf(file.name, options.types);
        if (full) {
          told.push({ name: file.name, said: `${file.name}: ${NOT_SENT_QUEUE_FULL}`, queued: null });
        } else if (type === null) {
          told.push({ name: file.name, said: `${file.name}: ${NOT_SENT_TYPE}`, queued: null });
        } else if (file.size > type.maxBytes) {
          told.push({ name: file.name, said: `${file.name}: ${NOT_SENT_SIZE}`, queued: null });
        } else {
          const result = await request<unknown>(queuedPath(place.kind, place.level, place.department), {
            method: "POST",
            file: { body: file, type: type.mediaType, name: file.name },
          });
          if (result.ok) {
            const queued = readQueued(result.data);
            told.push({ name: file.name, said: queued?.said ?? file.name, queued });
          } else {
            full = result.failure.status === 429;
            told.push({ name: file.name, said: `${file.name}: ${result.failure.message}`, queued: null });
          }
        }
        setLines([...told]);
      }
      setBusy(false);
    })();
  };

  const checkAgain = () => {
    void (async () => {
      const next: Line[] = [];
      let added = false;
      for (const line of lines) {
        if (line.queued === null || line.queued.state !== "queued") {
          next.push(line);
          continue;
        }
        const result = await request<unknown>(queuedTicketPath(line.queued.ticket));
        const queued = result.ok ? readQueued(result.data) : null;
        added = added || queued?.state === "added";
        next.push(queued === null ? line : { name: line.name, said: queued.said, queued });
      }
      setLines(next);
      if (added) {
        onAdded();
      }
    })();
  };

  const waiting = lines.some((line) => line.queued?.state === "queued");
  return (
    <>
      {busy ? (
        <p className="note" role="status">
          {QUEUEING}
        </p>
      ) : null}
      {lines.length === 0 ? null : (
        <ul className="list" aria-label="What became of each document">
          {lines.map((line, index) => (
            <li key={`${String(index)}-${line.name}`}>{line.said}</li>
          ))}
        </ul>
      )}
      {waiting && !busy ? (
        <div className="form-actions">
          <button type="button" className="button" onClick={checkAgain}>
            {CHECK_AGAIN}
          </button>
        </div>
      ) : null}
      <form className="form" aria-label={BULK_HEADING} onSubmit={onSubmit} noValidate>
        <label className="control-label">
          {FILES_LABEL}{" "}
          <input
            className="form-control"
            type="file"
            name="files"
            multiple
            accept={acceptOf(options.types)}
            onChange={(event) => setFiles([...(event.target.files ?? [])])}
          />
        </label>
        {problems.includes("file") ? <p className="note">{NO_FILES}</p> : null}
        <Placement options={options} draft={place} problems={problems} onChange={setPlace} />
        <p className="note">Checked before it is read by the {options.checkedBy}.</p>
        <div className="form-actions">
          <button type="submit" className="button" disabled={busy}>
            {QUEUE_FILES}
          </button>
        </div>
      </form>
    </>
  );
}

/** The two cards, or nothing for somebody who may add nothing, which the upload card says. */
export function KnowledgeIntake({ onAdded }: { readonly onAdded: () => void }) {
  const offered = useResource<unknown>(UPLOAD_OPTIONS_API_PATH);
  if (offered.busy) {
    return null;
  }
  if (offered.failure !== null) {
    return offered.failure.status === 404 && !offered.failure.secondFactorNeeded ? null : (
      <FailureNotice failure={offered.failure} />
    );
  }
  const options = readUploadOptions(offered.data);
  if (options === null || levelsOf(options).length === 0) {
    return null;
  }
  return (
    <>
      <section className="card">
        <h2>{LINK_HEADING}</h2>
        <p className="note">{LINK_LEDE}</p>
        <LinkForm options={options} onAdded={onAdded} />
      </section>
      <section className="card">
        <h2>{BULK_HEADING}</h2>
        <p className="note">{BULK_LEDE}</p>
        <BulkForm options={options} onAdded={onAdded} />
      </section>
    </>
  );
}
