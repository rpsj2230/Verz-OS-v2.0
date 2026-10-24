/**
 * The stored workflows an agent may run, on its Profile: who may assign one, run one through the
 * agent, and what a run did (M17.6.5).
 *
 * **It replaces a card that said no workflow could be stored.** A workflow is written once, as a
 * versioned definition (`WorkflowsPanel` on Features), and an agent is given it by name; the agent
 * runs exactly the version that is newest when it runs. This card is the assignment and the run.
 *
 * **Drawn from `GET /agents/{id}/workflows` and from nothing else about the agent.** The route
 * answers the same body to a reader who does not answer for the agent, with no names, so a reader
 * is told no more by this card than by an agent with none. Who may assign is the route's own
 * `may_change`; the list of workflows to choose from is a second read that only an administrator
 * is answered, and a reader refused it is offered no chooser.
 *
 * **Running is one press, and it is read-only by construction.** Each step goes through the gate as
 * the agent's own call at the asker's reach narrowed by the agent, and a step that would change
 * something is stated as not offered (`write_not_offered`). So the press is not confirmed and is
 * recorded in the allow-list of writes that end nothing; withdrawing an assignment is, because it
 * stops an agent doing something it did.
 *
 * **The switch.** While `stored_workflows` is off the route says so (`switched_on`), the press is
 * disabled and the sentence is the server's, drawn by `Explanation`. Assigning still works.
 *
 * Task ids: M17.6.5
 */

import { Workflow } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { Chip, ConfirmDialog, EmptyList, Explanation, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { FailureNotice } from "../../ui/FailureNotice";
import { NativeSelect } from "../access/formParts";
import { readNotChanged } from "../agentLifecycleQuery";
import {
  agentWorkflowRemovalApiPath,
  agentWorkflowRunApiPath,
  agentWorkflowsApiPath,
  causeWords,
  outcomeWords,
  readAssigned,
  readRun,
  readWorkflowList,
  statusWords,
  WORKFLOWS_API_PATH,
  type WorkflowRun,
} from "./agentWorkflowsQuery";

export const WORKFLOWS_HEADING = "Workflows";
export const WORKFLOWS_LEDE = "Stored, versioned procedures this agent may run, named here and never copied in.";
export const NO_WORKFLOWS = "No workflow is given to this agent";
export const NO_WORKFLOWS_ADDS = "A workflow is written under Install, Features and then given to this agent from here.";
export const CHOOSE_A_WORKFLOW = "Choose a workflow";
export const GIVE_IT = "Give it to this agent";
export const RUN_IT = "Run";
export const WITHDRAW = "Withdraw";
export const WORKFLOW_NOT_CHANGED = "Nothing was changed";
export const WORKFLOW_NOT_STARTED = "Nothing was started";
export const WITHDRAW_QUESTION = (workflow: string): string => `Withdraw ${workflow} from this agent?`;
export const WITHDRAW_CONSEQUENCE =
  "The agent can no longer run it. The workflow, its versions and every run kept stay as they are.";
export const A_RUN_IS_READ_ONLY =
  "A run goes through the gate as this agent's own call at your reach narrowed by the agent. A step that would change something is not offered and is recorded as not offered.";

interface Refused {
  readonly failure: ApiFailure;
  readonly title: string;
  readonly sentence?: string;
}

function RunResult({ run }: { readonly run: WorkflowRun }) {
  return (
    <div data-slot="workflow-run" className="flex min-w-0 flex-col gap-2 rounded-md border border-line px-3 py-2.5">
      <p className="m-0 text-[13px] font-medium text-ink [overflow-wrap:anywhere]">
        {`${run.workflow_id}, version ${String(run.version)}: ${outcomeWords(run.outcome)}`}
      </p>
      {run.failed_step === null ? null : (
        <p className="m-0 text-[12.5px] text-body [overflow-wrap:anywhere]">{`The first step that failed: ${run.failed_step}.`}</p>
      )}
      <ol aria-label="Steps of this run" className="m-0 flex list-none flex-col gap-1 p-0">
        {run.steps.map((one) => (
          <li key={one.step_id} className="flex min-w-0 flex-wrap items-center gap-2 text-[12.5px]">
            <span className="min-w-0 font-mono text-ink [overflow-wrap:anywhere]">{one.step_id}</span>
            <Chip>{statusWords(one.status)}</Chip>
            {one.cause === null || one.cause === undefined ? null : <span className="text-dim">{causeWords(one.cause)}</span>}
            {one.detail === "" ? null : <span className="text-dim [overflow-wrap:anywhere]">{one.detail}</span>}
            <span className="text-dim">{`${String(one.attempts)} ${one.attempts === 1 ? "try" : "tries"}, ${one.seconds.toFixed(1)} seconds`}</span>
          </li>
        ))}
      </ol>
      {run.candidates_opened === undefined || run.candidates_opened.length === 0 ? null : (
        <Note>{`A review was opened for ${run.candidates_opened.join(", ")}, because ${run.candidates_opened.length === 1 ? "it" : "they"} failed in each of the last runs. The workflow itself was not changed.`}</Note>
      )}
    </div>
  );
}

export function AgentWorkflows({ agentId }: { readonly agentId: string }) {
  const chooserId = useId();
  const [version, setVersion] = useState(0);
  const answer = useResource<unknown>(agentWorkflowsApiPath(agentId), version);
  const written = useResource<unknown>(WORKFLOWS_API_PATH);
  const shown = useMemo(() => (answer.data === null ? null : readAssigned(answer.data)), [answer.data]);
  const offered = useMemo(() => (written.data === null ? null : readWorkflowList(written.data)), [written.data]);
  const [chosen, setChosen] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [running, setRunning] = useState<string | null>(null);
  const [refused, setRefused] = useState<Refused | null>(null);
  const [last, setLast] = useState<WorkflowRun | null>(null);

  // A reader the route does not tell the names to is drawn no card: the body is the same whether
  // the agent has any or none, so nothing is said to them either way.
  if (shown === null || !shown.names_shown) {
    return null;
  }

  const refuse = (failure: ApiFailure, body: unknown, title: string): void => {
    const notChanged = failure.status === 409 ? readNotChanged(body) : null;
    setRefused(notChanged === null ? { failure, title } : { failure, title, sentence: notChanged.sentence });
  };

  const give = () => {
    if (chosen === "") {
      return;
    }
    setSending(true);
    void (async () => {
      const result = await request<unknown>(agentWorkflowsApiPath(agentId), { method: "POST", body: { workflow_id: chosen } });
      setSending(false);
      if (result.ok) {
        setChosen("");
        setRefused(null);
        setVersion((count) => count + 1);
        return;
      }
      refuse(result.failure, result.body, WORKFLOW_NOT_CHANGED);
    })();
  };

  const withdraw = () => {
    if (pending === null) {
      return;
    }
    const workflow = pending;
    setSending(true);
    void (async () => {
      const result = await request<unknown>(agentWorkflowRemovalApiPath(agentId), { method: "POST", body: { workflow_id: workflow } });
      setSending(false);
      setPending(null);
      if (result.ok) {
        setRefused(null);
        setLast(null);
        setVersion((count) => count + 1);
        return;
      }
      refuse(result.failure, result.body, WORKFLOW_NOT_CHANGED);
    })();
  };

  const startRun = (workflow: string) => {
    setRunning(workflow);
    setRefused(null);
    void (async () => {
      const result = await request<unknown>(agentWorkflowRunApiPath(agentId), { method: "POST", body: { workflow_id: workflow } });
      setRunning(null);
      if (result.ok) {
        setLast(readRun(result.data));
        return;
      }
      refuse(result.failure, result.body, WORKFLOW_NOT_STARTED);
    })();
  };

  const left = (offered?.workflows ?? []).filter((one) => !shown.workflows.includes(one.workflow_id));
  return (
    <SectionCard title={WORKFLOWS_HEADING} lede={WORKFLOWS_LEDE} action={<Workflow aria-hidden className="size-4 text-dim" />}>
      <div data-slot="agent-workflows" className="flex min-w-0 flex-col gap-3">
        {refused === null ? null : (
          <FailureNotice
            failure={refused.failure}
            title={refused.title}
            {...(refused.sentence === undefined ? {} : { sentence: refused.sentence })}
          />
        )}
        {shown.switched_on ? null : <Explanation form="note" act="workflow.run_switched_off" />}
        {shown.workflows.length === 0 ? (
          <EmptyList compact title={NO_WORKFLOWS} adds={NO_WORKFLOWS_ADDS} by={["super_admin", "department_admin"]} />
        ) : (
          <ul aria-label="Workflows this agent may run" className="m-0 flex list-none flex-col gap-2 p-0">
            {shown.workflows.map((one) => (
              <li key={one} className="flex min-w-0 flex-wrap items-center gap-2">
                <span className="min-w-0 font-medium text-ink [overflow-wrap:anywhere]">{one}</span>
                <span className="ml-auto flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    className="min-h-11 sm:min-h-8"
                    aria-label={`Run ${one} through this agent`}
                    disabled={!shown.switched_on || running !== null || sending}
                    onClick={() => {
                      startRun(one);
                    }}
                  >
                    {running === one ? "Running" : RUN_IT}
                  </Button>
                  {shown.may_change ? (
                    <Button
                      size="sm"
                      variant="outline"
                      className="min-h-11 sm:min-h-8"
                      aria-label={`Withdraw ${one} from this agent`}
                      disabled={sending}
                      onClick={() => {
                        setRefused(null);
                        setPending(one);
                      }}
                    >
                      {WITHDRAW}
                    </Button>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        )}
        {last === null ? null : <RunResult run={last} />}
        {shown.may_change && left.length > 0 ? (
          <div className="flex min-w-0 flex-wrap items-end gap-2">
            <div className="flex min-w-0 flex-col gap-1.5">
              <label htmlFor={chooserId} className="text-[13px] font-medium text-ink">
                {CHOOSE_A_WORKFLOW}
              </label>
              <NativeSelect id={chooserId} describedBy="" invalid={false} value={chosen} onChange={setChosen}>
                <option value="">{CHOOSE_A_WORKFLOW}</option>
                {left.map((one) => (
                  <option key={one.workflow_id} value={one.workflow_id}>
                    {`${one.name} (${one.workflow_id}, version ${String(one.version)})`}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <Button size="sm" className="min-h-11 sm:min-h-8" disabled={sending || chosen === ""} onClick={give}>
              {GIVE_IT}
            </Button>
          </div>
        ) : null}
        <Note>{A_RUN_IS_READ_ONLY}</Note>
      </div>
      <ConfirmDialog
        open={pending !== null}
        question={pending === null ? "" : WITHDRAW_QUESTION(pending)}
        consequence={WITHDRAW_CONSEQUENCE}
        confirmLabel="Withdraw it"
        cancelLabel="Not now"
        busy={sending}
        onConfirm={withdraw}
        onCancel={() => {
          setPending(null);
        }}
      />
    </SectionCard>
  );
}
