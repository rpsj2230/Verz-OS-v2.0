/**
 * Switching an agent on and off, archiving, duplicating and handing it on, from the Agents list and
 * from an agent's own page, each a confirmed write.
 *
 * **Choosing an act asks the API first.** `GET /agents/{id}/lifecycle` answers with the agent's state,
 * its steward, the digest a copy must name and what this reader may do, and the confirmation is
 * drawn from that answer rather than from the row the menu was opened on, so the state a person
 * confirms is the state the write sends back. A reader the API says may not act is told so and no
 * confirmation opens; the route asks every question again whatever this page believed.
 *
 * **Every write goes through `kit/ConfirmDialog`**, which `tests/destructive-confirmed.test.ts`
 * follows from the call to its `onConfirm`. A copy's name and a new steward are typed inside the
 * confirmation, with no form, and a blank one is said beside the field and sends nothing. A refusal
 * is the API's own sentence: a page that went stale, an archived agent somebody tried to switch on,
 * a steward who cannot take it.
 *
 * **One hook for any number of agents**, because the list offers the acts on every row and must not
 * hold a dialog per row. The page renders `dialog` and `notice` once, and passes `choose` to its menus.
 *
 * Task ids: M27.11.6, M27.11.7
 */

import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { ConfirmDialog } from "../../components/kit";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { FailureNotice } from "../../ui/FailureNotice";
import { Notice } from "../../ui/Notice";
import {
  ACT_CONSEQUENCES,
  ACT_DONE,
  ACT_LABELS,
  actQuestion,
  agentLifecycleApiPath,
  agentMoveApiPath,
  MAY_NOT_CHANGE,
  moveBody,
  readLifecycle,
  readNotChanged,
  TYPED_LABELS,
  TYPED_MISSING,
  type AgentLifecycle,
  type LifecycleAct,
} from "../agentLifecycleQuery";

export const KEEP_LABEL = "Not now";
export const NOT_CHANGED = "Nothing was changed";
export const SOMETHING_DID_NOT_WORK = "Something did not work";
export const OPEN_THE_COPY = "Open the copy";

interface Chosen {
  readonly act: LifecycleAct;
  readonly shown: AgentLifecycle;
}

interface Told {
  readonly title: string;
  readonly sentence: string;
  readonly to?: string;
}

interface Refused {
  readonly failure: ApiFailure;
  readonly title: string;
  readonly sentence?: string;
}

export interface LifecycleActs {
  /** Open an act on one agent: asks the API what this reader may do, then confirms. */
  readonly choose: (agentId: string, act: LifecycleAct) => void;
  /** True while an act is being asked about or sent, so a menu can hold its items still. */
  readonly busy: boolean;
  /** The confirmation. Rendered once by the page. */
  readonly dialog: ReactNode;
  /** What happened last, or why nothing did. Rendered once by the page. */
  readonly notice: ReactNode;
}

/** The copy's address, from the new agent the API made. */
function createdAddress(payload: unknown, addressOf: (agentId: string) => string): string | undefined {
  if (typeof payload !== "object" || payload === null) {
    return undefined;
  }
  // A cast at the boundary: the one field read is checked to be a non-blank string.
  const agent = (payload as { agent?: { agent_id?: unknown } }).agent;
  const agentId = agent?.agent_id;
  return typeof agentId === "string" && agentId !== "" ? addressOf(agentId) : undefined;
}

export function useLifecycleActs(onChanged: () => void, addressOf: (agentId: string) => string): LifecycleActs {
  const [chosen, setChosen] = useState<Chosen | null>(null);
  const [asking, setAsking] = useState(false);
  const [sending, setSending] = useState(false);
  const [typed, setTyped] = useState("");
  const [missing, setMissing] = useState<string | null>(null);
  const [told, setTold] = useState<Told | null>(null);
  const [refused, setRefused] = useState<Refused | null>(null);

  const choose = (agentId: string, act: LifecycleAct) => {
    setTold(null);
    setRefused(null);
    setAsking(true);
    void (async () => {
      const answer = await request<unknown>(agentLifecycleApiPath(agentId));
      setAsking(false);
      if (!answer.ok) {
        setRefused({ failure: answer.failure, title: SOMETHING_DID_NOT_WORK });
        return;
      }
      const shown = readLifecycle(answer.data);
      if (shown === null) {
        return;
      }
      const allowed = act === "duplicate" ? shown.mayDuplicate : shown.mayChange;
      if (!allowed) {
        setTold({
          title: NOT_CHANGED,
          sentence: act === "duplicate" ? (shown.duplicateUnavailable ?? MAY_NOT_CHANGE) : MAY_NOT_CHANGE,
        });
        return;
      }
      setTyped("");
      setMissing(null);
      setChosen({ act, shown });
    })();
  };

  const confirm = () => {
    if (chosen === null) {
      return;
    }
    const { act, shown } = chosen;
    const blank = TYPED_MISSING[act];
    if (blank !== undefined && typed.trim() === "") {
      setMissing(blank);
      return;
    }
    setSending(true);
    void (async () => {
      const path = agentMoveApiPath(shown.agentId, act);
      const result = await request<unknown>(path, { method: "POST", body: moveBody(act, shown, typed) });
      setSending(false);
      setChosen(null);
      if (result.ok) {
        const to = act === "duplicate" ? createdAddress(result.data, addressOf) : undefined;
        setTold({ title: ACT_DONE[act], sentence: shown.displayName, ...(to === undefined ? {} : { to }) });
        onChanged();
        return;
      }
      const notChanged = result.failure.status === 409 ? readNotChanged(result.body) : null;
      setRefused(
        notChanged === null
          ? { failure: result.failure, title: SOMETHING_DID_NOT_WORK }
          : { failure: result.failure, title: NOT_CHANGED, sentence: notChanged.sentence },
      );
    })();
  };

  const field = chosen === null ? undefined : TYPED_LABELS[chosen.act];
  const fieldId = "lifecycle-typed";
  const dialog = (
    <ConfirmDialog
      open={chosen !== null}
      question={chosen === null ? "" : actQuestion(chosen.act, chosen.shown.displayName)}
      consequence={chosen === null ? "" : ACT_CONSEQUENCES[chosen.act]}
      details={
        field === undefined ? undefined : (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={fieldId}>{field}</Label>
            <Input
              id={fieldId}
              value={typed}
              aria-invalid={missing !== null}
              {...(missing === null ? {} : { "aria-describedby": `${fieldId}-missing` })}
              onChange={(event) => {
                setTyped(event.target.value);
                setMissing(null);
              }}
            />
            {missing === null ? null : (
              <p id={`${fieldId}-missing`} className="text-[12px] text-danger-text">
                {missing}
              </p>
            )}
          </div>
        )
      }
      confirmLabel={chosen === null ? "" : ACT_LABELS[chosen.act]}
      cancelLabel={KEEP_LABEL}
      busy={sending}
      onConfirm={confirm}
      onCancel={() => {
        setChosen(null);
      }}
    />
  );

  const notice =
    refused !== null ? (
      <FailureNotice
        failure={refused.failure}
        title={refused.title}
        {...(refused.sentence === undefined ? {} : { sentence: refused.sentence })}
      />
    ) : told !== null ? (
      <Notice title={told.title}>
        <p>
          {told.sentence}
          {told.to === undefined ? null : (
            <>
              {" "}
              <Link to={told.to}>{OPEN_THE_COPY}</Link>
            </>
          )}
        </p>
      </Notice>
    ) : null;

  return { choose, busy: asking || sending, dialog, notice };
}
