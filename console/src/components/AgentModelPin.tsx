/**
 * An agent's model on its profile: its tier, the pinned provider and model if any, and the form
 * that pins one or takes the pin off.
 *
 * Drawn for a reader the workspace gave a profile. The write is refused by
 * `brain.agent_model_routes` without the matrix write over everything, whatever this drew, and
 * goes through `components/ConfirmAction.tsx` because it moves every question to the agent.
 *
 * Task ids: M5.7.3
 */

import { useState, type FormEvent } from "react";
import { request } from "../api/client";
import type { ApiFailure, FieldProblem } from "../api/errors";
import { FailureNotice } from "../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../ui/FieldProblems";
import { ConfirmAction } from "./ConfirmAction";
import {
  blankPinProblems,
  CLEAR_PIN,
  KEEP_PIN,
  MODEL_HEADING,
  modelPinApiPath,
  PIN_MODEL,
  pinConsequence,
  pinnedSentence,
  pinQuestion,
  tierSentence,
  type ModelChoice,
} from "../pages/agentModelPinQuery";

const PIN_FORM = "model-pin";

export function AgentModelPin({ agentId, choice }: { readonly agentId: string; readonly choice: ModelChoice }) {
  const [shown, setShown] = useState<ModelChoice>(choice);
  const [provider, setProvider] = useState(choice.provider ?? "");
  const [model, setModel] = useState(choice.model ?? "");
  const [blank, setBlank] = useState<FieldProblem[]>([]);
  const [pending, setPending] = useState<{ provider: string | null; model: string | null } | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const problems = [...blank, ...(failure?.problems ?? [])];

  const send = (asked: { provider: string | null; model: string | null }) => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(modelPinApiPath(agentId), { method: "PUT", body: asked });
      setBusy(false);
      setPending(null);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      setShown({ ...shown, provider: asked.provider, model: asked.model });
    })();
  };

  const ask = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFailure(null);
    const found = blankPinProblems(provider, model);
    setBlank(found);
    if (found.length > 0) {
      return;
    }
    setPending({ provider: provider.trim(), model: model.trim() });
  };

  return (
    <section className="card" aria-labelledby="agent-model">
      <h2 id="agent-model">{MODEL_HEADING}</h2>
      <p>{tierSentence(shown)}</p>
      <p>{pinnedSentence(shown)}</p>
      {failure === null ? null : <FailureNotice failure={failure} />}
      {pending === null ? null : (
        <ConfirmAction
          question={pinQuestion(pending.provider, pending.model)}
          consequence={pinConsequence(pending.provider, pending.model)}
          confirmLabel={pending.provider === null ? CLEAR_PIN : PIN_MODEL}
          cancelLabel={KEEP_PIN}
          busy={busy}
          onConfirm={() => {
            send(pending);
          }}
          onCancel={() => {
            setPending(null);
          }}
        />
      )}
      <form className="form" aria-label="Pin a model for this agent" onSubmit={ask}>
        <label className="control-label">
          Provider{" "}
          <input
            className="form-control"
            type="text"
            name="provider"
            value={provider}
            {...problemAttributes(problems, PIN_FORM, ["provider", "model_pin"])}
            onChange={(event) => {
              setProvider(event.target.value);
            }}
          />
        </label>
        <FieldProblems problems={problems} form={PIN_FORM} names={["provider", "model_pin"]} />
        <label className="control-label">
          Model{" "}
          <input
            className="form-control"
            type="text"
            name="model"
            value={model}
            {...problemAttributes(problems, PIN_FORM, "model")}
            onChange={(event) => {
              setModel(event.target.value);
            }}
          />
        </label>
        <FieldProblems problems={problems} form={PIN_FORM} names="model" />
        <div className="form-actions">
          <button type="submit" className="button" disabled={busy}>
            {PIN_MODEL}
          </button>{" "}
          {shown.provider === null ? null : (
            <button
              type="button"
              className="button"
              disabled={busy}
              onClick={() => {
                setFailure(null);
                setPending({ provider: null, model: null });
              }}
            >
              {CLEAR_PIN}
            </button>
          )}
        </div>
      </form>
    </section>
  );
}
