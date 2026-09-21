/**
 * The Routing screen's half of the matrix gate: the changes it decided, the golden questions it
 * asks, and a rung added at the end of a tier.
 *
 * `matrixGateQuery.ts` holds the arguments. The two reads are made for every reader of the matrix,
 * and a reader the API refuses sees its refusal in its own words; the forms and buttons are drawn
 * only for a reader the matrix page says may change it, and every write here is refused by
 * `brain.routing_routes` without the matrix write over everything whatever this page drew.
 *
 * **Every write asks first.** Adding a golden question changes what every later change must pass,
 * retiring one removes a check, and adding a rung puts a provider on the chain if the gate passes
 * it, so each goes through `components/ConfirmAction.tsx` saying what happens and to what.
 *
 * Task ids: M5.6.2, M5.7.2
 */

import { useState, type FormEvent } from "react";
import { request } from "../api/client";
import type { ApiFailure, FieldProblem } from "../api/errors";
import { useResource } from "../api/useResource";
import { ConfirmAction } from "./ConfirmAction";
import { FailureNotice } from "../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../ui/FieldProblems";
import {
  ADD_GOLDEN,
  ADD_RUNG,
  ADD_RUNG_API_PATH,
  ADD_RUNG_HEADING,
  addGoldenConsequence,
  addGoldenQuestion,
  addRungConsequence,
  addRungQuestion,
  APPLIED,
  blankGoldenProblems,
  blankRungProblems,
  CHANGES_API_PATH,
  expectWords,
  GATE_HEADING,
  GATE_LEDE,
  GOLDEN_API_PATH,
  GOLDEN_HEADING,
  GOLDEN_LEDE,
  HELD,
  heldSentence,
  KEEP_GOLDEN,
  KEEP_LADDER,
  NO_CHANGES,
  NO_GOLDEN,
  readChange,
  readChanges,
  readGolden,
  RETIRE_GOLDEN,
  RETIRE_GOLDEN_CONSEQUENCE,
  retireGoldenApiPath,
  retireGoldenQuestion,
  TIERS,
  type ChangeRow,
  type GoldenAsked,
  type GoldenRow,
  type RungAsked,
} from "../pages/matrixGateQuery";

const GOLDEN_FORM = "golden";
const RUNG_FORM = "add-rung";

type Pending =
  | { readonly kind: "golden"; readonly asked: GoldenAsked }
  | { readonly kind: "retire"; readonly row: GoldenRow }
  | { readonly kind: "rung"; readonly asked: RungAsked };

/** One decided change: applied, or held with the cases that held it. Never an answer. */
export function ChangeDecided({ change }: { readonly change: ChangeRow }) {
  return (
    <div aria-label={`${change.status === "held" ? HELD : APPLIED} change`}>
      <p>
        <strong>{change.status === "held" ? HELD : APPLIED}</strong>{" "}
        <span className="note">
          {change.kind === "add" ? "a new rung" : "a rung edit"}, by <code>{change.proposed_by}</code>
        </span>
      </p>
      {change.status === "held" ? (
        <>
          <p>{heldSentence(change)}</p>
          {change.reasons.map((reason) => (
            <p key={reason} className="note">
              {reason}
            </p>
          ))}
          {change.failing.length === 0 ? null : (
            <ul aria-label="Failing cases">
              {change.failing.map((one) => (
                <li key={one.case}>
                  <code>{one.case}</code>: {one.reason}
                </li>
              ))}
            </ul>
          )}
        </>
      ) : null}
    </div>
  );
}

export function MatrixGate({
  version,
  editable,
  onChanged,
}: {
  readonly version: number;
  readonly editable: boolean;
  readonly onChanged: () => void;
}) {
  const changes = useResource<unknown>(CHANGES_API_PATH, version);
  const golden = useResource<unknown>(GOLDEN_API_PATH, version);
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [decided, setDecided] = useState<ChangeRow | null>(null);

  const [question, setQuestion] = useState("");
  const [askedAs, setAskedAs] = useState("");
  const [expect, setExpect] = useState<GoldenAsked["expect"]>("answer");
  const [goldenBlank, setGoldenBlank] = useState<FieldProblem[]>([]);

  const [tier, setTier] = useState<RungAsked["tier"]>("main");
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [attempts, setAttempts] = useState("1");
  const [timeout, setTimeoutSeconds] = useState("20");
  const [concurrency, setConcurrency] = useState("4");
  const [rungBlank, setRungBlank] = useState<FieldProblem[]>([]);

  const goldenProblems = [...goldenBlank, ...(failure?.problems ?? [])];
  const rungProblems = [...rungBlank, ...(failure?.problems ?? [])];

  const send = (asked: Pending) => {
    setBusy(true);
    void (async () => {
      const result =
        asked.kind === "golden"
          ? await request<unknown>(GOLDEN_API_PATH, { method: "POST", body: asked.asked })
          : asked.kind === "retire"
            ? await request<unknown>(retireGoldenApiPath(asked.row.id), { method: "POST" })
            : await request<unknown>(ADD_RUNG_API_PATH, { method: "POST", body: asked.asked });
      setBusy(false);
      setPending(null);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      if (asked.kind === "rung") {
        setDecided(readChange(result.data));
      }
      if (asked.kind === "golden") {
        setQuestion("");
        setAskedAs("");
      }
      onChanged();
    })();
  };

  const askGolden = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFailure(null);
    const found = blankGoldenProblems(question, askedAs);
    setGoldenBlank(found);
    if (found.length > 0) {
      return;
    }
    setPending({ kind: "golden", asked: { question: question.trim(), asked_as: askedAs.trim(), expect } });
  };

  const askRung = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFailure(null);
    const found = blankRungProblems(provider, model, [attempts, timeout, concurrency]);
    setRungBlank(found);
    if (found.length > 0) {
      return;
    }
    setPending({
      kind: "rung",
      asked: {
        tier,
        provider: provider.trim(),
        model: model.trim(),
        attempts: Number(attempts),
        timeout_seconds: Number(timeout),
        max_concurrency: Number(concurrency),
      },
    });
  };

  const changeRows = changes.data === null ? [] : readChanges(changes.data);
  const goldenRows = golden.data === null ? [] : readGolden(golden.data);

  return (
    <>
      <section className="card" aria-labelledby="matrix-gate">
        <h2 id="matrix-gate">{GATE_HEADING}</h2>
        <p className="note">{GATE_LEDE}</p>
        {failure === null ? null : <FailureNotice failure={failure} />}
        {decided === null ? null : (
          <div role="status">
            <ChangeDecided change={decided} />
          </div>
        )}
        {pending === null ? null : (
          <ConfirmAction
            question={
              pending.kind === "golden"
                ? addGoldenQuestion(pending.asked)
                : pending.kind === "retire"
                  ? retireGoldenQuestion(pending.row)
                  : addRungQuestion(pending.asked)
            }
            consequence={
              pending.kind === "golden"
                ? addGoldenConsequence(pending.asked)
                : pending.kind === "retire"
                  ? RETIRE_GOLDEN_CONSEQUENCE
                  : addRungConsequence(pending.asked)
            }
            confirmLabel={pending.kind === "golden" ? ADD_GOLDEN : pending.kind === "retire" ? RETIRE_GOLDEN : ADD_RUNG}
            cancelLabel={pending.kind === "rung" ? KEEP_LADDER : KEEP_GOLDEN}
            busy={busy}
            onConfirm={() => {
              send(pending);
            }}
            onCancel={() => {
              setPending(null);
            }}
          />
        )}
        {changes.failure !== null ? (
          <FailureNotice failure={changes.failure} />
        ) : changes.busy ? null : changeRows.length === 0 ? (
          <p className="note">{NO_CHANGES}</p>
        ) : (
          <ul aria-label="Recent changes">
            {changeRows.map((change) => (
              <li key={change.id}>
                <ChangeDecided change={change} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card" aria-labelledby="matrix-golden">
        <h2 id="matrix-golden">{GOLDEN_HEADING}</h2>
        <p className="note">{GOLDEN_LEDE}</p>
        {golden.failure !== null ? (
          <FailureNotice failure={golden.failure} />
        ) : golden.busy ? null : goldenRows.length === 0 ? (
          <p className="note">{NO_GOLDEN}</p>
        ) : (
          <div className="grid__scroll">
            <table className="grid__table">
              <caption className="grid__caption">The golden questions a matrix change is asked</caption>
              <thead>
                <tr>
                  <th scope="col">Question</th>
                  <th scope="col">Asked as</th>
                  <th scope="col">Expected</th>
                  {editable ? <th scope="col">Actions</th> : null}
                </tr>
              </thead>
              <tbody>
                {goldenRows.map((row) => (
                  <tr key={row.id}>
                    <td>{row.question}</td>
                    <td>
                      <code>{row.asked_as}</code>
                    </td>
                    <td>{expectWords(row.expect)}</td>
                    {!editable ? null : (
                    <td>
                      <button
                        type="button"
                        className="button"
                        disabled={busy}
                        aria-label={`${RETIRE_GOLDEN}: ${row.question}`}
                        onClick={() => {
                          setFailure(null);
                          setPending({ kind: "retire", row });
                        }}
                      >
                        {RETIRE_GOLDEN}
                      </button>
                    </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {!editable ? null : (
        <form className="form" aria-label="Add a golden question" onSubmit={askGolden}>
          <label className="control-label">
            Question{" "}
            <input
              className="form-control"
              type="text"
              name="question"
              value={question}
              {...problemAttributes(goldenProblems, GOLDEN_FORM, "question")}
              onChange={(event) => {
                setQuestion(event.target.value);
              }}
            />
          </label>
          <FieldProblems problems={goldenProblems} form={GOLDEN_FORM} names="question" />
          <label className="control-label">
            Asked as (principal id){" "}
            <input
              className="form-control"
              type="text"
              name="asked_as"
              value={askedAs}
              {...problemAttributes(goldenProblems, GOLDEN_FORM, "asked_as")}
              onChange={(event) => {
                setAskedAs(event.target.value);
              }}
            />
          </label>
          <FieldProblems problems={goldenProblems} form={GOLDEN_FORM} names="asked_as" />
          <label className="control-label">
            It must be{" "}
            <select
              className="form-control"
              name="expect"
              value={expect}
              onChange={(event) => {
                setExpect(event.target.value === "refuse" ? "refuse" : "answer");
              }}
            >
              <option value="answer">answered</option>
              <option value="refuse">refused</option>
            </select>
          </label>
          <div className="form-actions">
            <button type="submit" className="button" disabled={busy}>
              {ADD_GOLDEN}
            </button>
          </div>
        </form>
        )}
      </section>

      {!editable ? null : (
      <section className="card" aria-labelledby="matrix-add-rung">
        <h2 id="matrix-add-rung">{ADD_RUNG_HEADING}</h2>
        <form className="form" aria-label={ADD_RUNG_HEADING} onSubmit={askRung}>
          <label className="control-label">
            Tier{" "}
            <select
              className="form-control"
              name="tier"
              value={tier}
              onChange={(event) => {
                const chosen = TIERS.find((one) => one === event.target.value);
                setTier(chosen ?? "main");
              }}
            >
              {TIERS.map((one) => (
                <option key={one} value={one}>
                  {one}
                </option>
              ))}
            </select>
          </label>
          <label className="control-label">
            Provider{" "}
            <input
              className="form-control"
              type="text"
              name="provider"
              value={provider}
              {...problemAttributes(rungProblems, RUNG_FORM, "provider")}
              onChange={(event) => {
                setProvider(event.target.value);
              }}
            />
          </label>
          <FieldProblems problems={rungProblems} form={RUNG_FORM} names="provider" />
          <label className="control-label">
            Model{" "}
            <input
              className="form-control"
              type="text"
              name="model"
              value={model}
              {...problemAttributes(rungProblems, RUNG_FORM, "model")}
              onChange={(event) => {
                setModel(event.target.value);
              }}
            />
          </label>
          <FieldProblems problems={rungProblems} form={RUNG_FORM} names="model" />
          <label className="control-label">
            Attempts{" "}
            <input
              className="form-control"
              type="number"
              name="attempts"
              min={1}
              value={attempts}
              {...problemAttributes(rungProblems, RUNG_FORM, "attempts")}
              onChange={(event) => {
                setAttempts(event.target.value);
              }}
            />
          </label>
          <FieldProblems problems={rungProblems} form={RUNG_FORM} names="attempts" />
          <label className="control-label">
            Timeout in seconds{" "}
            <input
              className="form-control"
              type="number"
              name="timeout_seconds"
              min={1}
              value={timeout}
              {...problemAttributes(rungProblems, RUNG_FORM, "timeout_seconds")}
              onChange={(event) => {
                setTimeoutSeconds(event.target.value);
              }}
            />
          </label>
          <FieldProblems problems={rungProblems} form={RUNG_FORM} names="timeout_seconds" />
          <label className="control-label">
            At most at once{" "}
            <input
              className="form-control"
              type="number"
              name="max_concurrency"
              min={1}
              value={concurrency}
              {...problemAttributes(rungProblems, RUNG_FORM, "max_concurrency")}
              onChange={(event) => {
                setConcurrency(event.target.value);
              }}
            />
          </label>
          <FieldProblems problems={rungProblems} form={RUNG_FORM} names="max_concurrency" />
          <div className="form-actions">
            <button type="submit" className="button" disabled={busy}>
              {ADD_RUNG}
            </button>
          </div>
        </form>
      </section>
      )}
    </>
  );
}
