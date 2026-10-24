/**
 * Stored workflows on the Features page: the ones written and their newest version, a way to write
 * the next version, and the runs kept (M17.6.5).
 *
 * **Writing is insert-only.** Saving a definition under a name writes the next version; the earlier
 * ones stay, and a run records which version it ran. The definition is typed as JSON because that is
 * the form the route reads, and a definition the reader refuses is told with its reasons and writes
 * nothing, in the route's own words. Giving a workflow to an agent, and running it, are on that
 * agent's Profile.
 *
 * **Nothing here decides who may.** The routes ask for `admin:agent_lifecycle`'s sibling, the
 * authority that weighs how agents are used, and answer everybody else as for a screen that is not
 * there, which a refusal here draws as the API wrote it. A run is told by its steps' statuses and
 * causes, never by what a step returned: the trace keeps none.
 *
 * Task ids: M17.6.5
 */

import { useId, useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { Chip, EmptyList, Explanation, FailureState, LoadingState, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";
import { FailureNotice } from "../../ui/FailureNotice";
import { whenWords } from "../access/formParts";
import { readNotChanged } from "../agentLifecycleQuery";
import {
  causeWords,
  outcomeWords,
  readKeptRuns,
  readWorkflowList,
  saveBody,
  statusWords,
  WORKFLOW_RUNS_API_PATH,
  WORKFLOWS_API_PATH,
  type KeptWorkflowRuns,
  type WorkflowList,
} from "../agents/agentWorkflowsQuery";

export const WORKFLOWS_TITLE = "Stored workflows";
export const READING_WORKFLOWS = "Reading the workflows written so far.";
export const UNREADABLE_WORKFLOWS =
  "The API answered in a shape this console does not read, so no workflow is listed. The console and the API are probably from different releases.";
export const NO_WORKFLOWS_WRITTEN = "No workflow is written";
export const NO_WORKFLOWS_WRITTEN_ADDS = "Write one with the form below, and its first version is kept.";
export const NO_WORKFLOW_RUNS = "No workflow has been run";
export const NO_WORKFLOW_RUNS_ADDS = "Give a workflow to an agent from the agent's Profile and run it there, and the run is kept here.";
export const SAVE_A_WORKFLOW = "Write a workflow";
export const WORKFLOW_ID_LABEL = "Name (lower case letters, digits, hyphens and underscores)";
export const DEFINITION_LABEL = "Definition (JSON)";
export const SAVE_AS_NEXT = "Save as the next version";
export const NOT_JSON_WORKFLOW = "That is not a JSON object, so nothing was sent.";
export const WORKFLOW_NOT_SAVED = "The workflow was not saved";
export const WRITING_NOTE =
  "Saving writes the next version and changes none of the earlier ones. An agent runs the newest version at the moment it runs.";

function SaveForm({ saved, onSaved }: { readonly saved: string | null; readonly onSaved: (said: string) => void }) {
  const idId = useId();
  const textId = useId();
  const [workflowId, setWorkflowId] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [failure, setFailure] = useState<{ readonly failure: ApiFailure; readonly sentence?: string } | null>(null);

  function save(): void {
    const body = saveBody(workflowId, text);
    if (body === null) {
      setProblem(NOT_JSON_WORKFLOW);
      return;
    }
    setProblem(null);
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(WORKFLOWS_API_PATH, { method: "POST", body });
      setBusy(false);
      if (!result.ok) {
        const notChanged = result.failure.status === 409 ? readNotChanged(result.body) : null;
        setFailure(notChanged === null ? { failure: result.failure } : { failure: result.failure, sentence: notChanged.sentence });
        return;
      }
      setFailure(null);
      const version = (result.data as { version?: unknown } | null)?.version;
      onSaved(`${body.workflow_id} was saved as version ${typeof version === "number" ? String(version) : "the next"}.`);
    })();
  }

  return (
    <SectionCard title={SAVE_A_WORKFLOW} headingLevel="h3">
      <div className="flex min-w-0 flex-col gap-2">
        <label htmlFor={idId} className="text-[13px] font-medium text-ink">
          {WORKFLOW_ID_LABEL}
        </label>
        <Input
          id={idId}
          className="h-11 sm:h-9"
          autoComplete="off"
          value={workflowId}
          onChange={(event) => {
            setWorkflowId(event.target.value);
          }}
        />
        <label htmlFor={textId} className="text-[13px] font-medium text-ink">
          {DEFINITION_LABEL}
        </label>
        <Textarea
          id={textId}
          rows={10}
          className="font-mono text-[12px]"
          value={text}
          onChange={(event) => {
            setText(event.target.value);
          }}
        />
        {problem === null ? null : <Note>{problem}</Note>}
        {failure === null ? null : (
          <FailureNotice
            failure={failure.failure}
            title={WORKFLOW_NOT_SAVED}
            {...(failure.sentence === undefined ? {} : { sentence: failure.sentence })}
          />
        )}
        {saved === null ? null : <Note>{saved}</Note>}
        <div>
          <Button size="sm" className="min-h-11 sm:min-h-8" disabled={busy || workflowId.trim() === "" || text.trim() === ""} onClick={save}>
            {SAVE_AS_NEXT}
          </Button>
        </div>
        <Note>{WRITING_NOTE}</Note>
      </div>
    </SectionCard>
  );
}

function Written({ list }: { readonly list: WorkflowList }) {
  return list.workflows.length === 0 ? (
    <EmptyList title={NO_WORKFLOWS_WRITTEN} adds={NO_WORKFLOWS_WRITTEN_ADDS} by={["super_admin"]} />
  ) : (
    <ul aria-label="Workflows written" className="m-0 flex list-none flex-col gap-2 p-0">
      {list.workflows.map((one) => (
        <li key={one.workflow_id} className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="min-w-0 font-medium text-ink [overflow-wrap:anywhere]">{one.name}</span>
          <span className="min-w-0 font-mono text-[12px] text-dim [overflow-wrap:anywhere]">{one.workflow_id}</span>
          <Chip>{`version ${String(one.version)}`}</Chip>
        </li>
      ))}
    </ul>
  );
}

function Kept({ kept }: { readonly kept: KeptWorkflowRuns }) {
  return kept.runs.length === 0 ? (
    <EmptyList title={NO_WORKFLOW_RUNS} adds={NO_WORKFLOW_RUNS_ADDS} by={["super_admin", "department_admin"]} />
  ) : (
    <ul aria-label="Workflow runs kept" className="m-0 flex list-none flex-col gap-3 p-0">
      {kept.runs.map((run) => (
        <li key={run.run_id} className="flex min-w-0 flex-col gap-1">
          <p className="m-0 text-[13px] text-ink [overflow-wrap:anywhere]">
            <span className="font-medium">{`${run.workflow_id}, version ${String(run.version)}`}</span>
            {`: ${outcomeWords(run.outcome)}. Run through ${run.agent_id} by ${run.run_by}, ${whenWords(run.started_at)}.`}
          </p>
          <ol aria-label={`Steps of ${run.run_id}`} className="m-0 flex list-none flex-wrap gap-x-4 gap-y-0.5 p-0 text-[12.5px] text-dim">
            {run.steps.map((one) => (
              <li key={one.step_id} className="[overflow-wrap:anywhere]">
                {`${one.step_id}: ${statusWords(one.status)}${one.cause === null || one.cause === undefined ? "" : `, ${causeWords(one.cause)}`}`}
              </li>
            ))}
          </ol>
        </li>
      ))}
    </ul>
  );
}

/**
 * What a save said is held by the panel and not by the form: saving re-reads the list, which draws
 * the loading sentence in its place, and a sentence held by what that replaces would be lost the
 * moment it arrived.
 */
export function WorkflowsPanel() {
  const [version, setVersion] = useState(0);
  const [saved, setSaved] = useState<string | null>(null);
  const written = useResource<unknown>(WORKFLOWS_API_PATH, version);
  const runs = useResource<unknown>(WORKFLOW_RUNS_API_PATH, version);

  let content;
  if (written.busy) {
    content = <LoadingState label={READING_WORKFLOWS} />;
  } else if (written.failure !== null) {
    content = <FailureState failure={written.failure} />;
  } else {
    const list = readWorkflowList(written.data);
    const kept = readKeptRuns(runs.data);
    content =
      list === null ? (
        <Note>{UNREADABLE_WORKFLOWS}</Note>
      ) : (
        <>
          {list.switched_on ? null : <Explanation form="note" act="workflow.run_switched_off" />}
          <Written list={list} />
          <SaveForm
            saved={saved}
            onSaved={(said) => {
              setSaved(said);
              setVersion((count) => count + 1);
            }}
          />
          <SectionCard title="Runs kept" headingLevel="h3">
            {runs.failure !== null ? <FailureState failure={runs.failure} /> : kept === null ? <Note>{UNREADABLE_WORKFLOWS}</Note> : <Kept kept={kept} />}
          </SectionCard>
        </>
      );
  }
  return (
    <section data-slot="workflows-panel" aria-label={WORKFLOWS_TITLE} className="flex min-w-0 flex-col gap-3">
      <h2 className="m-0 text-[15px] font-semibold">{WORKFLOWS_TITLE}</h2>
      {content}
    </section>
  );
}
