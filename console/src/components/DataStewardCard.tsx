/**
 * The People screen's Data steward card: who every read of the company's data begins with, and
 * naming them on an install whose setup named nobody.
 *
 * **Drawn only for somebody the API answers.** See
 * `pages/dataStewardQuery.A_CARD_NOBODY_MAY_USE_IS_NOT_DRAWN`. Once a steward is appointed it says
 * who, in the API's words, and offers nothing, because the console does not replace one.
 *
 * **Both ways of naming are confirmed, and naming yourself is its own button.** Naming the
 * administrator as the steward too is the choice the owner's decision says must be made out loud,
 * so it is never the form's default and never a box ticked beside a name: it is a separate press
 * and a separate confirmation, whose consequence is the API's sentence about holding both. Naming
 * another person is the form, judged blank before its confirmation opens.
 *
 * **Existing parts only.** The card, the form fields and `ConfirmAction` are the ones People and
 * Sign-in links already draw; the redesign of the console is a separate package.
 *
 * Task ids: M27.9.9
 */

import { useState, type FormEvent } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { ConfirmAction } from "./ConfirmAction";
import {
  CONFIRM_NAMING,
  DATA_STEWARD_HEADING,
  KEEP_AS_IT_IS,
  NAME_ANOTHER,
  NAME_YOURSELF,
  STEWARD_ADDRESS_LABEL,
  STEWARD_API_PATH,
  STEWARD_NAME_LABEL,
  YOURSELF_BODY,
  YOURSELF_QUESTION,
  anotherBody,
  anotherQuestion,
  blankProblems,
  problemsIn,
  readSteward,
} from "../pages/dataStewardQuery";
import { FailureNotice } from "../ui/FailureNotice";
import { Notice } from "../ui/Notice";

type Asking = "another" | "yourself" | null;

export function DataStewardCard() {
  const [version, setVersion] = useState(0);
  const answer = useResource<unknown>(STEWARD_API_PATH, version);
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [asking, setAsking] = useState<Asking>(null);
  const [busy, setBusy] = useState(false);
  const [problems, setProblems] = useState<Readonly<Record<string, string>>>({});
  const [refused, setRefused] = useState<string | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const steward = readSteward(answer.data);
  if (steward === null) {
    return null;
  }

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    // Never a native submission: a work address in a query string is in history and a proxy's log.
    event.preventDefault();
    const blank = blankProblems(name, address);
    setProblems(blank);
    setRefused(null);
    setFailure(null);
    if (Object.keys(blank).length === 0) {
      setAsking("another");
    }
  }

  async function send(body: Readonly<Record<string, unknown>>): Promise<void> {
    setBusy(true);
    const result = await request<unknown>(STEWARD_API_PATH, { method: "POST", body });
    setBusy(false);
    setAsking(null);
    if (result.ok) {
      setName("");
      setAddress("");
      setProblems({});
      setVersion((current) => current + 1);
      return;
    }
    // A 409 is the product's one error shape, so its sentence is the failure's own message: see
    // `brain.data_steward_routes.TOLD`, one sentence per refusal saying what to do.
    const told = result.failure.status === 422 ? problemsIn(result.body) : null;
    if (told !== null) {
      setProblems(told);
    } else if (result.failure.status === 409) {
      setRefused(result.failure.message);
    } else {
      setFailure(result.failure);
    }
  }

  return (
    <section className="card" aria-labelledby="data-steward-heading">
      <h2 id="data-steward-heading">{DATA_STEWARD_HEADING}</h2>
      <p>{steward.told}</p>
      {steward.appointed ? null : (
        <>
          {refused === null ? null : (
            <Notice title={DATA_STEWARD_HEADING}>
              <p>{refused}</p>
            </Notice>
          )}
          {failure === null ? null : <FailureNotice failure={failure} />}
          {asking === "another" ? (
            <ConfirmAction
              question={anotherQuestion(name.trim())}
              consequence={steward.appointing_another ?? ""}
              confirmLabel={CONFIRM_NAMING}
              cancelLabel={KEEP_AS_IT_IS}
              busy={busy}
              onConfirm={() => {
                void send(anotherBody(name, address));
              }}
              onCancel={() => {
                setAsking(null);
              }}
            />
          ) : null}
          {asking === "yourself" ? (
            <ConfirmAction
              question={YOURSELF_QUESTION}
              consequence={steward.appointing_yourself ?? ""}
              confirmLabel={CONFIRM_NAMING}
              cancelLabel={KEEP_AS_IT_IS}
              busy={busy}
              onConfirm={() => {
                void send(YOURSELF_BODY);
              }}
              onCancel={() => {
                setAsking(null);
              }}
            />
          ) : null}
          <form className="form" noValidate autoComplete="off" onSubmit={onSubmit}>
            <Field
              id="data-steward-full-name"
              label={STEWARD_NAME_LABEL}
              value={name}
              problem={problems["steward_full_name"]}
              onChange={setName}
            />
            <Field
              id="data-steward-work-address"
              label={STEWARD_ADDRESS_LABEL}
              value={address}
              problem={problems["steward_work_address"]}
              onChange={setAddress}
            />
            <div className="form-actions">
              <button type="submit" className="button" disabled={busy || asking !== null}>
                {NAME_ANOTHER}
              </button>
            </div>
          </form>
          <div className="form-actions">
            <button
              type="button"
              className="button"
              disabled={busy || asking !== null}
              onClick={() => {
                setProblems({});
                setRefused(null);
                setFailure(null);
                setAsking("yourself");
              }}
            >
              {NAME_YOURSELF}
            </button>
          </div>
        </>
      )}
    </section>
  );
}

function Field({
  id,
  label,
  value,
  problem,
  onChange,
}: {
  readonly id: string;
  readonly label: string;
  readonly value: string;
  readonly problem: string | undefined;
  readonly onChange: (value: string) => void;
}) {
  const problemId = `${id}-problem`;
  return (
    <div className="rjsf-field">
      <label className="control-label" htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        type="text"
        className="form-control"
        value={value}
        autoComplete="off"
        spellCheck={false}
        aria-invalid={problem !== undefined}
        {...(problem === undefined ? {} : { "aria-describedby": problemId })}
        onChange={(event) => onChange(event.target.value)}
      />
      {problem === undefined ? null : (
        <p id={problemId} className="first-run__problem">
          {problem}
        </p>
      )}
    </div>
  );
}
