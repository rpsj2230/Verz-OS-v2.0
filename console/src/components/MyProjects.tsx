/**
 * A person's own projects, in My workspace: threads and documents grouped under a name, which a
 * question asked inside the project reads as context (M40.7.7).
 *
 * Every row is the API's answer for the person asking (`brain.project_routes`) and draws what it
 * was sent. **A project is context for an answer and is never kept as memory**, and the card says
 * so beside the list. A document the person can no longer read stays on the list and nothing marks
 * it, because a mark would say what they may no longer read; the answer simply does not use it. No
 * figure counts anything.
 *
 * **The switch gates the door and not the room.** With projects switched off the list, the rename,
 * taking something out and putting a project away still work, and the card says projects cannot be
 * made or added to now, in a sentence.
 *
 * Task ids: M40.7.7
 */

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { when } from "../pages/artifactsQuery";
import {
  acceptOf,
  readUploaded,
  readUploadOptions,
  typeOf,
  UPLOAD_OPTIONS_API_PATH,
  uploadPath,
  type UploadOptions,
} from "../pages/knowledgeQuery";
import {
  PROJECTS_API_PATH,
  addItemApiPath,
  archiveApiPath,
  itemBody,
  nameBody,
  projectApiPath,
  removeItemApiPath,
  renameApiPath,
  type ProjectDetail,
  type ProjectsBody,
} from "../pages/myProjectsQuery";
import { readThreads, THREADS_API_PATH, type ThreadSummary } from "../pages/threadsQuery";
import { FailureNotice } from "../ui/FailureNotice";
import { ConfirmAction } from "./ConfirmAction";
import { EmptyList } from "./kit/states";

export const PROJECTS_CAPTION = "My projects";
export const PROJECTS_NOTE =
  "A project groups conversations and documents. A question asked inside it reads its documents " +
  "for that answer, at the access you hold at that moment, and nothing in a project is kept as " +
  "memory.";
export const NOTHING_IN_PROJECTS = "You have no project.";
export const NOT_SWITCHED_ON =
  "Projects are not switched on for this install, so none can be made and nothing can be added. " +
  "What you made before can still be looked at, renamed, emptied and put away.";
export const NAME_LABEL = "Name of the new project";
export const MAKE_LABEL = "Make a project";
export const OPEN_LABEL = "Open";
export const CLOSE_LABEL = "Close";
export const RENAME_LABEL = "Rename";
export const NEW_NAME_LABEL = "New name";
export const PUT_AWAY_LABEL = "Put away";
export const KEEP_LABEL = "Keep it";
export const PUT_AWAY_CONSEQUENCE =
  "It stops being listed and no question reads it. The conversations and documents in it stay " +
  "where they are.";
export const TAKE_OUT_LABEL = "Withdraw";
export const ADD_THREAD_LABEL = "Add a conversation";
export const CHOOSE_THREAD = "Choose a conversation";
export const ADD_FILE_LABEL = "Add a file";
export const FILE_FIELD_LABEL = "File to add";
export const FILE_KIND_LABEL = "What kind of document it is";
export const CHOOSE_A_FILE = "Choose a file to add.";
export const NOT_A_TYPE_OFFERED = "This kind of file cannot be added here.";
export const TOO_LARGE = "This file is larger than files of its kind may be.";
export const NOTHING_LISTED = "Nothing is in this project yet.";

function Reading({ what }: { readonly what: string }) {
  return (
    <p className="note" role="status">
      {`Reading ${what}.`}
    </p>
  );
}

function ProjectOpen({
  projectId,
  switchedOn,
  onChanged,
}: {
  readonly projectId: string;
  readonly switchedOn: boolean;
  readonly onChanged: () => void;
}) {
  const [version, setVersion] = useState(0);
  const detail = useResource<ProjectDetail>(projectApiPath(projectId), version);
  const [threads, setThreads] = useState<readonly ThreadSummary[]>([]);
  const [options, setOptions] = useState<UploadOptions | null>(null);
  const [renaming, setRenaming] = useState("");
  const [thread, setThread] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState("");
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  useEffect(() => {
    let live = true;
    void (async () => {
      const listed = await request<unknown>(THREADS_API_PATH);
      const read = listed.ok ? readThreads(listed.data) : null;
      const offered = await request<unknown>(UPLOAD_OPTIONS_API_PATH);
      const upload = offered.ok ? readUploadOptions(offered.data) : null;
      if (!live) return;
      setThreads(read ?? []);
      setOptions(upload);
      setKind(upload?.kinds[0]?.value ?? "");
    })();
    return () => {
      live = false;
    };
  }, []);

  const changed = useCallback(() => {
    setVersion((current) => current + 1);
    onChanged();
  }, [onChanged]);

  const send = useCallback(
    (path: string, body: unknown) => {
      setBusy(true);
      setFailure(null);
      void (async () => {
        const result = await request<unknown>(path, { method: "POST", body });
        setBusy(false);
        if (result.ok) {
          changed();
          return;
        }
        setFailure(result.failure);
      })();
    },
    [changed],
  );

  const onRename = (submitted: FormEvent<HTMLFormElement>) => {
    submitted.preventDefault();
    const body = nameBody(renaming);
    if (body === null) return;
    send(renameApiPath(projectId), body);
    setRenaming("");
  };

  const onAddFile = (submitted: FormEvent<HTMLFormElement>) => {
    submitted.preventDefault();
    const type = file === null || options === null ? null : typeOf(file.name, options.types);
    const found =
      file === null
        ? CHOOSE_A_FILE
        : type === null
          ? NOT_A_TYPE_OFFERED
          : file.size > type.maxBytes
            ? TOO_LARGE
            : "";
    setProblem(found);
    if (found !== "" || file === null || type === null) return;
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
      const listed = await request<unknown>(addItemApiPath(projectId), {
        method: "POST",
        body: itemBody("file", uploaded.itemId),
      });
      setBusy(false);
      if (listed.ok) {
        setFile(null);
        changed();
        return;
      }
      setFailure(listed.failure);
    })();
  };

  return (
    <div>
      {failure === null ? null : <FailureNotice failure={failure} />}
      {detail.failure ? (
        <FailureNotice failure={detail.failure} />
      ) : detail.data === null ? (
        <Reading what="the project" />
      ) : (
        <>
          <p className="note">{`Made ${when(detail.data.created_at)}.`}</p>
          {detail.data.items.length === 0 ? (
            <p className="note">{NOTHING_LISTED}</p>
          ) : (
            <ul aria-label={`In ${detail.data.name}`}>
              {detail.data.items.map((one) => (
                <li key={`${one.kind}-${one.ref}`}>
                  {one.kind === "thread"
                    ? `Conversation: ${one.title === "" ? one.ref : one.title}. `
                    : `File: ${one.ref}. `}
                  <button
                    type="button"
                    className="button"
                    disabled={busy}
                    aria-label={`${TAKE_OUT_LABEL}: ${one.kind} ${one.ref}`}
                    onClick={() => {
                      send(removeItemApiPath(projectId), itemBody(one.kind as "file" | "thread", one.ref));
                    }}
                  >
                    {TAKE_OUT_LABEL}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <form aria-label={`${RENAME_LABEL} ${detail.data.name}`} onSubmit={onRename} noValidate>
            <label className="ask__label" htmlFor={`rename-${projectId}`}>
              {NEW_NAME_LABEL}
            </label>
            <input
              id={`rename-${projectId}`}
              className="form-control"
              value={renaming}
              maxLength={120}
              disabled={busy}
              onChange={(changed_) => setRenaming(changed_.target.value)}
            />
            <div className="form-actions">
              <button type="submit" className="button" disabled={busy || nameBody(renaming) === null}>
                {RENAME_LABEL}
              </button>
            </div>
          </form>
          {switchedOn ? (
            <>
              <form
                aria-label={ADD_THREAD_LABEL}
                onSubmit={(submitted) => {
                  submitted.preventDefault();
                  if (thread !== "") send(addItemApiPath(projectId), itemBody("thread", thread));
                }}
              >
                <label className="ask__label" htmlFor={`thread-${projectId}`}>
                  {ADD_THREAD_LABEL}
                </label>
                <select
                  id={`thread-${projectId}`}
                  className="form-control"
                  value={thread}
                  disabled={busy}
                  onChange={(changed_) => setThread(changed_.target.value)}
                >
                  <option value="">{CHOOSE_THREAD}</option>
                  {threads.map((one) => (
                    <option key={one.threadId} value={one.threadId}>
                      {one.title === "" ? one.threadId : one.title}
                    </option>
                  ))}
                </select>
                <div className="form-actions">
                  <button type="submit" className="button" disabled={busy || thread === ""}>
                    {ADD_THREAD_LABEL}
                  </button>
                </div>
              </form>
              {options === null || !options.personal ? null : (
                <form aria-label={ADD_FILE_LABEL} onSubmit={onAddFile} noValidate>
                  <label className="ask__label" htmlFor={`file-${projectId}`}>
                    {FILE_FIELD_LABEL}
                  </label>
                  <input
                    id={`file-${projectId}`}
                    type="file"
                    className="form-control"
                    accept={acceptOf(options.types)}
                    disabled={busy}
                    aria-invalid={problem === "" ? undefined : true}
                    onChange={(changed_) => {
                      setFile(changed_.target.files?.[0] ?? null);
                      setProblem("");
                    }}
                  />
                  {problem === "" ? null : <p>{problem}</p>}
                  <label className="ask__label" htmlFor={`kind-${projectId}`}>
                    {FILE_KIND_LABEL}
                  </label>
                  <select
                    id={`kind-${projectId}`}
                    className="form-control"
                    value={kind}
                    disabled={busy}
                    onChange={(changed_) => setKind(changed_.target.value)}
                  >
                    {options.kinds.map((one) => (
                      <option key={one.value} value={one.value}>
                        {one.label}
                      </option>
                    ))}
                  </select>
                  <div className="form-actions">
                    <button type="submit" className="button" disabled={busy}>
                      {ADD_FILE_LABEL}
                    </button>
                  </div>
                </form>
              )}
            </>
          ) : null}
        </>
      )}
    </div>
  );
}

export function MyProjects() {
  const [version, setVersion] = useState(0);
  const answer = useResource<ProjectsBody>(PROJECTS_API_PATH, version);
  const [name, setName] = useState("");
  const [opened, setOpened] = useState("");
  const [putting, setPutting] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const reload = useCallback(() => {
    setVersion((current) => current + 1);
  }, []);

  const make = (submitted: FormEvent<HTMLFormElement>) => {
    submitted.preventDefault();
    const body = nameBody(name);
    if (body === null) return;
    setBusy(true);
    setFailure(null);
    void (async () => {
      const result = await request<unknown>(PROJECTS_API_PATH, { method: "POST", body });
      setBusy(false);
      if (result.ok) {
        setName("");
        reload();
        return;
      }
      setFailure(result.failure);
    })();
  };

  const putAway = (projectId: string) => {
    setBusy(true);
    setFailure(null);
    void (async () => {
      const result = await request<unknown>(archiveApiPath(projectId), { method: "POST", body: {} });
      setBusy(false);
      setPutting("");
      if (result.ok) {
        setOpened("");
        reload();
        return;
      }
      setFailure(result.failure);
    })();
  };

  return (
    <section className="card">
      <h2>{PROJECTS_CAPTION}</h2>
      <p className="note">{PROJECTS_NOTE}</p>
      {failure === null ? null : <FailureNotice failure={failure} />}
      {answer.failure ? (
        <FailureNotice failure={answer.failure} />
      ) : answer.data === null ? (
        <Reading what="your projects" />
      ) : (
        <>
          {answer.data.switched_on ? (
            <form aria-label={MAKE_LABEL} onSubmit={make} noValidate>
              <label className="ask__label" htmlFor="my-projects-name">
                {NAME_LABEL}
              </label>
              <input
                id="my-projects-name"
                className="form-control"
                value={name}
                maxLength={120}
                disabled={busy}
                onChange={(changed) => setName(changed.target.value)}
              />
              <div className="form-actions">
                <button type="submit" className="button" disabled={busy || nameBody(name) === null}>
                  {MAKE_LABEL}
                </button>
              </div>
            </form>
          ) : (
            <p className="note">{NOT_SWITCHED_ON}</p>
          )}
          {putting === "" ? null : (
            <ConfirmAction
              question="Put this project away?"
              consequence={PUT_AWAY_CONSEQUENCE}
              confirmLabel={PUT_AWAY_LABEL}
              cancelLabel={KEEP_LABEL}
              busy={busy}
              onConfirm={() => {
                putAway(putting);
              }}
              onCancel={() => {
                setPutting("");
              }}
            />
          )}
          {answer.data.projects.length === 0 ? (
            <EmptyList
              compact
              title={NOTHING_IN_PROJECTS}
              adds="Make a project here, then add conversations and documents to it."
              by={["member"]}
            />
          ) : (
            <ul aria-label={PROJECTS_CAPTION}>
              {answer.data.projects.map((one) => (
                <li key={one.project_id}>
                  <strong>{one.name}</strong>
                  {` ${when(one.created_at)} `}
                  <button
                    type="button"
                    className="button"
                    aria-expanded={opened === one.project_id}
                    aria-label={`${opened === one.project_id ? CLOSE_LABEL : OPEN_LABEL}: ${one.name}`}
                    onClick={() => {
                      setOpened(opened === one.project_id ? "" : one.project_id);
                    }}
                  >
                    {opened === one.project_id ? CLOSE_LABEL : OPEN_LABEL}
                  </button>{" "}
                  <button
                    type="button"
                    className="button"
                    aria-label={`${PUT_AWAY_LABEL}: ${one.name}`}
                    onClick={() => {
                      setPutting(one.project_id);
                    }}
                  >
                    {PUT_AWAY_LABEL}
                  </button>
                  {opened === one.project_id ? (
                    <ProjectOpen
                      projectId={one.project_id}
                      switchedOn={answer.data?.switched_on ?? false}
                      onChanged={reload}
                    />
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
