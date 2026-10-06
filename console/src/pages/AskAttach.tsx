/**
 * The control on Ask that attaches a file to the conversation (M12.3.6).
 *
 * **Offered only to somebody who may add a document at their own level.** The upload options say
 * so (`personal`), and somebody they do not offer it to sees no control rather than one that
 * fails. The file types and their limits are the options' own, so the control refuses what the
 * route would refuse before anything is sent.
 *
 * **The kind is chosen by the person, as on the Knowledge page.** The owner's rule is that the
 * person adding a document says what kind it is and nothing guesses (`brain.knowledge.kinds`), so
 * the control offers the same list, the first chosen.
 *
 * **Attached files are listed by their titles above the question, until a new conversation.**
 * Asking then continues the thread the attachment named, which is what reads the file into the
 * answer. See `askAttachQuery.ts`.
 *
 * Task ids: M12.3.6
 */

import { useEffect, useState, type FormEvent } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { FailureNotice } from "../ui/FailureNotice";
import { ATTACHMENTS_API_PATH, attachBody, readAttached } from "./askAttachQuery";
import {
  acceptOf,
  readUploaded,
  readUploadOptions,
  typeOf,
  UPLOAD_OPTIONS_API_PATH,
  uploadPath,
  type UploadOptions,
} from "./knowledgeQuery";

export const ATTACH_HEADING = "Attach a file to this conversation";
export const ATTACH_FILE_LABEL = "File";
export const ATTACH_KIND_LABEL = "What kind of document it is";
export const ATTACH_LABEL = "Attach";
export const ATTACHING = "Attaching the file.";
export const ATTACHED_LABEL = "Attached to this conversation";
export const CHOOSE_A_FILE = "Choose a file to attach.";
export const NOT_A_TYPE_OFFERED = "This kind of file cannot be attached here.";
export const TOO_LARGE = "This file is larger than files of its kind may be.";

const FILE_FIELD_ID = "ask-attach-file";
const KIND_FIELD_ID = "ask-attach-kind";

export function AskAttach({
  thread,
  disabled,
  onAttached,
}: {
  readonly thread: string;
  readonly disabled: boolean;
  readonly onAttached: (threadId: string, title: string) => void;
}): React.JSX.Element | null {
  const [options, setOptions] = useState<UploadOptions | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState("");
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  useEffect(() => {
    let live = true;
    void (async () => {
      const answered = await request<unknown>(UPLOAD_OPTIONS_API_PATH);
      if (!live || !answered.ok) {
        return;
      }
      const read = readUploadOptions(answered.data);
      setOptions(read);
      setKind(read?.kinds[0]?.value ?? "");
    })();
    return () => {
      live = false;
    };
  }, []);

  if (options === null || !options.personal) {
    return null;
  }

  const onSubmit = (submitted: FormEvent<HTMLFormElement>) => {
    submitted.preventDefault();
    const type = file === null ? null : typeOf(file.name, options.types);
    const found =
      file === null
        ? CHOOSE_A_FILE
        : type === null
          ? NOT_A_TYPE_OFFERED
          : file.size > type.maxBytes
            ? TOO_LARGE
            : "";
    setProblem(found);
    if (found !== "" || file === null || type === null) {
      return;
    }
    setBusy(true);
    setFailure(null);
    void (async () => {
      const added = await request<unknown>(uploadPath(kind, "personal", ""), {
        method: "POST",
        file: { body: file, type: type.mediaType, name: file.name },
      });
      const uploaded = added.ok ? readUploaded(added.data) : null;
      if (!added.ok || uploaded === null) {
        setBusy(false);
        setFailure(added.ok ? null : added.failure);
        return;
      }
      const named = await request<unknown>(ATTACHMENTS_API_PATH, {
        method: "POST",
        body: attachBody(thread, uploaded.itemId),
      });
      setBusy(false);
      const kept = named.ok ? readAttached(named.data) : null;
      if (!named.ok || kept === null) {
        setFailure(named.ok ? null : named.failure);
        return;
      }
      setFile(null);
      onAttached(kept.threadId, uploaded.title);
    })();
  };

  return (
    <form className="ask__attach" aria-label={ATTACH_HEADING} onSubmit={onSubmit} noValidate>
      <h2 className="ask__attach-heading">{ATTACH_HEADING}</h2>
      {failure === null ? null : <FailureNotice failure={failure} fields={["file", "kind"]} />}
      {busy ? (
        <p className="note" role="status">
          {ATTACHING}
        </p>
      ) : null}
      <label className="ask__label" htmlFor={FILE_FIELD_ID}>
        {ATTACH_FILE_LABEL}
      </label>
      <input
        id={FILE_FIELD_ID}
        type="file"
        name="file"
        className="form-control"
        accept={acceptOf(options.types)}
        disabled={disabled || busy}
        aria-invalid={problem === "" ? undefined : true}
        aria-describedby={problem === "" ? undefined : `${FILE_FIELD_ID}-problem`}
        onChange={(changed) => {
          setFile(changed.target.files?.[0] ?? null);
          setProblem("");
        }}
      />
      {problem === "" ? null : (
        <p id={`${FILE_FIELD_ID}-problem`} className="field-problem">
          {problem}
        </p>
      )}
      <label className="ask__label" htmlFor={KIND_FIELD_ID}>
        {ATTACH_KIND_LABEL}
      </label>
      <select
        id={KIND_FIELD_ID}
        className="form-control"
        value={kind}
        disabled={disabled || busy}
        onChange={(changed) => setKind(changed.target.value)}
      >
        {options.kinds.map((one) => (
          <option key={one.value} value={one.value}>
            {one.label}
          </option>
        ))}
      </select>
      <div className="form-actions">
        <button type="submit" className="button" disabled={disabled || busy}>
          {ATTACH_LABEL}
        </button>
      </div>
    </form>
  );
}

/** The files attached to the conversation, by title. Nothing when there are none. */
export function AttachedFiles({ titles }: { readonly titles: readonly string[] }): React.JSX.Element | null {
  if (titles.length === 0) {
    return null;
  }
  return (
    <section className="ask__attached" aria-label={ATTACHED_LABEL}>
      <h2 className="ask__attach-heading">{ATTACHED_LABEL}</h2>
      <ul>
        {titles.map((title, index) => (
          <li key={`${String(index)}-${title}`}>{title}</li>
        ))}
      </ul>
    </section>
  );
}
