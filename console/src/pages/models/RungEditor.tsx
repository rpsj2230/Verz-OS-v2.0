/**
 * One step's editor, open at its own address (`/routing/{id}`): its four numbers, where it sits,
 * and retiring it, each sent from a confirmation through the matrix gate.
 *
 * **Four numbers, and nothing else, are an edit**, for `brain.routing_routes`' reason: the attempts,
 * the time allowed, the calls at once and whether it is in use are the dials an incident is answered
 * with, and none of them changes what the chain is. **Where it sits is a move**, which is a new step
 * in the new place and the old one retired, and **taking it off is a retirement**; both are held
 * when they would leave a level with no step.
 *
 * **Each field says what it accepts, with the route's own bounds** (`matrixQuery`'s, held against
 * the route by a test), and a blank or out-of-range number is said beside it before anything asks
 * to be confirmed. Identifiers are under Advanced.
 *
 * Task ids: M5.3.3, M27.15.38, M5.6.2, M27.16.1
 */

import { X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { request } from "../../api/client";
import type { ApiFailure, FieldProblem } from "../../api/errors";
import { Advanced, Chip, ConfirmDialog, Fact, FactList, FailureState, NotOffered, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { problemAttributes } from "../../ui/FieldProblems";
import { readChange, TIERS, type ChangeRow } from "../matrixGateQuery";
import { MATRIX_PATH, MAX_SMALLINT, MAX_TIMEOUT_SECONDS, rungApiPath, scopeLines } from "../matrixQuery";
import { levelName } from "../modelsQuery";
import { FIELD_CONTROL, FormField } from "./FormField";
import { moveStepApiPath, NOT_OFFERED, retireStepApiPath } from "./modelsActions";
import {
  KEEP_STEP,
  MOVE_STEP,
  moveConsequence,
  moveQuestion,
  RETIRE_STEP,
  retireConsequence,
  retireQuestion,
  SAVE_STEP,
  saveConsequence,
  saveQuestion,
  stepName,
  type MatrixLine,
  type StepNumbers,
} from "./routingWords";

const EDIT_FORM = "step-edit";
const MOVE_FORM = "step-move";

export const ATTEMPTS_HINT = `Tries before the next step. A whole number from 1 to ${String(MAX_SMALLINT)}.`;
export const TIMEOUT_HINT = `Seconds to wait for an answer. More than 0 and at most ${String(MAX_TIMEOUT_SECONDS)}.`;
export const CONCURRENCY_HINT = `Calls it takes at once. A whole number from 1 to ${String(MAX_SMALLINT)}.`;
export const MOVE_LEVEL_HINT = "The level it moves to: its own, or another.";
export const MOVE_STEP_HINT = "The step number it takes in that level, from 1. A number past the last puts it last.";
export const CLOSE_EDITOR = "Close";

/** A whole number within the bounds, or null. */
function whole(value: string, least: number): number | null {
  const found = Number(value.trim());
  return value.trim() !== "" && Number.isInteger(found) && found >= least && found <= MAX_SMALLINT ? found : null;
}

/** The problems with an edit's numbers, said beside each field. Empty when all four are good. */
export function numberProblems(attempts: string, timeout: string, concurrency: string): FieldProblem[] {
  const found: FieldProblem[] = [];
  if (whole(attempts, 1) === null) {
    found.push({ field: "attempts", code: "blank", message: `Give a whole number of tries from 1 to ${String(MAX_SMALLINT)}.` });
  }
  const seconds = Number(timeout.trim());
  if (timeout.trim() === "" || !(seconds > 0) || seconds > MAX_TIMEOUT_SECONDS) {
    found.push({ field: "timeout_seconds", code: "blank", message: `Give the seconds to wait, above 0 and at most ${String(MAX_TIMEOUT_SECONDS)}.` });
  }
  if (whole(concurrency, 1) === null) {
    found.push({ field: "max_concurrency", code: "blank", message: `Give a whole number of calls from 1 to ${String(MAX_SMALLINT)}.` });
  }
  return found;
}

type Pending =
  | { readonly kind: "edit"; readonly numbers: StepNumbers }
  | { readonly kind: "move"; readonly tier: string; readonly step: number }
  | { readonly kind: "retire" };

export function RungEditor({
  line,
  onDecided,
}: {
  readonly line: MatrixLine;
  readonly onDecided: (change: ChangeRow | null) => void;
}) {
  const rung = line.rung;
  const [attempts, setAttempts] = useState(String(rung?.attempts ?? ""));
  const [timeout, setTimeoutSeconds] = useState(String(rung?.timeout_seconds ?? ""));
  const [concurrency, setConcurrency] = useState(String(rung?.max_concurrency ?? ""));
  const [enabled, setEnabled] = useState(rung?.enabled ?? true);
  const [tier, setTier] = useState(line.tier);
  const [step, setStep] = useState(String(line.step ?? 1));
  const [blank, setBlank] = useState<FieldProblem[]>([]);
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const problems = [...blank, ...(failure?.problems ?? [])];
  const id = (form: string, name: string) => `${form}-${name}`;
  if (rung === null) {
    return null;
  }

  const askEdit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFailure(null);
    const found = numberProblems(attempts, timeout, concurrency);
    setBlank(found);
    if (found.length > 0) {
      return;
    }
    setPending({
      kind: "edit",
      numbers: { attempts: Number(attempts), timeout_seconds: Number(timeout), max_concurrency: Number(concurrency), enabled },
    });
  };

  const askMove = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFailure(null);
    const place = whole(step, 1);
    const found: FieldProblem[] =
      place === null ? [{ field: "step", code: "blank", message: "Give the step number it moves to, from 1." }] : [];
    setBlank(found);
    if (place === null) {
      return;
    }
    setPending({ kind: "move", tier, step: place });
  };

  const send = (asked: Pending) => {
    setBusy(true);
    void (async () => {
      const result =
        asked.kind === "edit"
          ? await request<unknown>(rungApiPath(rung.id), { method: "PATCH", body: asked.numbers })
          : asked.kind === "move"
            ? await request<unknown>(moveStepApiPath(rung.id), { method: "POST", body: { tier: asked.tier, step: asked.step } })
            : await request<unknown>(retireStepApiPath(rung.id), { method: "POST" });
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
    <FormField id={id(EDIT_FORM, name)} label={label} hint={hint} form={EDIT_FORM} name={name} problems={problems}>
      <input
        id={id(EDIT_FORM, name)}
        name={name}
        className={FIELD_CONTROL}
        inputMode="decimal"
        value={value}
        {...problemAttributes(problems, EDIT_FORM, name, `${id(EDIT_FORM, name)}-hint`)}
        onChange={(event) => {
          set(event.target.value);
        }}
      />
    </FormField>
  );

  return (
    <SectionCard
      title={`Step ${String(line.step ?? 0)} of the ${levelName(line.tier)} level`}
      lede={`${line.provider} ${line.model}`}
      action={
        <Button asChild variant="ghost" size="sm" className="min-h-11 text-body no-underline sm:min-h-8">
          <Link to={MATRIX_PATH}>
            <X aria-hidden /> {CLOSE_EDITOR}
          </Link>
        </Button>
      }
    >
      <div className="flex flex-col gap-5">
        <form aria-label={`Numbers for ${stepName(line)}`} className="flex flex-col gap-3" onSubmit={askEdit} noValidate>
          <div className="[display:grid] grid-cols-1 gap-3 sm:grid-cols-3">
            {number("attempts", "Attempts", ATTEMPTS_HINT, attempts, setAttempts)}
            {number("timeout_seconds", "Seconds to wait", TIMEOUT_HINT, timeout, setTimeoutSeconds)}
            {number("max_concurrency", "Calls at once", CONCURRENCY_HINT, concurrency, setConcurrency)}
          </div>
          <label className="flex min-h-11 items-center gap-2 text-[13px] text-ink sm:min-h-8">
            <input
              type="checkbox"
              name="enabled"
              checked={enabled}
              onChange={(event) => {
                setEnabled(event.target.checked);
              }}
            />
            In use (untick to pause the step without retiring it)
          </label>
          <div className="flex justify-end">
            <Button type="submit" className="min-h-11 sm:min-h-9" disabled={busy}>
              {SAVE_STEP}
            </Button>
          </div>
        </form>

        <form aria-label={`Move ${stepName(line)}`} className="flex flex-col gap-3 border-t border-line pt-4" onSubmit={askMove} noValidate>
          <div className="[display:grid] grid-cols-1 gap-3 sm:grid-cols-2">
            <FormField id={id(MOVE_FORM, "tier")} label="Level" hint={MOVE_LEVEL_HINT} form={MOVE_FORM} name="tier" problems={problems}>
              <select
                id={id(MOVE_FORM, "tier")}
                name="tier"
                className={FIELD_CONTROL}
                value={tier}
                onChange={(event) => {
                  setTier(TIERS.find((one) => one === event.target.value) ?? line.tier);
                }}
              >
                {TIERS.map((one) => (
                  <option key={one} value={one}>
                    {levelName(one)}
                  </option>
                ))}
              </select>
            </FormField>
            <FormField id={id(MOVE_FORM, "step")} label="Step" hint={MOVE_STEP_HINT} form={MOVE_FORM} name="step" problems={problems}>
              <input
                id={id(MOVE_FORM, "step")}
                name="step"
                className={FIELD_CONTROL}
                inputMode="numeric"
                value={step}
                {...problemAttributes(problems, MOVE_FORM, "step", `${id(MOVE_FORM, "step")}-hint`)}
                onChange={(event) => {
                  setStep(event.target.value);
                }}
              />
            </FormField>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              className="min-h-11 sm:min-h-9"
              disabled={busy}
              onClick={() => {
                setFailure(null);
                setPending({ kind: "retire" });
              }}
            >
              {RETIRE_STEP}
            </Button>
            <Button type="submit" className="min-h-11 sm:min-h-9" disabled={busy}>
              {MOVE_STEP}
            </Button>
          </div>
          <NotOffered>{NOT_OFFERED.stepRestore}</NotOffered>
        </form>

        {failure === null || failure.problems.length > 0 ? null : <FailureState failure={failure} />}

        <Advanced>
          <FactList>
            <Fact label="Step id">
              <Chip mono>{rung.id}</Chip>
            </Fact>
            <Fact label="Deployment">
              <Chip mono>{rung.deployment_id}</Chip>
            </Fact>
            <Fact label="Provider id">
              <Chip mono>{rung.provider}</Chip>
            </Fact>
            <Fact label="Position">
              <span className="font-mono text-[12px]">{String(rung.position)}</span>
            </Fact>
            <Fact label="Applies to">
              {scopeLines(rung.scope).length === 0 ? "Every question" : scopeLines(rung.scope).join("; ")}
            </Fact>
          </FactList>
        </Advanced>
      </div>
      <ConfirmDialog
        open={pending !== null}
        question={
          pending === null
            ? ""
            : pending.kind === "edit"
              ? saveQuestion(line)
              : pending.kind === "move"
                ? moveQuestion(line, pending.tier, pending.step)
                : retireQuestion(line)
        }
        consequence={
          pending === null
            ? ""
            : pending.kind === "edit"
              ? saveConsequence(pending.numbers)
              : pending.kind === "move"
                ? moveConsequence(pending.tier, pending.step)
                : retireConsequence(line)
        }
        confirmLabel={pending?.kind === "retire" ? RETIRE_STEP : pending?.kind === "move" ? MOVE_STEP : SAVE_STEP}
        cancelLabel={KEEP_STEP}
        busy={busy}
        onConfirm={() => {
          if (pending !== null) {
            send(pending);
          }
        }}
        onCancel={() => {
          setPending(null);
        }}
      />
    </SectionCard>
  );
}
