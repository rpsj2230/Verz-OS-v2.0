/**
 * Adding documents: one file, a web page by its link, or many files for the background worker. Each
 * is drawn in a drawer from the Knowledge list's Add menu (M7.6.3, M7.1.2, M7.1.5).
 *
 * **Drawn only from what the API offered.** The types, the departments and whether a person may add
 * for themselves come from `GET /knowledge/uploads/options`; a file this form can tell will be
 * refused is said beside its field and not sent, and a refusal the API makes is its own sentence.
 * Adding ends nothing, so nothing here asks to be confirmed (`tests/destructive-confirmed.test.ts`).
 *
 * **A spreadsheet chosen as a document is offered to Classification** (M7.7.3), by the endings the
 * options name, beside the field and with a link there, and is not sent; the API makes the same
 * offer by name and declared type for anything that reaches it.
 *
 * Task ids: M7.1.2, M7.1.5, M7.6.3, M27.16.1, M7.7.3
 */

import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { FailureNotice } from "../../ui/FailureNotice";
import {
  LINK_PROBLEMS,
  LINKS_API_PATH,
  linkBody,
  linkProblems,
  queuedPath,
  queuedTicketPath,
  readQueued,
  type LinkProblem,
  type Queued,
} from "../knowledgeIntakeQuery";
import { CLASSIFICATION_PATH } from "../classificationQuery";
import {
  acceptOf,
  addedSentence,
  isOfferedAsTable,
  readUploaded,
  typeOf,
  uploadPath,
  type UploadLevel,
  type UploadOptions,
} from "../knowledgeQuery";
import {
  acceptsWords,
  ADD_FILE,
  ADD_LINK,
  ADDING,
  ADD_IT_ON_CLASSIFICATION,
  ADDRESS_HINT,
  ADDRESS_LABEL,
  CHECK_AGAIN,
  DEPARTMENT_LABEL,
  FETCHING,
  Field,
  FILE_LABEL,
  FILES_LABEL,
  FORM,
  KIND_LABEL,
  LEVEL_LABEL,
  NOT_SENT_QUEUE_FULL,
  NOT_SENT_SIZE,
  NOT_SENT_TABLE,
  NOT_SENT_TYPE,
  OFFERED_AS_A_TABLE,
  PROBLEMS,
  QUEUE_FILES,
  QUEUEING,
  SELECT,
  Status,
  Submit,
} from "./formParts";

export function levelsOf(options: UploadOptions): UploadLevel[] {
  return [
    ...(options.departments.length > 0 ? (["department"] as const) : []),
    ...(options.personal ? (["personal"] as const) : []),
  ];
}

interface Place {
  readonly kind: string;
  readonly level: UploadLevel;
  readonly department: string;
}

function firstPlace(options: UploadOptions): Place {
  return {
    kind: "",
    level: levelsOf(options)[0] ?? "department",
    department: options.departments.length === 1 ? (options.departments[0] ?? "") : "",
  };
}

function placeProblems(place: Place): string[] {
  return [
    ...(place.kind === "" ? [PROBLEMS.kind] : []),
    ...(place.level === "department" && place.department === "" ? [PROBLEMS.department] : []),
  ];
}

/** The type, the level and the department, drawn from the options. */
function PlaceFields({
  options,
  place,
  onChange,
  problems,
}: {
  readonly options: UploadOptions;
  readonly place: Place;
  readonly onChange: (next: Place) => void;
  readonly problems: readonly string[];
}) {
  const levels = levelsOf(options);
  return (
    <>
      <Field label={KIND_LABEL} problems={problems.filter((one) => one === PROBLEMS.kind)}>
        {(id) => (
          <select
            id={id}
            name="kind"
            className={SELECT}
            value={place.kind}
            onChange={(event) => {
              onChange({ ...place, kind: event.target.value });
            }}
          >
            <option value="">Choose one</option>
            {options.kinds.map((one) => (
              <option key={one.value} value={one.value}>
                {one.label}
              </option>
            ))}
          </select>
        )}
      </Field>
      <Field label={LEVEL_LABEL} hint="Making a document readable by the whole company is asked for afterwards, and approved by somebody else.">
        {(id, describedBy) => (
          <select
            id={id}
            name="level"
            className={SELECT}
            aria-describedby={describedBy}
            value={place.level}
            onChange={(event) => {
              onChange({ ...place, level: event.target.value === "personal" ? "personal" : "department" });
            }}
          >
            {levels.map((one) => (
              <option key={one} value={one}>
                {one === "department" ? "One department" : "You only"}
              </option>
            ))}
          </select>
        )}
      </Field>
      {place.level === "department" ? (
        <Field label={DEPARTMENT_LABEL} problems={problems.filter((one) => one === PROBLEMS.department)}>
          {(id) => (
            <select
              id={id}
              name="department"
              className={SELECT}
              value={place.department}
              onChange={(event) => {
                onChange({ ...place, department: event.target.value });
              }}
            >
              <option value="">Choose one</option>
              {options.departments.map((one) => (
                <option key={one} value={one}>
                  {one}
                </option>
              ))}
            </select>
          )}
        </Field>
      ) : null}
    </>
  );
}

// ------------------------------------------------------------------ adding (K1, K3)
/** Upload one file (M7.6.3). */
export function AddFileForm({ options, onAdded }: { readonly options: UploadOptions; readonly onAdded: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [place, setPlace] = useState<Place>(firstPlace(options));
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [said, setSaid] = useState("");

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const type = file === null ? null : typeOf(file.name, options.types);
    const table = file !== null && isOfferedAsTable(file.name, options);
    const found = [
      ...(file === null
        ? [PROBLEMS.file]
        : table
          ? [OFFERED_AS_A_TABLE]
          : type === null
            ? [PROBLEMS.type]
            : file.size > type.maxBytes
              ? [PROBLEMS.size]
              : []),
      ...placeProblems(place),
    ];
    setProblems(found);
    setSaid("");
    if (found.length > 0 || file === null || type === null) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(uploadPath(place.kind, place.level, place.department), {
        method: "POST",
        file: { body: file, type: type.mediaType, name: file.name },
      });
      setBusy(false);
      setFailure(result.ok ? null : result.failure);
      if (result.ok) {
        const added = readUploaded(result.data);
        setSaid(added === null ? "" : addedSentence(added));
        onAdded();
      }
    })();
  };

  return (
    <form className={FORM} aria-label="Upload a file" onSubmit={onSubmit} noValidate>
      {failure === null ? null : <FailureNotice failure={failure} fields={["file", "kind", "level", "department"]} />}
      {said === "" ? null : <Status>{said}</Status>}
      {busy ? <Status>{ADDING}</Status> : null}
      <Field
        label={FILE_LABEL}
        hint={acceptsWords(options.types)}
        problems={problems.filter(
          (one) => one === PROBLEMS.file || one === PROBLEMS.type || one === PROBLEMS.size || one === OFFERED_AS_A_TABLE,
        )}
      >
        {(id, describedBy) => (
          <Input
            id={id}
            type="file"
            name="file"
            className="h-11 sm:h-9"
            aria-describedby={describedBy}
            accept={acceptOf(options.types)}
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
            }}
          />
        )}
      </Field>
      {problems.includes(OFFERED_AS_A_TABLE) ? (
        <p className="m-0 text-[12.5px]">
          <Link to={CLASSIFICATION_PATH}>{ADD_IT_ON_CLASSIFICATION}</Link>
        </p>
      ) : null}
      <PlaceFields options={options} place={place} onChange={setPlace} problems={problems} />
      <p className="m-0 text-[12px] text-dim">
        Checked by the {options.checkedBy} before it is read, and found by {options.foundBy}.
      </p>
      <Submit label={ADD_FILE} busy={busy} />
    </form>
  );
}

/** Add a web page by its link (M7.1.2). */
export function AddLinkForm({ options, onAdded }: { readonly options: UploadOptions; readonly onAdded: () => void }) {
  const [url, setUrl] = useState("");
  const [place, setPlace] = useState<Place>(firstPlace(options));
  const [problems, setProblems] = useState<readonly LinkProblem[]>([]);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [said, setSaid] = useState("");

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const draft = { url, ...place };
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
      setFailure(result.ok ? null : result.failure);
      if (result.ok) {
        const added = readUploaded(result.data);
        setSaid(added === null ? "" : addedSentence(added));
        onAdded();
      }
    })();
  };

  const placeSaid = [
    ...(problems.includes("kind") ? [PROBLEMS.kind] : []),
    ...(problems.includes("department") ? [PROBLEMS.department] : []),
  ];
  return (
    <form className={FORM} aria-label="Add a web page" onSubmit={onSubmit} noValidate>
      {failure === null ? null : <FailureNotice failure={failure} fields={["url", "kind", "level", "department"]} />}
      {said === "" ? null : <Status>{said}</Status>}
      {busy ? <Status>{FETCHING}</Status> : null}
      <Field label={ADDRESS_LABEL} hint={ADDRESS_HINT} problems={problems.includes("url") ? [LINK_PROBLEMS.url] : []}>
        {(id, describedBy) => (
          <Input
            id={id}
            type="url"
            name="url"
            className="h-11 sm:h-9"
            placeholder="https://"
            aria-describedby={describedBy}
            value={url}
            onChange={(event) => {
              setUrl(event.target.value);
            }}
          />
        )}
      </Field>
      <PlaceFields options={options} place={place} onChange={setPlace} problems={placeSaid} />
      <Submit label={ADD_LINK} busy={busy} />
    </form>
  );
}

interface Line {
  readonly name: string;
  readonly said: string;
  readonly queued: Queued | null;
}

/** Queue many files for the background worker (M7.1.5). */
export function AddManyForm({ options, onAdded }: { readonly options: UploadOptions; readonly onAdded: () => void }) {
  const [files, setFiles] = useState<readonly File[]>([]);
  const [place, setPlace] = useState<Place>(firstPlace(options));
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [busy, setBusy] = useState(false);
  const [lines, setLines] = useState<readonly Line[]>([]);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const found = [...(files.length === 0 ? [PROBLEMS.files] : []), ...placeProblems(place)];
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
        } else if (isOfferedAsTable(file.name, options)) {
          told.push({ name: file.name, said: `${file.name}: ${NOT_SENT_TABLE}`, queued: null });
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
    <form className={FORM} aria-label="Add many files" onSubmit={onSubmit} noValidate>
      {busy ? <Status>{QUEUEING}</Status> : null}
      {lines.length === 0 ? null : (
        <ul aria-label="What became of each file" className="m-0 flex list-none flex-col gap-1 p-0 text-[12.5px] text-ink">
          {lines.map((line, index) => (
            <li key={`${String(index)}-${line.name}`} className="[overflow-wrap:anywhere]">
              {line.said}
            </li>
          ))}
        </ul>
      )}
      {waiting && !busy ? (
        <div>
          <Button type="button" variant="outline" size="sm" className="min-h-11 sm:min-h-8" onClick={checkAgain}>
            {CHECK_AGAIN}
          </Button>
        </div>
      ) : null}
      <Field
        label={FILES_LABEL}
        hint={`${acceptsWords(options.types)} The background worker reads them one at a time, so questions asked meanwhile are not slowed.`}
        problems={problems.filter((one) => one === PROBLEMS.files)}
      >
        {(id, describedBy) => (
          <Input
            id={id}
            type="file"
            name="files"
            multiple
            className="h-11 sm:h-9"
            aria-describedby={describedBy}
            accept={acceptOf(options.types)}
            onChange={(event) => {
              setFiles([...(event.target.files ?? [])]);
            }}
          />
        )}
      </Field>
      <PlaceFields options={options} place={place} onChange={setPlace} problems={problems} />
      <Submit label={QUEUE_FILES} busy={busy} />
    </form>
  );
}
