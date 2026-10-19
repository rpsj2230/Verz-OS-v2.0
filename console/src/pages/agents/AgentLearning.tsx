/**
 * The learning switch on an agent's Profile, and the confirmed act that pauses or resumes it
 * (M27.11.14).
 *
 * **It is the switch the server has had since M16.7.13, drawn.** `POST /agents/{id}/learning` pauses
 * or resumes what an agent's runs may teach, with a reason, in the caller's name. The Profile's
 * Learning card listed four tiers and said there is no single on and off switch, and that sentence
 * is still true of what the switch does not do: it cannot let anything be learnt unchecked, because
 * resuming only lets each tier go on doing what it already checks. It can only stop learning, so it
 * can only narrow what is kept, which is why the owner asked for it (needs-rupash 201, question 2).
 *
 * **It is drawn only for a reader the route answers.** The lifecycle authority over the agent's row
 * opens it, and anybody else is the one 404, so a reader refused draws no switch and no heading, and
 * a state of "on" is never inferred from the refusal.
 *
 * **Both directions go through `kit/ConfirmDialog` and each needs a reason**, written to the row. A
 * blank reason is said beside the field and sends nothing, and the dialog stays open until the route
 * has answered, so a refusal is read where the person is looking.
 *
 * Task ids: M27.11.14
 */

import { useId, useMemo, useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { ConfirmDialog, Note } from "../../components/kit";
import { Input } from "../../components/ui/input";
import { Switch } from "../../components/ui/switch";
import { FailureNotice } from "../../ui/FailureNotice";
import { agentLearningApiPath, learningBody, readLearning } from "./agentLearningQuery";

export const LEARNING_SWITCH_LABEL = "Let this agent learn from its conversations";
export const LEARNING_ON = "On: what its runs teach it can be kept, tier by tier as listed above.";
export const LEARNING_OFF = "Paused: nothing its runs teach it is kept until it is resumed. What it already learnt stays.";
export const PAUSE_QUESTION = (name: string): string => `Pause what ${name} learns?`;
export const RESUME_QUESTION = (name: string): string => `Let ${name} learn again?`;
export const PAUSE_CONSEQUENCE =
  "From its next turn nothing the agent's runs teach it is kept. What it already learnt stays, and so does every correction.";
export const RESUME_CONSEQUENCE =
  "From its next turn what its runs teach it can be kept again. Each tier still checks what it applies, and anything that would change who may see what still waits for a person.";
export const REASON_LABEL = "Why";
export const REASON_NEEDED = "Say why, in a few words, so the next person knows.";
export const LEARNING_NOT_CHANGED = "Nothing was changed";

export function AgentLearningSwitch({ agentId, name }: { readonly agentId: string; readonly name: string }) {
  const reasonId = useId();
  const [version, setVersion] = useState(0);
  const answer = useResource<unknown>(agentLearningApiPath(agentId), version);
  const shown = useMemo(() => (answer.data === null ? null : readLearning(answer.data)), [answer.data]);
  const [target, setTarget] = useState<boolean | null>(null);
  const [reason, setReason] = useState("");
  const [needed, setNeeded] = useState(false);
  const [sending, setSending] = useState(false);
  const [refused, setRefused] = useState<ApiFailure | null>(null);

  if (shown === null) {
    return null;
  }

  const confirm = () => {
    if (target === null) {
      return;
    }
    if (reason.trim() === "") {
      setNeeded(true);
      return;
    }
    const pausing = target;
    setSending(true);
    void (async () => {
      const result = await request<unknown>(agentLearningApiPath(agentId), {
        method: "POST",
        body: learningBody(pausing, reason),
      });
      setSending(false);
      if (result.ok) {
        setTarget(null);
        setReason("");
        setNeeded(false);
        setRefused(null);
        setVersion((count) => count + 1);
        return;
      }
      setTarget(null);
      setRefused(result.failure);
    })();
  };

  const switchId = `${reasonId}-switch`;
  return (
    <div data-slot="agent-learning-switch" className="flex min-w-0 flex-col gap-2">
      {refused === null ? null : <FailureNotice failure={refused} title={LEARNING_NOT_CHANGED} />}
      <div className="flex items-center justify-between gap-3 rounded-md border border-line px-3 py-2.5">
        <label htmlFor={switchId} className="text-[13px] text-ink">
          {LEARNING_SWITCH_LABEL}
        </label>
        <Switch
          id={switchId}
          aria-describedby={`${switchId}-state`}
          checked={!shown.paused}
          disabled={sending}
          onCheckedChange={(on) => {
            setRefused(null);
            setNeeded(false);
            setReason("");
            // Asking to turn it on is asking to resume, and off is asking to pause.
            setTarget(!on);
          }}
        />
      </div>
      <div id={`${switchId}-state`}>
        <Note>{shown.paused ? LEARNING_OFF : LEARNING_ON}</Note>
      </div>
      <ConfirmDialog
        open={target !== null}
        question={target === true ? PAUSE_QUESTION(name) : RESUME_QUESTION(name)}
        consequence={target === true ? PAUSE_CONSEQUENCE : RESUME_CONSEQUENCE}
        details={
          <div className="flex flex-col gap-1.5">
            <label htmlFor={reasonId} className="text-[13px] font-medium text-ink">
              {REASON_LABEL}
            </label>
            <Input
              id={reasonId}
              className="h-11 sm:h-9"
              autoComplete="off"
              value={reason}
              aria-invalid={needed ? true : undefined}
              onChange={(event) => {
                setReason(event.target.value);
                setNeeded(false);
              }}
            />
            {needed ? <span className="text-[12px] text-destructive">{REASON_NEEDED}</span> : null}
          </div>
        }
        confirmLabel={target === true ? "Pause it" : "Resume it"}
        cancelLabel="Not now"
        danger={target === true}
        busy={sending}
        onConfirm={confirm}
        onCancel={() => {
          setTarget(null);
        }}
      />
    </div>
  );
}
