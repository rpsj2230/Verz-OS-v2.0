/**
 * The specialists a coordinating agent may hand a subtask to, on its Profile: who they are, whether
 * they may be run together, and a place to give it a request and read how it was split and what came
 * back (M18.5.1, M18.6.2).
 *
 * **A link is configuration and confers no reach.** The route says so once (`words`) and this card
 * draws that sentence and no other. Whoever asks a coordinator is the one asking: every specialist
 * runs at the asker's own reach, narrowed by the coordinating agent, the specialist and the subtask,
 * so the card never offers a result the asker could not have had by asking each specialist directly.
 *
 * **Drawn from `GET /agents/{id}/coordination`.** The route answers a reader who does not answer for
 * the agent with the same body and no names, so the card says no more to that reader than to a
 * reader of an agent with none. A refusal is the API's own words, under a heading that says nothing
 * changed.
 *
 * **Withdrawing a specialist and changing whether specialists may run together are confirmed**, the
 * first because it stops the coordinator handing that agent work and the second because running
 * together spends the install's parallel room and costs more for the same request. Allowing one adds
 * a row and ends nothing. **Asking is one press and records nothing but the run**: the plan, who did
 * what and the result are drawn from the answer, and the cost is the product's estimate, which the
 * route says beside it.
 *
 * **The switch.** While `multi_agent_coordination` is off the route says so (`switched_on`), the ask
 * is disabled and the sentence is the server's, drawn by `Explanation`. Links can still be edited.
 *
 * Task ids: M18.5.1, M18.6.2
 */

import { Network } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { Chip, ConfirmDialog, EmptyList, Explanation, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Switch } from "../../components/ui/switch";
import { Textarea } from "../../components/ui/textarea";
import { FailureNotice } from "../../ui/FailureNotice";
import { NativeSelect } from "../access/formParts";
import { readNotChanged } from "../agentLifecycleQuery";
import { readRoster, ROSTER_API_PATH } from "../agentsQuery";
import { moneyWords } from "../spendQuery";
import {
  agentCalleeRemovalsApiPath,
  agentCalleesApiPath,
  agentCoordinationApiPath,
  agentFanOutApiPath,
  askBody,
  childWords,
  COORDINATED_RUNS_API_PATH,
  modeWords,
  readCoordinatedRun,
  readCoordination,
  whyWords,
  type CoordinationRun,
} from "./agentSpecialistsQuery";

export const SPECIALISTS_HEADING = "Specialists";
export const SPECIALISTS_LEDE = "The agents this one may hand a subtask to, and the request it splits between them.";
export const NO_SPECIALISTS = "No specialist is allowed for this agent";
export const NO_SPECIALISTS_ADDS = "A specialist is allowed from here, by choosing another agent, so this one can hand it a subtask.";
export const CHOOSE_A_SPECIALIST = "Choose an agent to allow";
export const ALLOW_IT = "Allow it";
export const FAN_OUT_LABEL = "Let this agent run its specialists at the same time";
export const FAN_OUT_ON = "On: when the gate agrees there is room and the request splits well, specialists run together.";
export const FAN_OUT_OFF = "Off: specialists run one after another, and the run records that this is why.";
export const ASK_LABEL = "A request to split between the specialists";
export const ASK_IT = "Split and run";
export const SPECIALISTS_NOT_CHANGED = "Nothing was changed";
export const REQUEST_NOT_STARTED = "Nothing was started";
export const WITHDRAW_QUESTION = (name: string): string => `Withdraw ${name} as a specialist?`;
export const WITHDRAW_CONSEQUENCE =
  "This agent will not hand it a subtask again. Runs already kept stay as they are, and nothing the agent could see changes.";
export const GRANT_FAN_OUT_QUESTION = (name: string): string => `Let ${name} run its specialists together?`;
export const GRANT_FAN_OUT_CONSEQUENCE =
  "A request can then be split across specialists at once, which finishes sooner and costs more for the same request. The gate still decides each time, and every specialist still runs at the asker's own reach.";
export const WITHDRAW_FAN_OUT_QUESTION = (name: string): string => `Stop ${name} running its specialists together?`;
export const WITHDRAW_FAN_OUT_CONSEQUENCE = "From its next run the specialists go one after another.";

type Pending =
  | { readonly kind: "withdraw"; readonly id: string; readonly name: string }
  | { readonly kind: "fan-out"; readonly enabled: boolean };

interface Refused {
  readonly failure: ApiFailure;
  readonly title: string;
  readonly sentence?: string;
}

/** The merged values of one subtask, as "name: value" lines, for the asker who was given them. */
function valueLines(values: Readonly<Record<string, unknown>>): string[] {
  return Object.entries(values).map(([key, value]) => `${key}: ${typeof value === "string" ? value : JSON.stringify(value)}`);
}

export function RunAnswer({ run }: { readonly run: CoordinationRun }) {
  const merged = run.merged;
  return (
    <div data-slot="coordinated-run" className="flex min-w-0 flex-col gap-2 rounded-md border border-line px-3 py-2.5">
      <p className="m-0 flex flex-wrap items-center gap-2 text-[13px] font-medium text-ink">
        <span>{modeWords(run.mode)}</span>
        <Chip>{run.mode}</Chip>
      </p>
      {run.why.length === 0 ? null : (
        <p className="m-0 text-[12.5px] text-body">{`Not run together because ${run.why.map(whyWords).join(", and ")}.`}</p>
      )}
      <ol aria-label="Subtasks of this run" className="m-0 flex list-none flex-col gap-1 p-0">
        {run.children.map((one) => (
          <li key={one.subtask_id} className="flex min-w-0 flex-wrap items-center gap-2 text-[12.5px]">
            <span className="min-w-0 font-mono text-ink [overflow-wrap:anywhere]">{one.subtask_id}</span>
            <span className="text-dim [overflow-wrap:anywhere]">{`handed to ${one.callee_id}`}</span>
            <Chip>{childWords(one.status)}</Chip>
            <span className="text-dim">{`${one.seconds.toFixed(1)} seconds`}</span>
          </li>
        ))}
      </ol>
      {Object.keys(merged.values).length === 0 ? null : (
        <div className="flex min-w-0 flex-col gap-1" aria-label="What came back">
          {Object.entries(merged.values).map(([subtask, values]) => (
            <div key={subtask} className="min-w-0 text-[12.5px]">
              <span className="font-medium text-ink [overflow-wrap:anywhere]">{subtask}</span>
              <ul className="m-0 list-none p-0 text-body">
                {valueLines(values).map((line) => (
                  <li key={line} className="[overflow-wrap:anywhere]">
                    {line}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
      <p className="m-0 text-[12.5px] text-body">{merged.complete ? "Every specialist returned what it promised." : merged.notice}</p>
      <p className="m-0 text-[12.5px] text-dim">{`Estimated cost: ${moneyWords(merged.total_minor, merged.currency)}. ${run.cost_note}`}</p>
    </div>
  );
}

export function AgentSpecialists({ agentId, name }: { readonly agentId: string; readonly name: string }) {
  const chooserId = useId();
  const askId = useId();
  const [version, setVersion] = useState(0);
  const answer = useResource<unknown>(agentCoordinationApiPath(agentId), version);
  const roster = useResource<unknown>(ROSTER_API_PATH);
  const shown = useMemo(() => (answer.data === null ? null : readCoordination(answer.data)), [answer.data]);
  const agents = useMemo(() => (roster.data === null ? null : readRoster(roster.data)), [roster.data]);
  const [chosen, setChosen] = useState("");
  const [pending, setPending] = useState<Pending | null>(null);
  const [sending, setSending] = useState(false);
  const [asking, setAsking] = useState(false);
  const [text, setText] = useState("");
  const [refused, setRefused] = useState<Refused | null>(null);
  const [last, setLast] = useState<CoordinationRun | null>(null);

  // A reader the route does not tell the names to is drawn no card: the body is the same whether
  // the agent has any or none, so nothing is said to them either way.
  if (shown === null || !shown.names_shown) {
    return null;
  }

  const refuse = (failure: ApiFailure, body: unknown, title: string): void => {
    const notChanged = failure.status === 409 ? readNotChanged(body) : null;
    setRefused(notChanged === null ? { failure, title } : { failure, title, sentence: notChanged.sentence });
  };

  const allow = () => {
    if (chosen === "") {
      return;
    }
    setSending(true);
    void (async () => {
      const result = await request<unknown>(agentCalleesApiPath(agentId), { method: "POST", body: { callee_id: chosen } });
      setSending(false);
      if (result.ok) {
        setChosen("");
        setRefused(null);
        setVersion((count) => count + 1);
        return;
      }
      refuse(result.failure, result.body, SPECIALISTS_NOT_CHANGED);
    })();
  };

  const confirm = () => {
    if (pending === null) {
      return;
    }
    const doing = pending;
    setSending(true);
    void (async () => {
      const result =
        doing.kind === "withdraw"
          ? await request<unknown>(agentCalleeRemovalsApiPath(agentId), { method: "POST", body: { callee_id: doing.id } })
          : await request<unknown>(agentFanOutApiPath(agentId), { method: "POST", body: { enabled: doing.enabled } });
      setSending(false);
      setPending(null);
      if (result.ok) {
        setRefused(null);
        setVersion((count) => count + 1);
        return;
      }
      refuse(result.failure, result.body, SPECIALISTS_NOT_CHANGED);
    })();
  };

  const ask = () => {
    setAsking(true);
    setRefused(null);
    void (async () => {
      const result = await request<unknown>(COORDINATED_RUNS_API_PATH, { method: "POST", body: askBody(agentId, text) });
      setAsking(false);
      if (result.ok) {
        setLast(readCoordinatedRun(result.data));
        return;
      }
      refuse(result.failure, result.body, REQUEST_NOT_STARTED);
    })();
  };

  const linked = new Set(shown.callees.map((one) => one.agent_id));
  const choices = (agents?.entries ?? []).filter((one) => one.agentId !== agentId && !linked.has(one.agentId));
  return (
    <SectionCard title={SPECIALISTS_HEADING} lede={SPECIALISTS_LEDE} action={<Network aria-hidden className="size-4 text-dim" />}>
      <div data-slot="agent-specialists" className="flex min-w-0 flex-col gap-3">
        {refused === null ? null : (
          <FailureNotice
            failure={refused.failure}
            title={refused.title}
            {...(refused.sentence === undefined ? {} : { sentence: refused.sentence })}
          />
        )}
        {shown.switched_on ? null : <Explanation form="note" act="coordination.run_switched_off" />}
        {shown.callees.length === 0 ? (
          <EmptyList compact title={NO_SPECIALISTS} adds={NO_SPECIALISTS_ADDS} by={["super_admin", "department_admin"]} />
        ) : (
          <ul aria-label="Specialists this agent may hand a subtask to" className="m-0 flex list-none flex-col gap-2 p-0">
            {shown.callees.map((one) => (
              <li key={one.agent_id} className="flex min-w-0 flex-wrap items-center gap-2">
                <span className="min-w-0 font-medium text-ink [overflow-wrap:anywhere]">{one.display_name}</span>
                {shown.may_change ? (
                  <Button
                    size="sm"
                    variant="outline"
                    className="ml-auto min-h-11 sm:min-h-8"
                    aria-label={`Stop handing ${one.display_name} subtasks`}
                    disabled={sending}
                    onClick={() => {
                      setRefused(null);
                      setPending({ kind: "withdraw", id: one.agent_id, name: one.display_name });
                    }}
                  >
                    Withdraw
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
        {shown.may_change && choices.length > 0 ? (
          <div className="flex min-w-0 flex-wrap items-end gap-2">
            <div className="flex min-w-0 flex-col gap-1.5">
              <label htmlFor={chooserId} className="text-[13px] font-medium text-ink">
                {CHOOSE_A_SPECIALIST}
              </label>
              <NativeSelect id={chooserId} describedBy="" invalid={false} value={chosen} onChange={setChosen}>
                <option value="">{CHOOSE_A_SPECIALIST}</option>
                {choices.map((one) => (
                  <option key={one.agentId} value={one.agentId}>
                    {one.displayName}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <Button size="sm" className="min-h-11 sm:min-h-8" disabled={sending || chosen === ""} onClick={allow}>
              {ALLOW_IT}
            </Button>
          </div>
        ) : null}
        {shown.may_change ? (
          <>
            <div className="flex items-center justify-between gap-3 rounded-md border border-line px-3 py-2.5">
              <label htmlFor={`${askId}-fan`} className="text-[13px] text-ink">
                {FAN_OUT_LABEL}
              </label>
              <Switch
                id={`${askId}-fan`}
                aria-describedby={`${askId}-fan-state`}
                checked={shown.fan_out_enabled}
                disabled={sending}
                onCheckedChange={(on) => {
                  setRefused(null);
                  setPending({ kind: "fan-out", enabled: on });
                }}
              />
            </div>
            <div id={`${askId}-fan-state`}>
              <Note>{shown.fan_out_enabled ? FAN_OUT_ON : FAN_OUT_OFF}</Note>
            </div>
          </>
        ) : null}
        {shown.callees.length === 0 ? null : (
          <div className="flex min-w-0 flex-col gap-1.5">
            <label htmlFor={askId} className="text-[13px] font-medium text-ink">
              {ASK_LABEL}
            </label>
            <Textarea
              id={askId}
              rows={3}
              maxLength={4000}
              value={text}
              onChange={(event) => {
                setText(event.target.value);
              }}
            />
            <div>
              <Button size="sm" className="min-h-11 sm:min-h-8" disabled={asking || !shown.switched_on || text.trim() === ""} onClick={ask}>
                {asking ? "Running" : ASK_IT}
              </Button>
            </div>
          </div>
        )}
        {last === null ? null : <RunAnswer run={last} />}
        {shown.words === "" ? null : <Note>{shown.words}</Note>}
      </div>
      <ConfirmDialog
        open={pending !== null}
        question={
          pending === null
            ? ""
            : pending.kind === "withdraw"
              ? WITHDRAW_QUESTION(pending.name)
              : pending.enabled
                ? GRANT_FAN_OUT_QUESTION(name)
                : WITHDRAW_FAN_OUT_QUESTION(name)
        }
        consequence={
          pending === null
            ? ""
            : pending.kind === "withdraw"
              ? WITHDRAW_CONSEQUENCE
              : pending.enabled
                ? GRANT_FAN_OUT_CONSEQUENCE
                : WITHDRAW_FAN_OUT_CONSEQUENCE
        }
        confirmLabel={pending?.kind === "withdraw" ? "Withdraw it" : pending?.kind === "fan-out" && pending.enabled ? "Allow it" : "Stop it"}
        cancelLabel="Not now"
        busy={sending}
        onConfirm={confirm}
        onCancel={() => {
          setPending(null);
        }}
      />
    </SectionCard>
  );
}
