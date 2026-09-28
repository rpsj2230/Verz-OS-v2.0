/**
 * The Routing screen's half of the matrix gate: the changes it decided, the golden questions it
 * asks, and a step added at the end of a level.
 *
 * `matrixGateQuery.ts` holds the arguments. The two reads are made for every reader of the matrix,
 * and a reader the API refuses sees its refusal in its own words; the forms and buttons are drawn
 * only for a reader the matrix page says may change it, and every write here is refused by
 * `brain.routing_routes` without the matrix write over everything whatever this page drew.
 *
 * **Every write asks first.** Adding a golden question changes what every later change must pass,
 * retiring one removes a check, and adding a step puts a provider on the matrix if the checks pass
 * it, so each goes through `components/ConfirmAction.tsx` saying what happens and to what.
 *
 * **A held change says why and what to do, where it was made** (the owner, 2026-09-28): the reason
 * in a sentence, what counts as an answered golden question, and the three steps that get a change
 * through, with the raw cases and reasons kept under Details. `HeldExplanation` is that block, and
 * the Routing page draws it above the matrix for a save it just made as well as here.
 *
 * **Every input is named by its label** through `htmlFor` and an id, and carries a `name`: the
 * owner's audit on 2026-09-28 found the Add form's inputs had no accessible name.
 *
 * Task ids: M5.6.2, M5.7.2
 */

import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { request } from "../api/client";
import type { ApiFailure, FieldProblem } from "../api/errors";
import { useResource, type Resource } from "../api/useResource";
import { ConfirmAction } from "./ConfirmAction";
import { FailureNotice } from "../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../ui/FieldProblems";
import { KNOWLEDGE_PATH } from "../pages/knowledgeQuery";
import { levelName } from "../pages/modelsQuery";
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
  ASKED_AS_LABEL,
  askedAsWords,
  ASKERS_API_PATH,
  blankGoldenProblems,
  blankRungProblems,
  caseReasonWords,
  caseWords,
  CHANGES_API_PATH,
  CHOOSE_A_PERSON,
  DETAILS,
  expectWords,
  GATE_HEADING,
  GATE_LEDE,
  GOLDEN_API_PATH,
  GOLDEN_COUNTS_WHEN,
  GOLDEN_HEADING,
  GOLDEN_LEDE,
  HELD,
  heldSentence,
  heldWhy,
  HOW_TO_PASS,
  KEEP_GOLDEN,
  KEEP_LADDER,
  MORE_PEOPLE,
  needsGoldenSteps,
  NO_CHANGES,
  NO_GOLDEN,
  NOBODY_LISTED,
  readAskers,
  readChange,
  readChanges,
  readGolden,
  RETIRE_GOLDEN,
  RETIRE_GOLDEN_CONSEQUENCE,
  retireGoldenApiPath,
  retireGoldenQuestion,
  STEPS_TO_PASS,
  TIERS,
  type ChangeRow,
  type GoldenAsked,
  type GoldenRow,
  type RungAsked,
} from "../pages/matrixGateQuery";

const GOLDEN_FORM = "golden";
const RUNG_FORM = "add-rung";

type Pending =
  | { readonly kind: "golden"; readonly asked: GoldenAsked; readonly name: string }
  | { readonly kind: "retire"; readonly row: GoldenRow }
  | { readonly kind: "rung"; readonly asked: RungAsked };

/**
 * What counts as an answered golden question, and the three steps that get a change through.
 * Drawn wherever a change can be held or is held, so the rule is never met without its way out.
 */
export function StepsToPass() {
  return (
    <div aria-label={HOW_TO_PASS}>
      <p className="note">{GOLDEN_COUNTS_WHEN}</p>
      <p className="note">{HOW_TO_PASS}</p>
      <ol>
        {STEPS_TO_PASS.map((step, index) => (
          <li key={step}>
            {index === 0 ? (
              <>
                {step} <Link to={KNOWLEDGE_PATH}>Open Knowledge</Link>
              </>
            ) : (
              step
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

/**
 * Why a held change was held, in plain words, the steps when a golden question is what held it,
 * and the raw cases and reasons under Details.
 */
export function HeldExplanation({
  change,
  golden = [],
  goldenCount = null,
}: {
  readonly change: ChangeRow;
  readonly golden?: readonly GoldenRow[];
  /** How many golden questions are recorded now, or null where the page does not know. */
  readonly goldenCount?: number | null;
}) {
  return (
    <>
      <p>{heldSentence(change)}</p>
      <p>{heldWhy(change, goldenCount)}</p>
      {change.failing.length === 0 ? null : (
        <ul aria-label="What failed">
          {change.failing.map((one) => (
            <li key={one.case}>
              {caseWords(one.case, golden)}: {caseReasonWords(one.reason)}
            </li>
          ))}
        </ul>
      )}
      {needsGoldenSteps(change) ? <StepsToPass /> : null}
      <details>
        <summary>{DETAILS}</summary>
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
      </details>
    </>
  );
}

/** One decided change: applied, or held with why and what to do. Never an answer. */
export function ChangeDecided({
  change,
  golden = [],
  goldenCount = null,
}: {
  readonly change: ChangeRow;
  readonly golden?: readonly GoldenRow[];
  readonly goldenCount?: number | null;
}) {
  return (
    <div aria-label={`${change.status === "held" ? HELD : APPLIED} change`}>
      <p>
        <strong>{change.status === "held" ? HELD : APPLIED}</strong>{" "}
        <span className="note">
          {change.kind === "add" ? "a new step" : "a change to a step"}, by <code>{change.proposed_by}</code>
        </span>
      </p>
      {change.status === "held" ? <HeldExplanation change={change} golden={golden} goldenCount={goldenCount} /> : null}
    </div>
  );
}

export function MatrixGate({
  version,
  golden,
  editable,
  onChanged,
}: {
  readonly version: number;
  /** The golden questions, read once by the page for this card and the held change above it. */
  readonly golden: Resource<unknown>;
  readonly editable: boolean;
  readonly onChanged: () => void;
}) {
  const changes = useResource<unknown>(CHANGES_API_PATH, version);
  // The people are asked for only where the form that lists them is drawn.
  const askers = useResource<unknown>(editable ? ASKERS_API_PATH : null, version);
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [decided, setDecided] = useState<ChangeRow | null>(null);
  // Fixed ids, one gate per page: two mounts draw the same markup, which the tests compare.
  const field = (form: string, name: string) => `matrix-gate-${form}-${name}`;

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

  const people = askers.data === null ? [] : readAskers(askers.data);
  const peopleCut =
    typeof askers.data === "object" && askers.data !== null && (askers.data as { truncated?: unknown }).truncated === true;

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
    const chosen = people.find((one) => one.id === askedAs);
    setPending({
      kind: "golden",
      asked: { question: question.trim(), asked_as: askedAs.trim(), expect },
      name: chosen?.name ?? askedAs.trim(),
    });
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
  // Known only once the list has answered; until then a held change does not claim there are none.
  const goldenCount = golden.data === null || golden.failure !== null ? null : goldenRows.length;

  return (
    <>
      <section className="card" aria-labelledby="matrix-gate">
        <h2 id="matrix-gate">{GATE_HEADING}</h2>
        <p className="note">{GATE_LEDE}</p>
        {failure === null ? null : <FailureNotice failure={failure} />}
        {decided === null ? null : (
          <div role="status">
            <ChangeDecided change={decided} golden={goldenRows} goldenCount={goldenCount} />
          </div>
        )}
        {pending === null ? null : (
          <ConfirmAction
            question={
              pending.kind === "golden"
                ? addGoldenQuestion(pending.name)
                : pending.kind === "retire"
                  ? retireGoldenQuestion(pending.row)
                  : addRungQuestion(pending.asked)
            }
            consequence={
              pending.kind === "golden"
                ? addGoldenConsequence(pending.asked, pending.name)
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
                <ChangeDecided change={change} golden={goldenRows} goldenCount={goldenCount} />
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
          <>
            <p className="note">{NO_GOLDEN}</p>
            <StepsToPass />
          </>
        ) : (
          <div className="grid__scroll">
            <table className="grid__table">
              <caption className="grid__caption">The golden questions a change to the failover matrix is asked</caption>
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
                    <td>{askedAsWords(row)}</td>
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
            <label className="control-label" htmlFor={field(GOLDEN_FORM, "question")}>
              Question
            </label>
            <input
              id={field(GOLDEN_FORM, "question")}
              className="form-control"
              type="text"
              name="question"
              value={question}
              {...problemAttributes(goldenProblems, GOLDEN_FORM, "question")}
              onChange={(event) => {
                setQuestion(event.target.value);
              }}
            />
            <FieldProblems problems={goldenProblems} form={GOLDEN_FORM} names="question" />
            <label className="control-label" htmlFor={field(GOLDEN_FORM, "asked_as")}>
              {ASKED_AS_LABEL}
            </label>
            {askers.failure !== null ? <FailureNotice failure={askers.failure} /> : null}
            <select
              id={field(GOLDEN_FORM, "asked_as")}
              className="form-control"
              name="asked_as"
              value={askedAs}
              {...problemAttributes(goldenProblems, GOLDEN_FORM, "asked_as")}
              onChange={(event) => {
                setAskedAs(event.target.value);
              }}
            >
              <option value="">{CHOOSE_A_PERSON}</option>
              {people.map((one) => (
                <option key={one.id} value={one.id}>
                  {one.name}
                </option>
              ))}
            </select>
            {!askers.busy && askers.failure === null && people.length === 0 ? (
              <p className="note">{NOBODY_LISTED}</p>
            ) : null}
            {peopleCut ? <p className="note">{MORE_PEOPLE}</p> : null}
            <FieldProblems problems={goldenProblems} form={GOLDEN_FORM} names="asked_as" />
            <label className="control-label" htmlFor={field(GOLDEN_FORM, "expect")}>
              It must be
            </label>
            <select
              id={field(GOLDEN_FORM, "expect")}
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
            <label className="control-label" htmlFor={field(RUNG_FORM, "tier")}>
              Level
            </label>
            <select
              id={field(RUNG_FORM, "tier")}
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
                  {levelName(one)}
                </option>
              ))}
            </select>
            <label className="control-label" htmlFor={field(RUNG_FORM, "provider")}>
              Provider
            </label>
            <input
              id={field(RUNG_FORM, "provider")}
              className="form-control"
              type="text"
              name="provider"
              value={provider}
              {...problemAttributes(rungProblems, RUNG_FORM, "provider")}
              onChange={(event) => {
                setProvider(event.target.value);
              }}
            />
            <FieldProblems problems={rungProblems} form={RUNG_FORM} names="provider" />
            <label className="control-label" htmlFor={field(RUNG_FORM, "model")}>
              Model
            </label>
            <input
              id={field(RUNG_FORM, "model")}
              className="form-control"
              type="text"
              name="model"
              value={model}
              {...problemAttributes(rungProblems, RUNG_FORM, "model")}
              onChange={(event) => {
                setModel(event.target.value);
              }}
            />
            <FieldProblems problems={rungProblems} form={RUNG_FORM} names="model" />
            <label className="control-label" htmlFor={field(RUNG_FORM, "attempts")}>
              Attempts
            </label>
            <input
              id={field(RUNG_FORM, "attempts")}
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
            <FieldProblems problems={rungProblems} form={RUNG_FORM} names="attempts" />
            <label className="control-label" htmlFor={field(RUNG_FORM, "timeout_seconds")}>
              Seconds to wait for an answer
            </label>
            <input
              id={field(RUNG_FORM, "timeout_seconds")}
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
            <FieldProblems problems={rungProblems} form={RUNG_FORM} names="timeout_seconds" />
            <label className="control-label" htmlFor={field(RUNG_FORM, "max_concurrency")}>
              Calls at once, at most
            </label>
            <input
              id={field(RUNG_FORM, "max_concurrency")}
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
