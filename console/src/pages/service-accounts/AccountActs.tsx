/**
 * The acts on service accounts, shared by the list and an account's page: register, issue a key
 * (shown once), revoke a key, and retire the account.
 *
 * **Every act is confirmed, and says what it will do before anything is sent.** Registering and
 * issuing are confirmed as well as the two that end something, because each creates a credential
 * somebody could use; the confirmation names the account and when it stops working.
 *
 * **The key is drawn from the issue's answer and from nothing else**, in the drawer that issued it,
 * with a copy button, until the person says they have kept it; then it is gone from the page. See
 * `serviceAccountsQuery.A_KEY_IS_SHOWN_ONCE_AND_NEVER_READ_BACK`.
 *
 * **Each form says what every field accepts before it is sent**, and a blank field is told beside
 * itself without a request; everything else (a wildcard, an approve or admin capability, an id of
 * the wrong shape) is the API's to refuse, in its sentence, beside the field it names.
 *
 * Task ids: M27.11.5, M27.15.26, M27.16.1
 */

import { useCallback, useState, type FormEvent, type ReactNode } from "react";
import { request } from "../../api/client";
import type { ApiFailure, FieldProblem } from "../../api/errors";
import { ConfirmDialog, Drawer, Fact, FactList, Note } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Textarea } from "../../components/ui/textarea";
import { FailureNotice } from "../../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../../ui/FieldProblems";
import {
  accountName,
  blankKeyProblems,
  blankRegistrationProblems,
  ceilingFrom,
  CEILING_RULE,
  ID_SHAPE,
  ISSUE_KEY_API_PATH,
  keyBody,
  readIssuedKey,
  registrationBody,
  RETIRE_ACCOUNT_API_PATH,
  retirementBody,
  REVOKE_KEY_API_PATH,
  revocationBody,
  SERVICE_ACCOUNTS_API_PATH,
  toldBy,
  when,
  type AccountRow,
  type IssuedKeyBody,
  type KeyRow,
} from "../serviceAccountsQuery";
import { ACT_LABELS, NOT_OFFERED } from "./serviceAccountActions";

export const CANCEL = "Change nothing";
export const REVIEW = "Review";
export const REGISTER_DESCRIPTION = "An integration that calls this system with a key, acting at your reach and never more.";
export const ISSUE_DESCRIPTION = "A key for this account. It is shown once, when it is issued.";
export const NEW_KEY_HEADING = "The new key";
export const COPY_LABEL = "Copy key";
export const COPIED = "Copied.";
export const COPY_UNAVAILABLE = "This browser would not copy it. Select the key and copy it by hand.";
export const KEPT_LABEL = "I have kept it";
export const NOT_REGISTERED = "The account was not registered";
export const NOT_ISSUED = "The key was not issued";
export const NOT_REVOKED = "The key was not revoked";
export const NOT_RETIRED = "The account was not retired";

/** What each field accepts, said under it before anything is sent. */
export const HINTS = Object.freeze({
  client_id: ID_SHAPE,
  label: "A name people will recognise, such as Weekly report export. Optional.",
  ceiling: CEILING_RULE,
  not_after: "The account and every key it has stop working at the end of this day.",
  subject:
    "Only for an integration that signs in through the identity provider with its own client. Leave it empty otherwise.",
  key_label: "A name for this key, such as where it is used. Optional.",
  key_not_after: "The key stops working at the end of this day, or when the account does if that is sooner.",
});

const REGISTER_FORM = "service-account";
const REGISTER_FIELDS: readonly string[] = ["client_id", "label", "ceiling", "not_after", "subject"];
const KEY_FORM = "service-account-key";
const KEY_FIELDS: readonly string[] = ["client_id", "label", "not_after"];

/** What registering says: the account, and any capability it cannot use because you lack it now. */
export function registered(clientId: string, notHeld: readonly string[]): string {
  const said = `${clientId} is registered. Issue it a key to use it.`;
  return notHeld.length === 0
    ? said
    : `${said} You do not hold ${notHeld.join(", ")} now, so it cannot use ${notHeld.length === 1 ? "that" : "those"} yet.`;
}

function Field({
  form,
  name,
  label,
  hint,
  problems,
  children,
}: {
  readonly form: string;
  readonly name: string;
  readonly label: string;
  readonly hint: string;
  readonly problems: readonly FieldProblem[];
  readonly children: (describedBy: string) => ReactNode;
}) {
  const hintId = `${form}-${name}-hint`;
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <Label htmlFor={`${form}-${name}`}>{label}</Label>
      {children(hintId)}
      <p id={hintId} className="m-0 text-[12.5px] leading-snug text-dim">
        {hint}
      </p>
      <FieldProblems problems={problems} form={form} names={[name]} />
    </div>
  );
}

// ------------------------------------------------------------------------------ register

export function RegisterDrawer({
  onClose,
  onDone,
}: {
  readonly onClose: () => void;
  readonly onDone: (clientId: string, told: string) => void;
}) {
  const [clientId, setClientId] = useState("");
  const [label, setLabel] = useState("");
  const [ceiling, setCeiling] = useState("");
  const [lapsesOn, setLapsesOn] = useState("");
  const [subject, setSubject] = useState("");
  const [blank, setBlank] = useState<readonly FieldProblem[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [pending, setPending] = useState(false);
  const [busy, setBusy] = useState(false);
  const problems: readonly FieldProblem[] = [...blank, ...(failure?.problems ?? [])];

  function ask(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    setFailure(null);
    const found = blankRegistrationProblems(clientId, ceiling, lapsesOn);
    setBlank(found);
    if (found.length === 0) {
      setPending(true);
    }
  }

  function send(): void {
    setBusy(true);
    void (async () => {
      const body = registrationBody(clientId, label, ceiling, lapsesOn, subject);
      const result = await request<unknown>(SERVICE_ACCOUNTS_API_PATH, { method: "POST", body });
      setBusy(false);
      setPending(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      const answered = result.data as Partial<AccountRow>;
      onDone(body.client_id, registered(body.client_id, answered.not_held_now ?? []));
    })();
  }

  return (
    <Drawer
      open
      onOpenChange={(open) => {
        if (!open && !busy) {
          onClose();
        }
      }}
      title={ACT_LABELS.register}
      description={REGISTER_DESCRIPTION}
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            {CANCEL}
          </Button>
          <Button type="submit" form={REGISTER_FORM} disabled={busy}>
            {REVIEW}
          </Button>
        </>
      }
    >
      <div className="flex min-w-0 flex-col gap-3">
        {failure === null ? null : <FailureNotice failure={failure} title={NOT_REGISTERED} fields={REGISTER_FIELDS} />}
        <form id={REGISTER_FORM} className="flex flex-col gap-4" noValidate autoComplete="off" onSubmit={ask}>
          <Field form={REGISTER_FORM} name="client_id" label="Account ID" hint={HINTS.client_id} problems={problems}>
            {(describedBy) => (
              <Input
                id={`${REGISTER_FORM}-client_id`}
                name="client_id"
                value={clientId}
                spellCheck={false}
                aria-describedby={describedBy}
                {...problemAttributes(problems, REGISTER_FORM, ["client_id"])}
                onChange={(event) => {
                  setClientId(event.target.value);
                }}
              />
            )}
          </Field>
          <Field form={REGISTER_FORM} name="label" label="Name" hint={HINTS.label} problems={problems}>
            {(describedBy) => (
              <Input
                id={`${REGISTER_FORM}-label`}
                name="label"
                value={label}
                aria-describedby={describedBy}
                onChange={(event) => {
                  setLabel(event.target.value);
                }}
              />
            )}
          </Field>
          <Field form={REGISTER_FORM} name="ceiling" label="Capabilities it may use" hint={HINTS.ceiling} problems={problems}>
            {(describedBy) => (
              <Textarea
                id={`${REGISTER_FORM}-ceiling`}
                name="ceiling"
                rows={4}
                value={ceiling}
                spellCheck={false}
                aria-describedby={describedBy}
                {...problemAttributes(problems, REGISTER_FORM, ["ceiling"])}
                onChange={(event) => {
                  setCeiling(event.target.value);
                }}
              />
            )}
          </Field>
          <Field form={REGISTER_FORM} name="not_after" label="Stops working after" hint={HINTS.not_after} problems={problems}>
            {(describedBy) => (
              <Input
                id={`${REGISTER_FORM}-not_after`}
                name="not_after"
                type="date"
                value={lapsesOn}
                aria-describedby={describedBy}
                {...problemAttributes(problems, REGISTER_FORM, ["not_after"])}
                onChange={(event) => {
                  setLapsesOn(event.target.value);
                }}
              />
            )}
          </Field>
          <Field form={REGISTER_FORM} name="subject" label="Identity provider client (optional)" hint={HINTS.subject} problems={problems}>
            {(describedBy) => (
              <Input
                id={`${REGISTER_FORM}-subject`}
                name="subject"
                value={subject}
                spellCheck={false}
                aria-describedby={describedBy}
                onChange={(event) => {
                  setSubject(event.target.value);
                }}
              />
            )}
          </Field>
        </form>
        <Note>{NOT_OFFERED.changeOwner}</Note>
      </div>
      <ConfirmDialog
        open={pending}
        question={`Register ${clientId.trim()}?`}
        consequence="It acts at your reach, narrowed to the capabilities listed, and holds nothing of its own. It can do nothing until it has a key."
        details={
          <FactList>
            <Fact label="Capabilities">{ceilingFrom(ceiling).join(", ")}</Fact>
            <Fact label="Stops working after">{lapsesOn}</Fact>
          </FactList>
        }
        confirmLabel={ACT_LABELS.register}
        cancelLabel={CANCEL}
        busy={busy}
        onConfirm={send}
        onCancel={() => {
          setPending(false);
        }}
      />
    </Drawer>
  );
}

// --------------------------------------------------------------------------------- issue

/** The key, whole, this once, and the copy button beside it. */
function NewKey({ issued, onKept }: { readonly issued: IssuedKeyBody; readonly onKept: () => void }) {
  const [copied, setCopied] = useState<string | null>(null);
  const copy = useCallback(() => {
    const clipboard = typeof navigator === "undefined" ? undefined : navigator.clipboard;
    if (clipboard === undefined) {
      setCopied(COPY_UNAVAILABLE);
      return;
    }
    void clipboard.writeText(issued.key).then(
      () => {
        setCopied(COPIED);
      },
      () => {
        setCopied(COPY_UNAVAILABLE);
      },
    );
  }, [issued.key]);
  return (
    <section aria-label={NEW_KEY_HEADING} className="flex min-w-0 flex-col gap-3">
      <h3 className="m-0 text-sm font-semibold text-ink">{NEW_KEY_HEADING}</h3>
      <p aria-label="Key" className="m-0 rounded-md border border-line bg-sunk p-3 font-mono text-[12.5px] text-ink [overflow-wrap:anywhere]">
        {issued.key}
      </p>
      <Note kind="not-yet">{issued.shown_once}</Note>
      <p className="m-0 text-[12.5px] text-dim">It stops working after {when(issued.lapses_at)}.</p>
      {copied === null ? null : (
        <p role="status" className="m-0 text-[12.5px] text-dim">
          {copied}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" onClick={copy}>
          {COPY_LABEL}
        </Button>
        <Button type="button" onClick={onKept}>
          {KEPT_LABEL}
        </Button>
      </div>
    </section>
  );
}

export function IssueKeyDrawer({
  account,
  onClose,
  onDone,
}: {
  readonly account: AccountRow;
  readonly onClose: () => void;
  /** Called once the person has kept the key, so the page reads its keys again. */
  readonly onDone: () => void;
}) {
  const [label, setLabel] = useState("");
  const [lapsesOn, setLapsesOn] = useState("");
  const [blank, setBlank] = useState<readonly FieldProblem[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [pending, setPending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [issued, setIssued] = useState<IssuedKeyBody | null>(null);
  const problems: readonly FieldProblem[] = [...blank, ...(failure?.problems ?? [])];
  const name = accountName(account);

  function ask(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    setFailure(null);
    const found = blankKeyProblems(lapsesOn);
    setBlank(found);
    if (found.length === 0) {
      setPending(true);
    }
  }

  function send(): void {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(ISSUE_KEY_API_PATH, {
        method: "POST",
        body: keyBody(account.client_id, label, lapsesOn),
      });
      setBusy(false);
      setPending(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setIssued(readIssuedKey(result.data));
    })();
  }

  const close = () => {
    if (issued !== null) {
      onDone();
      return;
    }
    onClose();
  };

  return (
    <Drawer
      open
      onOpenChange={(open) => {
        // A key on screen is closed only by saying it was kept, so it is not lost to a stray press.
        if (!open && !busy && issued === null) {
          close();
        }
      }}
      title={`${ACT_LABELS.issue}: ${name}`}
      description={ISSUE_DESCRIPTION}
      footer={
        issued === null ? (
          <>
            <Button variant="outline" onClick={close} disabled={busy}>
              {CANCEL}
            </Button>
            <Button type="submit" form={KEY_FORM} disabled={busy}>
              {REVIEW}
            </Button>
          </>
        ) : undefined
      }
    >
      {issued === null ? (
        <div className="flex min-w-0 flex-col gap-3">
          {failure === null ? null : <FailureNotice failure={failure} title={NOT_ISSUED} fields={KEY_FIELDS} />}
          <form id={KEY_FORM} className="flex flex-col gap-4" noValidate autoComplete="off" onSubmit={ask}>
            <Field form={KEY_FORM} name="label" label="Key name" hint={HINTS.key_label} problems={problems}>
              {(describedBy) => (
                <Input
                  id={`${KEY_FORM}-label`}
                  name="label"
                  value={label}
                  aria-describedby={describedBy}
                  onChange={(event) => {
                    setLabel(event.target.value);
                  }}
                />
              )}
            </Field>
            <Field form={KEY_FORM} name="not_after" label="Key stops working after" hint={HINTS.key_not_after} problems={problems}>
              {(describedBy) => (
                <Input
                  id={`${KEY_FORM}-not_after`}
                  name="not_after"
                  type="date"
                  value={lapsesOn}
                  aria-describedby={describedBy}
                  {...problemAttributes(problems, KEY_FORM, ["not_after"])}
                  onChange={(event) => {
                    setLapsesOn(event.target.value);
                  }}
                />
              )}
            </Field>
          </form>
          <Note>{NOT_OFFERED.rotate}</Note>
        </div>
      ) : (
        <NewKey issued={issued} onKept={onDone} />
      )}
      <ConfirmDialog
        open={pending}
        question={`Issue a key for ${name}?`}
        consequence="Anyone holding the key can call this system as this account until it stops working or is revoked. It is shown once."
        confirmLabel={ACT_LABELS.issue}
        cancelLabel={CANCEL}
        busy={busy}
        onConfirm={send}
        onCancel={() => {
          setPending(false);
        }}
      />
    </Drawer>
  );
}

// --------------------------------------------------------------------- revoke and retire

/** What a pending revocation or retirement is about. */
export type Ending =
  | { readonly kind: "revoke"; readonly account: AccountRow; readonly key: KeyRow }
  | { readonly kind: "retire"; readonly account: AccountRow };

/** The confirmation that revokes a key or retires an account, and its failure. */
export function EndingDialog({
  ending,
  onClose,
  onDone,
}: {
  readonly ending: Ending | null;
  readonly onClose: () => void;
  readonly onDone: (ending: Ending, told: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  function send(chosen: Ending): void {
    setBusy(true);
    void (async () => {
      const result =
        chosen.kind === "revoke"
          ? await request<unknown>(REVOKE_KEY_API_PATH, { method: "POST", body: revocationBody(chosen.key.handle) })
          : await request<unknown>(RETIRE_ACCOUNT_API_PATH, {
              method: "POST",
              body: retirementBody(chosen.account.client_id),
            });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      setFailure(null);
      onDone(chosen, toldBy(result.data));
    })();
  }

  if (ending === null) {
    return null;
  }
  const name = accountName(ending.account);
  const keyName = ending.kind === "revoke" ? (ending.key.label.trim() === "" ? "this key" : `the key ${ending.key.label}`) : "";
  return (
    <ConfirmDialog
      open
      question={ending.kind === "revoke" ? `Revoke ${keyName} of ${name}?` : `Retire ${name}?`}
      consequence={
        ending.kind === "revoke"
          ? "The key is refused from its next use, and an integration still using it stops working. The revocation is recorded with your name."
          : "The account and every key it has are refused from their next use. A retired account cannot be brought back. The retirement is recorded with your name."
      }
      details={
        failure === null ? undefined : (
          <FailureNotice failure={failure} title={ending.kind === "revoke" ? NOT_REVOKED : NOT_RETIRED} />
        )
      }
      confirmLabel={ending.kind === "revoke" ? "Revoke key" : ACT_LABELS.retire}
      cancelLabel={CANCEL}
      busy={busy}
      onConfirm={() => {
        send(ending);
      }}
      onCancel={() => {
        setFailure(null);
        onClose();
      }}
    />
  );
}