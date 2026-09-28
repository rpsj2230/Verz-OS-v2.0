/**
 * Setting or replacing one slot's value: `PUT /api/v1/credentials/{family}/{name}`.
 *
 * **The value is never in React.** Each field is a `SecretField`, whose value lives in the element
 * and leaves it through `take()`, which empties the field in the same call, and it is read only once
 * the person has confirmed, so it exists in this page for the length of one request. The answer says
 * the slot is held and when, and what that means for whatever uses it; it never carries the value,
 * and nothing here keeps one to show.
 *
 * **What the field accepts is said before anything is sent**, under the field, in the API's own
 * words (`FORMAT_TOLD`): one unbroken line, how long, and what happens to a line break at the end.
 * A problem the API still finds is drawn beside the field it names, and a problem naming no field on
 * this form under the failure, `api/problems.ts`' rule.
 *
 * **One form for every kind.** A slot of one field sends `value`; the object store's key pair sends
 * both of its fields under `values`, in one request, because a pair written a field at a time is
 * never a pair the store accepts. Which fields a slot takes is the API's answer on the slot's page,
 * so nothing here decides it.
 *
 * Task ids: M27.11.10, M27.15.50, M27.8.7
 */

import { useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { problemsFor, unmatchedProblems } from "../../api/problems";
import { ConfirmDialog, FailureState } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { SecretField, useSecret, type SecretHandle } from "../../components/ui/secret-field";
import { credentialApiPath, type CredentialDetail } from "./credentialRows";

export const SET_VALUE = "Set the value";
export const REPLACE_VALUE = "Replace the value";
export const KEEP_IT = "Do not change it";
export const TYPE_FIRST = "Type or paste a value into every field first.";
export const SAVING = "Saving.";

export function saveQuestion(detail: CredentialDetail): string {
  const verb = detail.row.held === true ? "Replace" : "Set";
  return `${verb} the credential for ${detail.row.holder}?`;
}

export function saveConsequence(detail: CredentialDetail): string {
  const replaced =
    detail.row.held === true ? " The value held now is replaced, and it cannot be brought back from here." : "";
  return `${detail.takesEffectTold}${replaced}`;
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

export function SetValueForm({
  detail,
  onSaved,
}: {
  readonly detail: CredentialDetail;
  /** Called with the API's sentence once the value is held; the page reads the slot again. */
  readonly onSaved: (sentence: string) => void;
}) {
  // Two handles always, because hooks cannot follow a list: no slot has more than two fields.
  const first = useSecret();
  const second = useSecret();
  const handles: readonly SecretHandle[] = [first, second];
  const fields = detail.fields.slice(0, handles.length);
  const [typed, setTyped] = useState<readonly boolean[]>(() => fields.map(() => false));
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (fields.length === 0 || typed.some((one) => !one)) {
      setProblem(TYPE_FIRST);
      return;
    }
    setProblem(null);
    setFailure(null);
    setAsking(true);
  };

  // Read only once the person has confirmed, so the value leaves the field for the request and no sooner.
  const save = () => {
    const values = fields.map((one, index) => [one.field, handles[index]?.take() ?? ""] as const);
    if (values.some(([, value]) => value === "")) {
      setAsking(false);
      setProblem(TYPE_FIRST);
      return;
    }
    const body =
      fields.length === 1 && fields[0]?.field === "value"
        ? { value: values[0]?.[1] ?? "" }
        : { values: Object.fromEntries(values) };
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(credentialApiPath(detail.row.slot), { method: "PUT", body });
      setBusy(false);
      setAsking(false);
      setTyped(fields.map(() => false));
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      onSaved(readKept(result.data)?.told ?? "");
    })();
  };

  const names = fields.map((one) => one.field);
  const problems = failure?.problems ?? [];
  const held = detail.row.held === true;
  return (
    <form className="flex min-w-0 flex-col gap-4" aria-label={`Credential for ${detail.row.holder}`} onSubmit={onSubmit}>
      {fields.map((one, index) => {
        const handle = handles[index];
        const said = problemsFor(problems, one.field);
        return handle === undefined ? null : (
          <div key={one.field} className="flex min-w-0 flex-col gap-1">
            <SecretField
              secret={handle}
              label={one.label}
              stored={held}
              description={one.accepts}
              disabled={busy}
              invalid={said.length > 0}
              onPresenceChange={(present) => {
                setTyped((now) => now.map((was, at) => (at === index ? present : was)));
              }}
            />
            {said.map((sentence) => (
              <p key={sentence} className="m-0 text-[12.5px] text-crit">
                {sentence}
              </p>
            ))}
          </div>
        );
      })}
      {problem === null ? null : <p className="m-0 text-[12.5px] text-crit">{problem}</p>}
      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" className="min-h-11 sm:min-h-9" disabled={busy || asking}>
          {held ? REPLACE_VALUE : SET_VALUE}
        </Button>
        {busy ? (
          <span role="status" className="text-[12.5px] text-dim">
            {SAVING}
          </span>
        ) : null}
      </div>
      <ConfirmDialog
        open={asking}
        question={saveQuestion(detail)}
        consequence={saveConsequence(detail)}
        confirmLabel={held ? REPLACE_VALUE : SET_VALUE}
        cancelLabel={KEEP_IT}
        busy={busy}
        onConfirm={() => {
          save();
        }}
        onCancel={() => {
          setAsking(false);
        }}
      />
      {failure === null ? null : (
        <FailureState failure={failure}>
          {unmatchedProblems(problems, names).map((one) => (
            <p key={`${one.field}-${one.code}`} className="m-0 text-[12.5px]">
              {one.message}
            </p>
          ))}
        </FailureState>
      )}
    </form>
  );
}
