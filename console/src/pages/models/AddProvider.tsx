/**
 * Adding an OpenAI-compatible provider: its short name, what people call it, its address, its
 * model names and its key, sent once from a confirmation.
 *
 * **Drawn inline under the list's header, not in a drawer**, so the form is where the person is
 * looking and a keyboard reaches it in the page's own order. **The key is never in React**:
 * `SecretField` holds it in the element and `take()` empties the field in the call that reads it,
 * so it exists in this page only for the request (`brain.provider_registry_routes` writes it to
 * the vault before the row, and the answer never carries it).
 *
 * **Every field says what it accepts before anything is sent**, and a blank one is said beside it
 * without asking to confirm anything (`tests/validated-before-write.test.tsx`).
 *
 * Task ids: M5.7.2, M27.16.1
 */

import { useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure, FieldProblem } from "../../api/errors";
import { ConfirmDialog, FailureState, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { SecretField, useSecret } from "../../components/ui/secret-field";
import { problemAttributes } from "../../ui/FieldProblems";
import {
  ADD_CONSEQUENCE,
  ADD_PROVIDER,
  ADD_PROVIDER_API_PATH,
  ADD_PROVIDER_HEADING,
  ADD_PROVIDER_NOTE,
  addQuestion,
  blankAddProblems,
  DO_NOT_ADD,
  modelNames,
  type AddAsked,
} from "../providerRegisterQuery";
import { FIELD_AREA, FIELD_CONTROL, FormField } from "./FormField";

const FORM = "add-provider";

export const SLUG_HINT = "Lower-case letters, digits and _, starting with a letter, 2 to 31 characters, like acme_llm.";
export const LABEL_HINT = "What people call it, up to 80 characters.";
export const ADDRESS_HINT = "The https address its OpenAI-compatible interface is served at, like https://llm.example.com/v1.";
export const MODELS_HINT = "Each model name it serves, one per line or separated by commas.";
export const KEY_HINT = "The key the provider issued. It is kept in the vault and never shown again.";

export function AddProvider({ onAdded, onClose }: { readonly onAdded: (name: string) => void; readonly onClose: () => void }) {
  const secret = useSecret();
  const [slug, setSlug] = useState("");
  const [label, setLabel] = useState("");
  const [address, setAddress] = useState("");
  const [models, setModels] = useState("");
  const [typed, setTyped] = useState(false);
  const [blank, setBlank] = useState<FieldProblem[]>([]);
  const [pending, setPending] = useState<Omit<AddAsked, "key"> | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const problems = [...blank, ...(failure?.problems ?? [])];
  const id = (name: string) => `${FORM}-${name}`;

  const ask = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFailure(null);
    const found = blankAddProblems(slug, label, address, models, typed ? "typed" : "");
    setBlank(found);
    if (found.length > 0) {
      return;
    }
    setPending({ slug: slug.trim(), label: label.trim(), base_url: address.trim(), models: modelNames(models) });
  };

  // The key leaves the field only once the person has confirmed, and only for this request.
  const add = (asked: Omit<AddAsked, "key">) => {
    const key = secret.take();
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(ADD_PROVIDER_API_PATH, { method: "POST", body: { ...asked, key } });
      setBusy(false);
      setPending(null);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      onAdded(asked.label);
    })();
  };

  return (
    <SectionCard title={ADD_PROVIDER_HEADING} lede={ADD_PROVIDER_NOTE}>
      <form aria-label={ADD_PROVIDER_HEADING} className="flex flex-col gap-3" onSubmit={ask} noValidate>
        <div className="[display:grid] grid-cols-1 gap-3 sm:grid-cols-2">
          <FormField id={id("slug")} label="Short name" hint={SLUG_HINT} form={FORM} name="slug" problems={problems}>
            <input
              id={id("slug")}
              name="slug"
              className={FIELD_CONTROL}
              value={slug}
              {...problemAttributes(problems, FORM, "slug", `${id("slug")}-hint`)}
              onChange={(event) => {
                setSlug(event.target.value);
              }}
            />
          </FormField>
          <FormField id={id("label")} label="Name" hint={LABEL_HINT} form={FORM} name="label" problems={problems}>
            <input
              id={id("label")}
              name="label"
              className={FIELD_CONTROL}
              value={label}
              {...problemAttributes(problems, FORM, "label", `${id("label")}-hint`)}
              onChange={(event) => {
                setLabel(event.target.value);
              }}
            />
          </FormField>
        </div>
        <FormField id={id("base_url")} label="Address" hint={ADDRESS_HINT} form={FORM} name="base_url" problems={problems}>
          <input
            id={id("base_url")}
            name="base_url"
            className={FIELD_CONTROL}
            value={address}
            inputMode="url"
            {...problemAttributes(problems, FORM, "base_url", `${id("base_url")}-hint`)}
            onChange={(event) => {
              setAddress(event.target.value);
            }}
          />
        </FormField>
        <FormField id={id("models")} label="Model names" hint={MODELS_HINT} form={FORM} name="models" problems={problems}>
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
        <SecretField
          secret={secret}
          label="Key"
          stored={false}
          description={KEY_HINT}
          disabled={busy}
          invalid={problems.some((one) => one.field === "key")}
          onPresenceChange={setTyped}
        />
        {problems.some((one) => one.field === "key") ? (
          <p className="m-0 text-[12.5px] text-crit">{problems.find((one) => one.field === "key")?.message}</p>
        ) : null}
        {failure === null || failure.problems.length > 0 ? null : <FailureState failure={failure} />}
        <div className="flex flex-wrap justify-end gap-2">
          <Button type="button" variant="outline" className="min-h-11 sm:min-h-9" onClick={onClose}>
            {DO_NOT_ADD}
          </Button>
          <Button type="submit" className="min-h-11 sm:min-h-9" disabled={busy}>
            {ADD_PROVIDER}
          </Button>
        </div>
      </form>
      <ConfirmDialog
        open={pending !== null}
        question={pending === null ? "" : addQuestion({ ...pending, key: "" })}
        consequence={ADD_CONSEQUENCE}
        confirmLabel={ADD_PROVIDER}
        cancelLabel={DO_NOT_ADD}
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
