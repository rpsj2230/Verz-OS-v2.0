/**
 * An agent's leash on its Profile: each entry's rung with a control to change it, every move with
 * its evidence, the supervision pin and its review, and the actions waiting for somebody to say what
 * they would have done.
 *
 * **Every control is offered only where the API said so, and every write is confirmed.** A rung is
 * changed by a holder of the department's leash role (`mayMove`); a lowering takes effect at once and
 * the dialog says so, a rise is judged on the agent's record by the API and may come back as a
 * proposal waiting for a second person, in the API's own words. A verdict is the steward's or a leash
 * holder's (`mayJudge`), and the dialog says a verdict can trip the rung.
 *
 * **Nothing here decides anything.** The rungs, the evidence, who may press and whether a rise is
 * allowed are the route's; a refusal is shown in the sentence the route sent.
 *
 * Task ids: M39.3.2.1, M39.3.2.2, M39.3.2.3, M39.3.2.4, M39.3.2.5, M39.8.2
 */

import { useId, useState } from "react";
import { request } from "../../api/client";
import { useResource } from "../../api/useResource";
import { ConfirmDialog, FailureState, LoadingState, Note } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Label } from "../../components/ui/label";
import { dayWords } from "../access/formParts";
import { rungWords } from "./agentActions";
import {
  MOVE_WORDS,
  PIN_WORDS,
  VERDICT_WORDS,
  agentLeashApiPath,
  leashMoveApiPath,
  percent,
  readAgentLeash,
  supervisionApiPath,
  takeoverWords,
  type AwaitingShown,
  type LeashEntryShown,
  type LeashScope,
} from "./agentLeashQuery";

export const LOADING_LEASH = "Loading how much a person sees before this agent acts.";
export const NO_MOVES = "No setting has moved since it was installed.";
export const RUNG_CHOICES = ["shadow", "assisted", "autonomous"] as const;

type Asking =
  | { readonly kind: "move"; readonly setting: Settable; readonly to: string }
  | { readonly kind: "verdict"; readonly action: AwaitingShown; readonly verdict: string }
  | { readonly kind: "pin" }
  | { readonly kind: "review" };

const CONTROL = "h-8 min-w-0 rounded-md border border-input bg-transparent px-2 text-[12.5px] text-ink";

/** One thing a rung can be set on: an entry as it stands, or an action nothing names yet. */
interface Settable {
  readonly key: string;
  readonly target: string;
  readonly scope: LeashScope;
  readonly rung: string;
  readonly label: string;
  /** The lower rung the autonomy breaker holds it to; the lower one is what binds. */
  readonly loweredTo?: string;
}

function settables(entries: readonly LeashEntryShown[], unnamed: readonly string[]): Settable[] {
  const named = entries.map((one) => ({
    key: `${one.target}|${JSON.stringify(one.scope)}`,
    target: one.target,
    scope: one.scope,
    rung: one.rung,
    label: one.where === "" ? one.target : `${one.target}, ${one.where}`,
    ...(one.loweredTo === undefined ? {} : { loweredTo: one.loweredTo }),
  }));
  const bare = unnamed
    .filter((target) => !entries.some((one) => one.target === target && one.scope.clauses.length === 0))
    .map((target) => ({ key: `${target}|{}`, target, scope: { clauses: [] }, rung: "shadow", label: target }));
  return [...named, ...bare];
}

function ChangeForm({ choices, onAsk }: { readonly choices: readonly Settable[]; readonly onAsk: (asking: Asking) => void }) {
  const id = useId();
  const [picked, setPicked] = useState(choices[0]?.key ?? "");
  const chosen = choices.find((one) => one.key === picked) ?? choices[0];
  const [to, setTo] = useState(chosen?.rung ?? "shadow");
  if (chosen === undefined) {
    return null;
  }
  return (
    <form
      data-slot="leash-change"
      className="flex flex-wrap items-end gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (to !== chosen.rung) {
          onAsk({ kind: "move", setting: chosen, to });
        }
      }}
    >
      <div className="flex min-w-0 flex-col gap-1">
        <Label htmlFor={`${id}-what`}>Setting</Label>
        <select
          id={`${id}-what`}
          className={CONTROL}
          value={chosen.key}
          onChange={(event) => {
            setPicked(event.target.value);
            setTo(choices.find((one) => one.key === event.target.value)?.rung ?? "shadow");
          }}
        >
          {choices.map((one) => (
            <option key={one.key} value={one.key}>
              {one.loweredTo === undefined
                ? `${one.label} (${rungWords(one.rung)})`
                : `${one.label} (${rungWords(one.rung)}, held at ${rungWords(one.loweredTo)} for now)`}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor={`${id}-to`}>Change to</Label>
        <select id={`${id}-to`} className={CONTROL} value={to} onChange={(event) => setTo(event.target.value)}>
          {RUNG_CHOICES.map((one) => (
            <option key={one} value={one}>
              {rungWords(one)}
            </option>
          ))}
        </select>
      </div>
      <Button type="submit" size="xs" variant="outline" disabled={to === chosen.rung}>
        Change
      </Button>
    </form>
  );
}

function AwaitingRow({ action, onAsk }: { readonly action: AwaitingShown; readonly onAsk: (asking: Asking) => void }) {
  const id = useId();
  const [verdict, setVerdict] = useState("approved");
  return (
    <li data-slot="leash-awaiting" className="flex flex-wrap items-end gap-2 border-b border-line py-2 text-[12.5px] last:border-b-0">
      <span className="min-w-0 text-ink [overflow-wrap:anywhere]">{action.target}</span>
      <span className="text-dim">{dayWords(action.at)}</span>
      <form
        className="ml-auto flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          onAsk({ kind: "verdict", action, verdict });
        }}
      >
        <div className="flex flex-col gap-1">
          <Label htmlFor={id}>What you would have done</Label>
          <select id={id} className={CONTROL} value={verdict} onChange={(event) => setVerdict(event.target.value)}>
            {Object.entries(VERDICT_WORDS).map(([key, words]) => (
              <option key={key} value={key}>
                {words}
              </option>
            ))}
          </select>
        </div>
        <Button type="submit" size="xs" variant="outline">
          Record
        </Button>
      </form>
    </li>
  );
}

export function AgentLeash({ agentId, unnamed }: { readonly agentId: string; readonly unnamed: readonly string[] }) {
  const [version, setVersion] = useState(0);
  const answer = useResource<unknown>(agentLeashApiPath(agentId), version);
  const [asking, setAsking] = useState<Asking | null>(null);
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<string | null>(null);

  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  const leash = answer.data === null ? null : readAgentLeash(answer.data);
  if (answer.busy || leash === null) {
    return <LoadingState label={LOADING_LEASH} />;
  }

  const decide = async (one: Asking): Promise<void> => {
    setBusy(true);
    const result =
      one.kind === "move"
        ? await request<unknown>(leashMoveApiPath(agentId), {
            method: "POST",
            body: { target: one.setting.target, scope: one.setting.scope, to: one.to },
          })
        : one.kind === "verdict"
          ? await request<unknown>(supervisionApiPath(agentId, "verdicts"), {
              method: "POST",
              body: { action_digest: one.action.actionDigest, verdict: one.verdict },
            })
          : await request<unknown>(supervisionApiPath(agentId, one.kind), { method: "POST" });
    setBusy(false);
    setAsking(null);
    setSaid(result.ok ? null : result.failure.message);
    setVersion((count) => count + 1);
  };

  const supervision = leash.supervision;
  const order: readonly string[] = RUNG_CHOICES;
  const lowering = asking?.kind === "move" && order.indexOf(asking.to) < order.indexOf(asking.setting.rung);
  const proposals = leash.entries.filter((one) => one.proposed !== undefined);
  return (
    <div data-slot="agent-leash" className="flex min-w-0 flex-col gap-3">
      {said === null ? null : (
        <p role="alert" className="m-0 text-[12.5px] text-crit">
          {said}
        </p>
      )}
      {leash.mayMove ? <ChangeForm choices={settables(leash.entries, unnamed)} onAsk={setAsking} /> : null}
      {proposals.map((one) => (
        <span key={`${one.target}-${JSON.stringify(one.scope)}`} data-slot="leash-proposal" className="text-[11.5px] text-warn">
          {`A rise of ${one.target} to ${rungWords(one.proposed ?? "")} is waiting for a second person.`}
        </span>
      ))}
      <div data-slot="leash-supervision" className="flex flex-col gap-1.5 text-[12.5px]">
        {supervision === undefined ? (
          leash.mayMove ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-dim">Not under supervision.</span>
              <Button size="xs" variant="outline" onClick={() => setAsking({ kind: "pin" })}>
                Supervise it
              </Button>
            </div>
          ) : null
        ) : (
          <>
            <span className="text-ink">{PIN_WORDS[supervision.outcome] ?? supervision.outcome}</span>
            <span className="text-dim">
              {`Since ${dayWords(supervision.pinnedAt)}; next review ${dayWords(supervision.reviewDueAt)}.`}
              {supervision.reviewed === undefined || supervision.understood === undefined
                ? ""
                : ` Last review: ${String(supervision.understood)} of ${String(supervision.reviewed)} judged actions accepted unchanged.`}
            </span>
            {supervision.held ? <Note kind="not-yet">every action it takes only practises until a review finds it ready.</Note> : null}
            {leash.mayMove && supervision.held && supervision.due ? (
              <div>
                <Button size="xs" variant="outline" onClick={() => setAsking({ kind: "review" })}>
                  Review it now
                </Button>
              </div>
            ) : null}
          </>
        )}
      </div>
      {leash.awaiting.length === 0 ? null : (
        <div>
          <h3 className="m-0 mb-1 text-[13px] font-medium text-ink">Waiting for somebody to say what they would have done</h3>
          <ul className="m-0 flex list-none flex-col p-0">
            {leash.awaiting.map((one) => (
              <AwaitingRow key={one.actionDigest} action={one} onAsk={setAsking} />
            ))}
          </ul>
        </div>
      )}
      <div>
        <h3 className="m-0 mb-1 text-[13px] font-medium text-ink">Every change</h3>
        {leash.history.length === 0 ? (
          <Note>{NO_MOVES}</Note>
        ) : (
          <ol data-slot="leash-history" className="m-0 flex list-none flex-col p-0">
            {leash.history.map((one) => (
              <li key={`${one.target}-${one.at}-${one.kind}`} className="flex flex-col gap-0.5 border-b border-line py-1.5 text-[12.5px] last:border-b-0">
                <span className="text-ink">
                  {`${MOVE_WORDS[one.kind] ?? one.kind}: ${one.target} from ${rungWords(one.was)} to ${rungWords(one.became)}`}
                  <span className="text-dim">{` · ${dayWords(one.at)}`}</span>
                </span>
                {one.cleanRuns === undefined || one.agreementRate === undefined ? null : (
                  <span className="text-dim">
                    {`${String(one.cleanRuns)} actions in a row accepted unchanged, ${percent(one.agreementRate)} overall`}
                    {one.approver === "" ? "" : `; approved by ${one.approver}`}
                    {one.secondApprover === "" ? "" : ` and ${one.secondApprover}`}
                  </span>
                )}
                {one.takeovers === undefined ? null : <span className="text-dim">{takeoverWords(one.takeovers, one.threshold)}</span>}
                {one.metric === "" || one.measured === undefined || one.threshold === undefined ? null : (
                  <span className="text-dim">{`${one.metric} was ${percent(one.measured)}, below ${percent(one.threshold)}`}</span>
                )}
              </li>
            ))}
          </ol>
        )}
      </div>
      <ConfirmDialog
        open={asking !== null}
        question={
          asking?.kind === "move"
            ? `Change ${asking.setting.target} to ${rungWords(asking.to)}?`
            : asking?.kind === "verdict"
              ? "Record what you would have done?"
              : asking?.kind === "pin"
                ? "Put this agent under supervision?"
                : "Review its supervision now?"
        }
        consequence={
          asking?.kind === "move"
            ? lowering
              ? "It takes effect at once, and the change is on the audit log."
              : "It rises only if its record meets the bar, and an action touching money needs a second person. The change is on the audit log."
            : asking?.kind === "verdict"
              ? "It counts towards its record, and a verdict below the bar can put a raised setting back to Shadow at once."
              : asking?.kind === "pin"
                ? "Every action it takes only practises until a review, thirty days from now, finds it ready."
                : "Below the bar the supervision extends by thirty days; at the bar it is found ready, and a person still decides any rise."
        }
        confirmLabel={asking?.kind === "move" ? "Change" : asking?.kind === "verdict" ? "Record" : asking?.kind === "pin" ? "Supervise" : "Review"}
        cancelLabel="Leave it"
        danger={asking?.kind === "move" && !lowering}
        busy={busy}
        onConfirm={() => {
          if (asking !== null) {
            void decide(asking);
          }
        }}
        onCancel={() => setAsking(null)}
      />
    </div>
  );
}
