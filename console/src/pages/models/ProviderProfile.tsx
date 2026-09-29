/**
 * A provider's Profile: its key, what the company agreed with it and where it processes, and the
 * models it serves.
 *
 * **The key is added or replaced here, and never shown.** `components/ProviderKeyForm.tsx` writes
 * it to the slot the API named on this provider's row, which it sends only to a reader who may
 * manage keys; for anybody else the card says whether a key is held and offers nothing.
 *
 * **Terms and residency are one form, because they are one write** (`PUT
 * /models/providers/{provider}/terms`), and every field says what it accepts before anything is
 * sent. A reader who may not record terms reads them as facts. Since `0140` each save is on the
 * ledger under the provider's own subject, which the About view lists.
 *
 * Task ids: M5.6.4, M5.5.3, M5.1.3, M5.1.2, M27.16.1
 */

import { useState, type FormEvent, type InputHTMLAttributes } from "react";
import { request } from "../../api/client";
import type { ApiFailure, FieldProblem } from "../../api/errors";
import { Chip, ConfirmDialog, Fact, FactList, FailureState, Note, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { ProviderKeyForm } from "../../components/ProviderKeyForm";
import { problemAttributes } from "../../ui/FieldProblems";
import { keyAction, keyHeldWords, REPLACE_KEY, vaultKeyLine, type ProviderStateRow, type ProvidersBody } from "../modelsQuery";
import {
  blankTermsProblems,
  KEEP_TERMS,
  laneOverrides,
  modelNames,
  RESIDENCY_CLASSES,
  SAVE_TERMS,
  termsApiPath,
  termsConsequence,
  termsQuestion,
  type TermsAsked,
} from "../providerRegisterQuery";
import { FIELD_AREA, FIELD_CONTROL, FormField } from "./FormField";
import { isAdded, modelsInUse } from "./providerWords";

const FORM = "provider-terms";

export const KEY_HEADING = "Key";
export const TERMS_HEADING = "Terms and residency";
export const TERMS_LEDE = "What the company agreed with this provider, and where it processes what it is sent.";
export const MODELS_HEADING = "Models";
export const NOT_RECORDED = "Not recorded";

export const RESIDENCY_WORDS: Readonly<Record<string, string>> = Object.freeze({
  global: "Anywhere",
  region_pinned: "Kept in one region",
  on_prem: "On the company's own premises",
});

export const REGION_HINT = "Where it processes what it is sent, like eu-west-1, or global when nothing is promised. Up to 64 characters.";
export const RESIDENCY_HINT = "Whether the agreement keeps what it is sent in one region or on the company's premises.";
export const STORAGE_HINT = "Where it keeps what it is sent, in the agreement's words. Up to 300 characters.";
export const RETENTION_HINT = "How long it keeps questions and answers, in the agreement's words. Up to 1000 characters.";
export const TRAINING_HINT = "Whether what it is sent may train its models, in the agreement's words. Up to 1000 characters.";
export const AGREEMENT_HINT = "An https link to the signed agreement, or leave it empty.";
export const TIMEOUT_HINT = "Seconds a waiting person gives this provider before the next step is tried. A number above 0, or empty for each step's own.";
export const ATTEMPTS_HINT = "Tries per question for a waiting person. A whole number of 1 or more, or empty for each step's own.";
export const MODEL_NAMES_HINT = "Each model name it serves, one per line or separated by commas.";

function answerOverride(row: ProviderStateRow): { readonly timeout: string; readonly attempts: string } {
  const answer = row.registered?.lane_overrides.find((one) => one.lane === "answer");
  return {
    timeout: answer?.timeout_seconds === null || answer?.timeout_seconds === undefined ? "" : String(answer.timeout_seconds),
    attempts: answer?.attempts === null || answer?.attempts === undefined ? "" : String(answer.attempts),
  };
}

/** The key card: whether one is held, and for a reader who may manage keys, the form. */
function KeyCard({ row, name, onChanged }: { readonly row: ProviderStateRow; readonly name: string; readonly onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const [told, setTold] = useState<string | null>(null);
  const vault = vaultKeyLine(row);
  const key = keyAction(row);
  return (
    <SectionCard
      title={KEY_HEADING}
      action={
        row.credential === null || open ? undefined : (
          <Button
            variant="outline"
            size="sm"
            className="min-h-11 sm:min-h-8"
            aria-label={`${key}: ${name}`}
            onClick={() => {
              setTold(null);
              setOpen(true);
            }}
          >
            {key}
          </Button>
        )
      }
    >
      <FactList>
        <Fact label="Held on this server">{keyHeldWords(row.key_held)}</Fact>
        {vault === null ? null : <Fact label="In the vault">{vault}</Fact>}
      </FactList>
      {open && row.credential !== null ? (
        <div className="mt-3">
          <ProviderKeyForm
            row={row}
            name={name}
            held={key === REPLACE_KEY}
            onSaved={(sentence) => {
              setOpen(false);
              setTold(sentence);
              onChanged();
            }}
            onClose={() => {
              setOpen(false);
            }}
          />
        </div>
      ) : null}
      {told === null ? null : (
        <div role="status" className="mt-3">
          <Note kind="done">{told}</Note>
        </div>
      )}
    </SectionCard>
  );
}

/** The terms as facts, for a reader who may not record them. */
function TermsFacts({ row }: { readonly row: ProviderStateRow }) {
  const terms = row.registered;
  return (
    <FactList>
      <Fact label="Processing region">{terms?.processing_region ?? NOT_RECORDED}</Fact>
      <Fact label="Residency">{terms === null || terms === undefined ? NOT_RECORDED : (RESIDENCY_WORDS[terms.residency_class] ?? terms.residency_class)}</Fact>
      <Fact label="Storage location">{terms?.storage_location || NOT_RECORDED}</Fact>
      <Fact label="Retention">{terms?.retention_terms || NOT_RECORDED}</Fact>
      <Fact label="Training">{terms?.training_terms || NOT_RECORDED}</Fact>
      <Fact label="Agreement">{terms?.agreement_url ?? NOT_RECORDED}</Fact>
    </FactList>
  );
}

/** The terms form, for a reader the API says may record them. */
function TermsForm({ row, name, onChanged }: { readonly row: ProviderStateRow; readonly name: string; readonly onChanged: () => void }) {
  const terms = row.registered;
  const override = answerOverride(row);
  const added = isAdded(row);
  const [region, setRegion] = useState(terms?.processing_region ?? "global");
  const [residency, setResidency] = useState<TermsAsked["residency_class"]>(
    RESIDENCY_CLASSES.find((one) => one === terms?.residency_class) ?? "global",
  );
  const [storage, setStorage] = useState(terms?.storage_location ?? "");
  const [retention, setRetention] = useState(terms?.retention_terms ?? "");
  const [training, setTraining] = useState(terms?.training_terms ?? "");
  const [agreement, setAgreement] = useState(terms?.agreement_url ?? "");
  const [timeout, setTimeoutSeconds] = useState(override.timeout);
  const [attempts, setAttempts] = useState(override.attempts);
  const [models, setModels] = useState((terms?.models ?? []).join("\n"));
  const [blank, setBlank] = useState<FieldProblem[]>([]);
  const [pending, setPending] = useState<(TermsAsked & { readonly models?: readonly string[] }) | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [told, setTold] = useState<string | null>(null);
  const problems = [...blank, ...(failure?.problems ?? [])];
  const id = (field: string) => `${FORM}-${field}`;

  const ask = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFailure(null);
    setTold(null);
    const found = blankTermsProblems(region);
    if (added && modelNames(models).length === 0) {
      found.push({ field: "models", code: "blank", message: "List at least one model name it serves." });
    }
    setBlank(found);
    if (found.length > 0) {
      return;
    }
    setPending({
      processing_region: region.trim(),
      residency_class: residency,
      storage_location: storage.trim(),
      retention_terms: retention.trim(),
      training_terms: training.trim(),
      agreement_url: agreement.trim() === "" ? null : agreement.trim(),
      lane_overrides: laneOverrides(timeout, attempts),
      ...(added ? { models: modelNames(models) } : {}),
    });
  };

  const save = (asked: TermsAsked & { readonly models?: readonly string[] }) => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(termsApiPath(row.provider), { method: "PUT", body: asked });
      setBusy(false);
      setPending(null);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setTold(`The terms for ${name} were saved.`);
      onChanged();
    })();
  };

  const text = (field: string, value: string, set: (value: string) => void, extra: InputHTMLAttributes<HTMLInputElement> = {}) => (
    <input
      id={id(field)}
      name={field}
      className={FIELD_CONTROL}
      value={value}
      {...extra}
      {...problemAttributes(problems, FORM, field, `${id(field)}-hint`)}
      onChange={(event) => {
        set(event.target.value);
      }}
    />
  );

  return (
    <>
      <form aria-label={`${TERMS_HEADING} for ${name}`} className="flex flex-col gap-3" onSubmit={ask} noValidate>
        <div className="[display:grid] grid-cols-1 gap-3 sm:grid-cols-2">
          <FormField id={id("processing_region")} label="Processing region" hint={REGION_HINT} form={FORM} name="processing_region" problems={problems}>
            {text("processing_region", region, setRegion)}
          </FormField>
          <FormField id={id("residency_class")} label="Residency" hint={RESIDENCY_HINT} form={FORM} name="residency_class" problems={problems}>
            <select
              id={id("residency_class")}
              name="residency_class"
              className={FIELD_CONTROL}
              value={residency}
              onChange={(event) => {
                setResidency(RESIDENCY_CLASSES.find((one) => one === event.target.value) ?? "global");
              }}
            >
              {RESIDENCY_CLASSES.map((one) => (
                <option key={one} value={one}>
                  {RESIDENCY_WORDS[one] ?? one}
                </option>
              ))}
            </select>
          </FormField>
        </div>
        <FormField id={id("storage_location")} label="Storage location" hint={STORAGE_HINT} form={FORM} name="storage_location" problems={problems}>
          {text("storage_location", storage, setStorage)}
        </FormField>
        <FormField id={id("retention_terms")} label="Retention" hint={RETENTION_HINT} form={FORM} name="retention_terms" problems={problems}>
          {text("retention_terms", retention, setRetention)}
        </FormField>
        <FormField id={id("training_terms")} label="Training" hint={TRAINING_HINT} form={FORM} name="training_terms" problems={problems}>
          {text("training_terms", training, setTraining)}
        </FormField>
        <FormField id={id("agreement_url")} label="Agreement link" hint={AGREEMENT_HINT} form={FORM} name="agreement_url" problems={problems}>
          {text("agreement_url", agreement, setAgreement, { inputMode: "url" })}
        </FormField>
        <div className="[display:grid] grid-cols-1 gap-3 sm:grid-cols-2">
          <FormField id={id("timeout")} label="Seconds to wait" hint={TIMEOUT_HINT} form={FORM} name="lane_overrides" problems={problems}>
            {text("timeout", timeout, setTimeoutSeconds, { inputMode: "decimal" })}
          </FormField>
          <FormField id={id("attempts")} label="Tries" hint={ATTEMPTS_HINT} form={FORM} name="attempts" problems={problems}>
            {text("attempts", attempts, setAttempts, { inputMode: "numeric" })}
          </FormField>
        </div>
        {added ? (
          <FormField id={id("models")} label="Model names" hint={MODEL_NAMES_HINT} form={FORM} name="models" problems={problems}>
            <textarea
              id={id("models")}
              name="models"
              className={FIELD_AREA}
              value={models}
              {...problemAttributes(problems, FORM, "models", `${id("models")}-hint`)}
              onChange={(event) => {
                setModels(event.target.value);
              }}
            />
          </FormField>
        ) : null}
        {failure === null || failure.problems.length > 0 ? null : <FailureState failure={failure} />}
        {problems.some((one) => one.field === "terms") ? (
          <p className="m-0 text-[12.5px] text-crit">{problems.find((one) => one.field === "terms")?.message}</p>
        ) : null}
        <div className="flex justify-end">
          <Button type="submit" className="min-h-11 sm:min-h-9" disabled={busy}>
            {SAVE_TERMS}
          </Button>
        </div>
      </form>
      {told === null ? null : (
        <div role="status" className="mt-3">
          <Note kind="done">{told}</Note>
        </div>
      )}
      <ConfirmDialog
        open={pending !== null}
        question={termsQuestion(name)}
        consequence={pending === null ? "" : termsConsequence(name, pending)}
        confirmLabel={SAVE_TERMS}
        cancelLabel={KEEP_TERMS}
        busy={busy}
        onConfirm={() => {
          if (pending !== null) {
            save(pending);
          }
        }}
        onCancel={() => {
          setPending(null);
        }}
      />
    </>
  );
}

export function ProviderProfile({
  row,
  body,
  name,
  onChanged,
}: {
  readonly row: ProviderStateRow;
  readonly body: ProvidersBody;
  readonly name: string;
  readonly onChanged: () => void;
}) {
  const inUse = modelsInUse(row.provider, body.rungs);
  const served = row.registered?.models ?? [];
  return (
    <div data-slot="provider-profile" className="flex min-w-0 flex-col gap-4">
      <KeyCard row={row} name={name} onChanged={onChanged} />
      <SectionCard title={TERMS_HEADING} lede={TERMS_LEDE}>
        {body.editable ? <TermsForm key={JSON.stringify(row.registered)} row={row} name={name} onChanged={onChanged} /> : <TermsFacts row={row} />}
      </SectionCard>
      <SectionCard title={MODELS_HEADING}>
        <FactList>
          <Fact label="In use">
            {inUse.length === 0 ? (
              "None"
            ) : (
              <span className="flex flex-wrap gap-1">
                {inUse.map((one) => (
                  <Chip key={one} mono>
                    {one}
                  </Chip>
                ))}
              </span>
            )}
          </Fact>
          {served.length === 0 ? null : (
            <Fact label="It serves">
              <span className="flex flex-wrap gap-1">
                {served.map((one) => (
                  <Chip key={one} mono>
                    {one}
                  </Chip>
                ))}
              </span>
            </Fact>
          )}
        </FactList>
      </SectionCard>
    </div>
  );
}
