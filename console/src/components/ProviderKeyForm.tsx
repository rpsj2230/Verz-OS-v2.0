/**
 * Adding or replacing one provider's key, on that provider's row of the Providers table.
 *
 * The write is `PUT /credentials/{slot}` (`brain.credential_routes`). Until 2026-09-22 it was a
 * separate card below the table with a provider picker, and the owner read the screen as too
 * complicated: the key belongs to a provider, so the field opens on that provider's row from its
 * Add key or Replace key button, and there is no second place to choose the provider from.
 *
 * **Drawn only for a row the providers answer sent the vault's column for**, which is a reader
 * who holds `admin:credential` over everything; for anybody else the server would refuse the
 * write, so a field that could only fail is not offered. The slot written is the one the server
 * named on that row, never one built here, so a provider added from the register is set the same
 * way as a built-in one.
 *
 * **The key is never in React.** `SecretField` holds it in the element and `take()` empties the
 * field in the same call that reads it, so the value exists in this page only for the request.
 * The answer names the slot, that it is held and when; it never carries the key, and the row
 * closes the field once the key is kept, so nothing typed outlives the save.
 *
 * Task ids: M27.8.7, M5.1.2, M5.7.1
 */

import { useState, type FormEvent } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { ConfirmAction } from "./ConfirmAction";
import { FailureNotice } from "../ui/FailureNotice";
import { SecretField, useSecret } from "./ui/secret-field";
import type { ProviderStateRow } from "../pages/modelsQuery";

export const KEY_LABEL = "Key";
export const KEY_INTRO =
  "Paste the key the provider's own console gave you. It goes into this install's vault and is " +
  "never shown again.";
export const SAVE_THE_KEY = "Save the key";
export const CLOSE_THE_KEY = "Cancel";
export const NOTHING_TYPED = "Paste the key first.";
export const KEEP_THE_OLD_KEY = "Do not save";

export function saveKeyQuestion(name: string): string {
  return `Save this key for ${name}?`;
}

export function saveKeyConsequence(name: string, held: boolean): string {
  return held
    ? `Every question sent to ${name} uses this key from now on, and the key saved before is replaced. A wrong key stops ${name} answering until a right one is saved.`
    : `Every question sent to ${name} uses this key from now on.`;
}

export function keySavedSentence(name: string, told: string): string {
  return `Key saved for ${name}. ${told}`;
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
  row,
  name,
  held,
  onSaved,
  onClose,
}: {
  /** The provider's row, whose `credential.slot` is where the key is written. */
  readonly row: ProviderStateRow;
  /** The provider as a person knows it. */
  readonly name: string;
  /** Whether a key is already held, so the confirmation says one is replaced. */
  readonly held: boolean;
  /** Called with the sentence to show once the key is kept; the row closes the field. */
  readonly onSaved: (sentence: string) => void;
  readonly onClose: () => void;
}) {
  const secret = useSecret();
  const [typed, setTyped] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!typed) {
      setProblem(NOTHING_TYPED);
      return;
    }
    setProblem(null);
    setFailure(null);
    setAsking(true);
  };

  // Read only once the person has confirmed, so the key leaves the field for the request and no sooner.
  const save = () => {
    if (row.credential === null) {
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
      onSaved(keySavedSentence(name, kept === null ? "" : kept.told));
    })();
  };

  return (
    <form className="form" aria-label={`Key for ${name}`} onSubmit={onSubmit}>
      <p className="note">{KEY_INTRO}</p>
      <SecretField
        secret={secret}
        label={`${KEY_LABEL} for ${name}`}
        stored={held}
        disabled={busy}
        invalid={problem !== null}
        onPresenceChange={setTyped}
      />
      {problem === null ? null : <p className="note">{problem}</p>}
      <div className="form-actions">
        <button type="submit" className="button" disabled={busy || asking}>
          {SAVE_THE_KEY}
        </button>{" "}
        <button type="button" className="button" disabled={busy} onClick={onClose}>
          {CLOSE_THE_KEY}
        </button>
      </div>
      {!asking ? null : (
        <ConfirmAction
          question={saveKeyQuestion(name)}
          consequence={saveKeyConsequence(name, held)}
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
      {failure === null ? null : <FailureNotice failure={failure} />}
    </form>
  );
}
