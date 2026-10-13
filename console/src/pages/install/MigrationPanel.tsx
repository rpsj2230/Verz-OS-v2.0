/**
 * Migration from another system on the Features page: the register of what the old system holds, the
 * comparison period and the cutover, each with where it stands and what is outstanding in it, and a
 * place to save a version of it by pasting the document.
 *
 * **Nothing here decides who may.** The route asks for `admin:install_setting` over everything and
 * refuses everybody else before it reads anything, and a refusal is shown as the API wrote it. What is
 * outstanding is computed by the API from what was saved; nothing here works it out.
 *
 * Task ids: M37.1.1.1, M37.1.3.2, M37.1.4.1, M37.7.5
 */

import { useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { Chip, FailureState, LoadingState, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Textarea } from "../../components/ui/textarea";
import {
  COMPLETE_PATH,
  DOCUMENTS,
  findings,
  MIGRATION_API_PATH,
  MIGRATION_TITLE,
  NOT_JSON,
  NOT_REPORTED,
  NOT_SAVED,
  NOTHING_REACHES_IT,
  READING_MIGRATION,
  readDocument,
  readWorkspace,
  REPORT_COMPLETE,
  standing,
  SWITCHED_OFF,
  UNREADABLE_MIGRATION,
  type Document,
  type WorkspaceBody,
} from "../migrationQuery";

function Editor({
  document,
  body,
  onSaved,
}: {
  readonly document: Document;
  readonly body: WorkspaceBody;
  readonly onSaved: () => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const id = `migration-${document.key}`;
  const outstanding = findings(document.key, body);

  function save(): void {
    const parsed = readDocument(text);
    if (parsed === null) {
      setProblem(NOT_JSON);
      return;
    }
    setProblem(null);
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(document.path, { method: "PUT", body: parsed });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setText("");
      onSaved();
    })();
  }

  return (
    <SectionCard title={document.title} headingLevel="h3" action={<Chip>{standing(document.key, body)}</Chip>}>
      {outstanding.length === 0 ? null : (
        <ul className="m-0 list-disc pl-5 text-[12.5px] text-dim">
          {outstanding.map((one) => (
            <li key={one}>{one}</li>
          ))}
        </ul>
      )}
      {body.workspace_is_on ? (
        <>
          <label className="m-0 mt-2 block text-[13px] text-body" htmlFor={id}>
            {document.label}
          </label>
          <Textarea
            id={id}
            value={text}
            rows={6}
            className="mt-1 font-mono text-[12px]"
            onChange={(event) => {
              setText(event.target.value);
            }}
          />
          {problem === null ? null : <Note>{problem}</Note>}
          {failure === null ? null : <FailureState failure={failure} title={NOT_SAVED} />}
          <div className="mt-2">
            <Button size="sm" className="min-h-11 sm:min-h-8" disabled={busy || text.trim() === ""} onClick={save}>
              {`Save ${document.title.toLowerCase()}`}
            </Button>
          </div>
        </>
      ) : null}
    </SectionCard>
  );
}

function Reporter({ body, onReported }: { readonly body: WorkspaceBody; readonly onReported: () => void }) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  if (!body.workspace_is_on || body.cutover.saved === null || body.cutover.saved === undefined) {
    return null;
  }
  return (
    <div>
      <Button
        size="sm"
        variant="outline"
        className="min-h-11 sm:min-h-8"
        disabled={busy || body.cutover.reported_complete !== null}
        onClick={() => {
          setBusy(true);
          void (async () => {
            const result = await request<unknown>(COMPLETE_PATH, { method: "POST" });
            setBusy(false);
            if (!result.ok) {
              setFailure(result.failure);
              return;
            }
            setFailure(null);
            onReported();
          })();
        }}
      >
        {REPORT_COMPLETE}
      </Button>
      {failure === null ? null : <FailureState failure={failure} title={NOT_REPORTED} />}
    </div>
  );
}

export function MigrationPanel() {
  const [version, setVersion] = useState(0);
  const answer = useResource<unknown>(MIGRATION_API_PATH, version);

  let content;
  if (answer.busy) {
    content = <LoadingState label={READING_MIGRATION} />;
  } else if (answer.failure !== null) {
    content = <FailureState failure={answer.failure} />;
  } else {
    const body = readWorkspace(answer.data);
    content =
      body === null ? (
        <Note>{UNREADABLE_MIGRATION}</Note>
      ) : (
        <>
          {body.nothing_reaches_the_old_system ? <Note>{NOTHING_REACHES_IT}</Note> : null}
          {body.workspace_is_on ? null : <Note>{SWITCHED_OFF}</Note>}
          {DOCUMENTS.map((one) => (
            <Editor
              key={one.key}
              document={one}
              body={body}
              onSaved={() => {
                setVersion((count) => count + 1);
              }}
            />
          ))}
          <Reporter
            body={body}
            onReported={() => {
              setVersion((count) => count + 1);
            }}
          />
        </>
      );
  }
  return (
    <section data-slot="migration-panel" aria-label={MIGRATION_TITLE} className="flex min-w-0 flex-col gap-3">
      <h2 className="m-0 text-[15px] font-semibold">{MIGRATION_TITLE}</h2>
      {content}
    </section>
  );
}
