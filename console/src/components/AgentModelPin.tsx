/**
 * An agent's model on its profile: its level, the order a question to it tries models, and the
 * form that pins one or takes the pin off.
 *
 * Drawn for a reader the workspace gave a profile. The order and the choices are read from the
 * failover matrix (`GET /routing/rungs`), and a reader the matrix refuses sees the level and the
 * pin in words with the refusal where the order would be. The write is refused by
 * `brain.agent_model_routes` without the matrix write over everything, whatever this drew, and
 * goes through `components/ConfirmAction.tsx` because it moves every question to the agent.
 * `pages/agentModelPinQuery.ts` holds the arguments.
 *
 * Task ids: M5.7.3
 */

import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { request } from "../api/client";
import type { ApiFailure, FieldProblem } from "../api/errors";
import { useResource } from "../api/useResource";
import { Badge } from "../ui/Badge";
import { FailureNotice } from "../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../ui/FieldProblems";
import { ConfirmAction } from "./ConfirmAction";
import {
  agentSteps,
  blankPinProblems,
  CHOOSE_A_MODEL,
  CLEAR_PIN,
  FAILOVER_MATRIX_LINK,
  KEEP_PIN,
  levelSentence,
  MODEL_HEADING,
  modelPinApiPath,
  NOTHING_TO_PIN,
  PIN_LABEL,
  PIN_MODEL,
  pinChoices,
  pinConsequence,
  pinnedSentence,
  pinQuestion,
  STEPS_CAPTION,
  STEPS_EDITED_THERE,
  type ModelChoice,
} from "../pages/agentModelPinQuery";
import { chainApiPath, MATRIX_PATH, readMatrixPage } from "../pages/matrixQuery";
import { LEVEL_NAMES } from "../pages/modelsQuery";

const PIN_FORM = "model-pin";

export function AgentModelPin({ agentId, choice }: { readonly agentId: string; readonly choice: ModelChoice }) {
  const ladder = useResource<unknown>(chainApiPath());
  const [shown, setShown] = useState<ModelChoice>(choice);
  const [chosen, setChosen] = useState("");
  const [blank, setBlank] = useState<FieldProblem[]>([]);
  const [pending, setPending] = useState<{ provider: string | null; model: string | null } | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const problems = [...blank, ...(failure?.problems ?? [])];

  const rungs = ladder.data === null ? [] : readMatrixPage(ladder.data).rungs;
  const choices = pinChoices(rungs, Object.keys(LEVEL_NAMES));
  const steps = agentSteps(shown, rungs);

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
    const found = blankPinProblems(chosen);
    setBlank(found);
    const picked = choices[Number(chosen)];
    if (found.length > 0 || picked === undefined) {
      return;
    }
    setPending({ provider: picked.provider, model: picked.model });
  };

  return (
    <section className="card" aria-labelledby="agent-model">
      <h2 id="agent-model">{MODEL_HEADING}</h2>
      <p>{levelSentence(shown)}</p>
      <p>{pinnedSentence(shown)}</p>
      {ladder.busy ? (
        <p className="note" role="status">
          Loading.
        </p>
      ) : ladder.failure !== null ? (
        <FailureNotice failure={ladder.failure} />
      ) : (
        <>
          {steps.length === 0 ? null : (
            <div className="grid__scroll">
              <table className="grid__table">
                <caption className="grid__caption">{STEPS_CAPTION}</caption>
                <thead>
                  <tr>
                    <th scope="col">Step</th>
                    <th scope="col">Provider</th>
                    <th scope="col">Model</th>
                    <th scope="col">Role</th>
                  </tr>
                </thead>
                <tbody>
                  {steps.map((row) => (
                    <tr key={row.key}>
                      <td className="matrix__step">{String(row.step)}</td>
                      <td>{row.provider}</td>
                      <td>
                        <code>{row.model}</code>
                      </td>
                      <td>
                        <span className="note">{row.role}</span>
                        {row.note === null ? null : (
                          <>
                            {" "}
                            <Badge label={row.note} tone="caution" />
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="note">
            {STEPS_EDITED_THERE} <Link to={MATRIX_PATH}>{FAILOVER_MATRIX_LINK}</Link>.
          </p>
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
          {choices.length === 0 ? (
            <>
              <p className="note">{NOTHING_TO_PIN}</p>
              {shown.provider === null ? null : (
                <p>
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
                </p>
              )}
            </>
          ) : (
            <form className="form" aria-label="Pin a model for this agent" onSubmit={ask}>
              <label className="control-label">
                {PIN_LABEL}{" "}
                <select
                  className="form-control"
                  name="model_pin"
                  value={chosen}
                  {...problemAttributes(problems, PIN_FORM, ["model_pin", "provider", "model"])}
                  onChange={(event) => {
                    setChosen(event.target.value);
                  }}
                >
                  <option value="">{CHOOSE_A_MODEL}</option>
                  {choices.map((one, index) => (
                    <option key={`${one.provider} ${one.model}`} value={String(index)}>
                      {one.label}
                    </option>
                  ))}
                </select>
              </label>
              <FieldProblems problems={problems} form={PIN_FORM} names={["model_pin", "provider", "model"]} />
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
          )}
        </>
      )}
    </section>
  );
}
