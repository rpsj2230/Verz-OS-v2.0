/**
 * The credential the nightly staff sync reads the source with: whether one is held, and a
 * write-only field that replaces it after a confirmation.
 *
 * The value is typed into `ui/secret-field.tsx`, taken out of the field in the same call that
 * builds the confirmed request, and never read back: the API answers whether a credential is held
 * and when it was written, and nothing else. What to paste is the API's own sentence for the chosen
 * source, drawn under the field before anything is sent.
 *
 * Drawn only for a reader the API answers; the page leaves the card out otherwise, so a reader who
 * may not manage it is not told that there is something here they may not see.
 *
 * Task ids: M1.8.6, M27.7.2, M27.16.1
 */

import { useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure, FieldProblem } from "../../api/errors";
import { ConfirmDialog, Fact, FactList, SectionCard } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { SecretField, useSecret } from "../../components/ui/secret-field";
import { FailureNotice } from "../../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../../ui/FieldProblems";
import { CREDENTIAL_API_PATH, CREDENTIAL_BLANK, readCredential, type StaffCredential } from "../staffSourcesQuery";
import { when } from "./staffSourceWords";

export const CREDENTIAL_HEADING = "Sync credential";
export const CREDENTIAL_LEDE = "What the nightly sync reads the staff list with. It is written here and never shown again.";
export const CREDENTIAL_STATE = "State";
export const CREDENTIAL_WRITTEN = "Written";
export const CREDENTIAL_HELD = "Held in the vault";
export const CREDENTIAL_NOT_HELD = "Not held, so the nightly sync cannot read the staff list";
export const NEW_CREDENTIAL = "New credential";
export const REPLACE_CREDENTIAL = "Replace credential";
export const KEEP_CREDENTIAL = "Keep the current one";
export const REPLACE_QUESTION = "Replace the credential the nightly sync reads with?";
export const REPLACE_CONSEQUENCE =
  "The next nightly run reads with the new one. If the source refuses it, that run changes nobody " +
  "and says so under Recent sync runs. The value is never shown again.";
export const SUPPLIED = "Supplied, and never shown again";
export const NOT_REPLACED = "The credential was not replaced";
/** Said when a replace was accepted and the API sent no sentence of its own. */
export const REPLACED = "The credential is held in the vault. The next scheduled run reads with it.";

const FORM = "staff-credential";
const FIELD = "value";

export function SyncCredential({
  credential,
  onDone,
}: {
  readonly credential: StaffCredential;
  /** Told what the API said, so the page can say it and read everything again. */
  readonly onDone: (told: string) => void;
}) {
  const secret = useSecret();
  const [present, setPresent] = useState(false);
  const [blank, setBlank] = useState<FieldProblem[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [pending, setPending] = useState(false);
  const [busy, setBusy] = useState(false);
  const problems: readonly FieldProblem[] = [...blank, ...(failure?.problems ?? [])];
  const described = problemAttributes(problems, FORM, FIELD)["aria-describedby"];

  function ask(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    setFailure(null);
    // A blank field is said beside it before anything is confirmed or sent.
    const found = present ? [] : [{ field: FIELD, code: "blank", message: CREDENTIAL_BLANK }];
    setBlank(found);
    if (found.length === 0) {
      setPending(true);
    }
  }

  function send(): void {
    // The value leaves the field in the same call that empties it, and goes into this body only.
    const body = { value: secret.take() };
    setPresent(false);
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(CREDENTIAL_API_PATH, { method: "PUT", body });
      setBusy(false);
      setPending(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      onDone(readCredential(result.data)?.told ?? REPLACED);
    })();
  }

  const state =
    credential.held === true ? CREDENTIAL_HELD : credential.held === false ? CREDENTIAL_NOT_HELD : credential.told;

  return (
    <SectionCard title={CREDENTIAL_HEADING} lede={CREDENTIAL_LEDE}>
      <div className="flex min-w-0 flex-col gap-4">
        <FactList>
          <Fact label={CREDENTIAL_STATE}>{state}</Fact>
          {credential.set_at === null || credential.set_at === undefined ? null : (
            <Fact label={CREDENTIAL_WRITTEN}>
              <time dateTime={credential.set_at}>{when(credential.set_at)}</time>
            </Fact>
          )}
        </FactList>
        {failure === null ? null : <FailureNotice failure={failure} title={NOT_REPLACED} fields={[FIELD]} />}
        <form id={FORM} className="flex min-w-0 flex-col gap-3" noValidate autoComplete="off" onSubmit={ask}>
          <SecretField
            secret={secret}
            label={NEW_CREDENTIAL}
            stored={credential.held === true}
            description={credential.form}
            disabled={busy}
            invalid={problems.some((one) => one.field === FIELD)}
            onPresenceChange={setPresent}
            {...(described === undefined ? {} : { describedBy: described })}
          />
          <FieldProblems problems={problems} form={FORM} names={FIELD} />
          <div>
            <Button type="submit" variant="outline" className="min-h-11 sm:min-h-8" disabled={busy}>
              {REPLACE_CREDENTIAL}
            </Button>
          </div>
        </form>
      </div>
      <ConfirmDialog
        open={pending}
        question={REPLACE_QUESTION}
        consequence={REPLACE_CONSEQUENCE}
        details={
          <FactList>
            <Fact label={NEW_CREDENTIAL}>{SUPPLIED}</Fact>
          </FactList>
        }
        confirmLabel={REPLACE_CREDENTIAL}
        cancelLabel={KEEP_CREDENTIAL}
        busy={busy}
        onConfirm={() => {
          send();
        }}
        onCancel={() => {
          setPending(false);
        }}
      />
    </SectionCard>
  );
}
