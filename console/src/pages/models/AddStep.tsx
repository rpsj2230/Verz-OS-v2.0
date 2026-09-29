/**
 * Adding a step at the end of a level: the level, the provider and model it calls, and its three
 * numbers, sent from a confirmation through the matrix gate.
 *
 * **A change is held while no golden question is recorded, and the form says so before it is sent**,
 * so nobody fills it in to learn that from the refusal.
 *
 * **The provider is chosen from the providers this install can call**, by the name a person knows,
 * and the model offers the names already in use and those an added provider serves; the route still
 * judges the pair (`brain.routing_routes.RungAdd`). The answer is the change as the gate decided it,
 * which the page draws: applied, or held with what failed and the way through.
 *
 * Task ids: M5.7.2, M5.6.2, M27.15.38, M27.16.1
 */

import { useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure, FieldProblem } from "../../api/errors";
import { ConfirmDialog, FailureState, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { problemAttributes } from "../../ui/FieldProblems";
import {
  ADD_RUNG,
  ADD_RUNG_API_PATH,
  ADD_RUNG_HEADING,
  addRungConsequence,
  addRungQuestion,
  blankRungProblems,
  KEEP_LADDER,
  readChange,
  TIERS,
  type ChangeRow,
  type RungAsked,
} from "../matrixGateQuery";
import { MAX_SMALLINT, MAX_TIMEOUT_SECONDS } from "../matrixQuery";
import { levelName, providerName, type ProviderStateRow, type RungStateRow } from "../modelsQuery";
import { FIELD_CONTROL, FormField } from "./FormField";
import { modelsInUse } from "./providerWords";
import { HELD_UNTIL_A_GOLDEN_QUESTION } from "./routingWords";

const FORM = "add-step";

export const ADD_STEP_LEDE = "A new step goes last in its level, after the steps already there.";
export const LEVEL_HINT = "Simple, Medium or Complex: the level of question it answers.";
export const PROVIDER_HINT = "One of the providers this install can call.";
export const MODEL_HINT = "The model's name as the provider spells it, like gpt-4o-mini.";
export const ATTEMPTS_HINT = `Tries before the next step. A whole number from 1 to ${String(MAX_SMALLINT)}.`;
export const TIMEOUT_HINT = `Seconds to wait for an answer. More than 0 and at most ${String(MAX_TIMEOUT_SECONDS)}.`;
export const CONCURRENCY_HINT = `Calls it takes at once. A whole number from 1 to ${String(MAX_SMALLINT)}.`;
export const DO_NOT_ADD_STEP = "Cancel";

export function AddStep({
  providers,
  plan,
  goldenCount,
  onDecided,
  onClose,
}: {
  readonly providers: readonly ProviderStateRow[];
  readonly plan: readonly RungStateRow[];
  /** How many golden questions are recorded, or null where the page does not know. */
  readonly goldenCount: number | null;
  readonly onDecided: (change: ChangeRow | null) => void;
  readonly onClose: () => void;
}) {
  const [tier, setTier] = useState<RungAsked["tier"]>("main");
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [attempts, setAttempts] = useState("1");
  const [timeout, setTimeoutSeconds] = useState("20");
  const [concurrency, setConcurrency] = useState("4");
  const [blank, setBlank] = useState<FieldProblem[]>([]);
  const [pending, setPending] = useState<RungAsked | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const problems = [...blank, ...(failure?.problems ?? [])];
  const id = (name: string) => `${FORM}-${name}`;
  const chosen = providers.find((one) => one.provider === provider);
  const suggested = [...new Set([...modelsInUse(provider, plan), ...(chosen?.registered?.models ?? [])])];

  const ask = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFailure(null);
    const found = blankRungProblems(provider, model, [attempts, timeout, concurrency]);
    setBlank(found);
    if (found.length > 0) {
      return;
    }
    setPending({
      tier,
      provider: provider.trim(),
      model: model.trim(),
      attempts: Number(attempts),
      timeout_seconds: Number(timeout),
      max_concurrency: Number(concurrency),
    });
  };

  const add = (asked: RungAsked) => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(ADD_RUNG_API_PATH, { method: "POST", body: asked });
      setBusy(false);
      setPending(null);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      onDecided(readChange(result.data));
    })();
  };

  const number = (name: string, label: string, hint: string, value: string, set: (value: string) => void) => (
    <FormField id={id(name)} label={label} hint={hint} form={FORM} name={name} problems={problems}>
      <input
        id={id(name)}
        name={name}
        className={FIELD_CONTROL}
        inputMode="decimal"
        value={value}
        {...problemAttributes(problems, FORM, name, `${id(name)}-hint`)}
        onChange={(event) => {
          set(event.target.value);
        }}
      />
    </FormField>
  );

  return (
    <SectionCard title={ADD_RUNG_HEADING} lede={ADD_STEP_LEDE}>
      <form aria-label={ADD_RUNG_HEADING} className="flex flex-col gap-3" onSubmit={ask} noValidate>
        {goldenCount === 0 ? <Note>{HELD_UNTIL_A_GOLDEN_QUESTION}</Note> : null}
        <div className="[display:grid] grid-cols-1 gap-3 sm:grid-cols-3">
          <FormField id={id("tier")} label="Level" hint={LEVEL_HINT} form={FORM} name="tier" problems={problems}>
            <select
              id={id("tier")}
              name="tier"
              className={FIELD_CONTROL}
              value={tier}
              onChange={(event) => {
                setTier(TIERS.find((one) => one === event.target.value) ?? "main");
              }}
            >
              {TIERS.map((one) => (
                <option key={one} value={one}>
                  {levelName(one)}
                </option>
              ))}
            </select>
          </FormField>
          <FormField id={id("provider")} label="Provider" hint={PROVIDER_HINT} form={FORM} name="provider" problems={problems}>
            <select
              id={id("provider")}
              name="provider"
              className={FIELD_CONTROL}
              value={provider}
              {...problemAttributes(problems, FORM, "provider", `${id("provider")}-hint`)}
              onChange={(event) => {
                setProvider(event.target.value);
              }}
            >
              <option value="">Choose a provider</option>
              {providers.map((one) => (
                <option key={one.provider} value={one.provider}>
                  {providerName(one.provider, providers)}
                </option>
              ))}
            </select>
          </FormField>
          <FormField id={id("model")} label="Model" hint={MODEL_HINT} form={FORM} name="model" problems={problems}>
            <input
              id={id("model")}
              name="model"
              className={FIELD_CONTROL}
              value={model}
              list={id("models")}
              {...problemAttributes(problems, FORM, "model", `${id("model")}-hint`)}
              onChange={(event) => {
                setModel(event.target.value);
              }}
            />
            <datalist id={id("models")}>
              {suggested.map((one) => (
                <option key={one} value={one} />
              ))}
            </datalist>
          </FormField>
        </div>
        <div className="[display:grid] grid-cols-1 gap-3 sm:grid-cols-3">
          {number("attempts", "Attempts", ATTEMPTS_HINT, attempts, setAttempts)}
          {number("timeout_seconds", "Seconds to wait", TIMEOUT_HINT, timeout, setTimeoutSeconds)}
          {number("max_concurrency", "Calls at once", CONCURRENCY_HINT, concurrency, setConcurrency)}
        </div>
        {failure === null || failure.problems.length > 0 ? null : <FailureState failure={failure} />}
        <div className="flex flex-wrap justify-end gap-2">
          <Button type="button" variant="outline" className="min-h-11 sm:min-h-9" onClick={onClose}>
            {DO_NOT_ADD_STEP}
          </Button>
          <Button type="submit" className="min-h-11 sm:min-h-9" disabled={busy}>
            {ADD_RUNG}
          </Button>
        </div>
      </form>
      <ConfirmDialog
        open={pending !== null}
        question={pending === null ? "" : addRungQuestion(pending)}
        consequence={pending === null ? "" : addRungConsequence(pending)}
        confirmLabel={ADD_RUNG}
        cancelLabel={KEEP_LADDER}
        busy={busy}
        onConfirm={() => {
          if (pending !== null) {
            add(pending);
          }
        }}
        onCancel={() => {
          setPending(null);
        }}
      />
    </SectionCard>
  );
}
