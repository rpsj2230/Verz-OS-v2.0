/**
 * Setting a model provider's key from Models and health: pick the provider, paste its key, save.
 *
 * The write is `PUT /credentials/{slot}` (`brain.credential_routes`), which already existed with
 * nothing on any screen calling it for the four built-in providers: the table beside this said
 * whether a key was held and offered no way to hold one, so an owner told to "add the key on
 * Models and health" found no field. This is that field.
 *
 * **Drawn only for a reader the providers answer sent the vault's column to**, which is a reader who
 * holds `admin:credential` over everything; for anybody else the server would refuse the write, so
 * a form that could only fail is not drawn. The slot written is the one the server named in that
 * column, never one built here, so a provider added from the register is set the same way.
 *
 * **The key is never in React.** `SecretField` holds it in the element and `take()` empties the
 * field in the same call that reads it, so the value exists in this page only for the request.
 * The answer names the slot, that it is held and when; it never carries the key.
 *
 * Task ids: M27.8.7, M5.1.2
 */

import { useState, type FormEvent } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { ConfirmAction } from "./ConfirmAction";
import { FailureNotice } from "../ui/FailureNotice";
import { SecretField, useSecret } from "./ui/secret-field";
import type { ProvidersBody } from "../pages/modelsQuery";

export const SET_A_KEY = "Set a provider's key";
export const SET_A_KEY_INTRO =
  "Choose the provider, paste the key its console gave you, and save. The key goes into this " +
  "install's vault; it is never shown again, and saving a new one replaces the old one.";
export const PROVIDER_LABEL = "Provider";
export const KEY_LABEL = "Key";
export const SAVE_THE_KEY = "Save the key";
export const NOTHING_TYPED = "Paste the key first.";
export const KEEP_THE_OLD_KEY = "Do not save";

export function saveKeyQuestion(provider: string): string {
  return `Save this key for ${provider}?`;
}

export function saveKeyConsequence(provider: string, held: boolean): string {
  return held
    ? `Every question sent to ${provider} uses this key from now on, and the key saved before is replaced. A wrong key stops ${provider} answering until a right one is saved.`
    : `Every question sent to ${provider} uses this key from now on.`;
}

export function keySavedSentence(provider: string, told: string): string {
  return `Key saved for ${provider}. ${told}`;
}

export function credentialPath(slot: string): string {
  return `/credentials/${slot}`;
}

interface Kept {
  readonly told: string;
}

function readKept(payload: unknown): Kept | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const told = (payload as { told?: unknown }).told;
  return typeof told === "string" ? { told } : null;
}

export function ProviderKeyForm({
  body,
  onSaved,
}: {
  readonly body: ProvidersBody;
  /** Called after a key is kept, so the page reads the providers again and the column updates. */
  readonly onSaved: () => void;
}) {
  const settable = body.providers.filter((one) => one.credential !== null);
  const secret = useSecret();
  const [provider, setProvider] = useState<string>(settable[0]?.provider ?? "");
  const [typed, setTyped] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);

  if (settable.length === 0) {
    return null;
  }

  const chosen = settable.find((one) => one.provider === provider);
  const held = chosen?.credential?.held === true;

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!typed) {
      setProblem(NOTHING_TYPED);
      return;
    }
    setProblem(null);
    setSaved(null);
    setFailure(null);
    setAsking(true);
  };

  // Read only once the person has confirmed, so the key leaves the field for the request and no sooner.
  const save = () => {
    const row = chosen;
    if (row === undefined || row.credential === null) {
      setAsking(false);
      return;
    }
    const value = secret.take();
    if (value === "") {
      setAsking(false);
      setProblem(NOTHING_TYPED);
      return;
    }
    setBusy(true);
    const slot = row.credential.slot;
    void (async () => {
      const result = await request<unknown>(credentialPath(slot), { method: "PUT", body: { value } });
      setBusy(false);
      setAsking(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      const kept = readKept(result.data);
      setSaved(keySavedSentence(row.provider, kept === null ? "" : kept.told));
      onSaved();
    })();
  };

  return (
    <form className="card" aria-labelledby="models-set-key" onSubmit={onSubmit}>
      <h3 id="models-set-key">{SET_A_KEY}</h3>
      <p className="note">{SET_A_KEY_INTRO}</p>
      <label>
        {PROVIDER_LABEL}{" "}
        <select
          name="provider"
          value={provider}
          disabled={busy}
          onChange={(event) => {
            setProvider(event.target.value);
          }}
        >
          {settable.map((one) => (
            <option key={one.provider} value={one.provider}>
              {one.provider}
            </option>
          ))}
        </select>
      </label>
      <SecretField
        secret={secret}
        label={KEY_LABEL}
        stored={held}
        disabled={busy}
        invalid={problem !== null}
        onPresenceChange={setTyped}
      />
      {problem === null ? null : <p className="note">{problem}</p>}
      <p>
        <button type="submit" className="button" disabled={busy || asking}>
          {SAVE_THE_KEY}
        </button>
      </p>
      {!asking ? null : (
        <ConfirmAction
          question={saveKeyQuestion(provider)}
          consequence={saveKeyConsequence(provider, held)}
          confirmLabel={SAVE_THE_KEY}
          cancelLabel={KEEP_THE_OLD_KEY}
          busy={busy}
          onConfirm={() => {
            save();
          }}
          onCancel={() => {
            setAsking(false);
          }}
        />
      )}
      {saved === null ? null : (
        <p className="note" role="status">
          {saved}
        </p>
      )}
      {failure === null ? null : <FailureNotice failure={failure} />}
    </form>
  );
}
