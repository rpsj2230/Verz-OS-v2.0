/**
 * The three acts that change a webhook subscriber: registering one, replacing its signing secret
 * and switching it off.
 *
 * **Every write is sent from a confirmation, in the API's words.** Each opens `kit/ConfirmDialog`
 * with the sentence `brain.webhook_routes` serves for that act (`registering`, `replacing`,
 * `switching_off`), so the words a person agrees to are the words of the system that does it.
 *
 * **Every field says what it accepts before anything is sent**, and a blank one is said beside it in
 * the API's own blank sentence before the confirmation opens (`webhooksQuery.BLANK_SENTENCES`, held
 * to the Python by the page test). Whatever else the API refuses is drawn beside the field it names.
 *
 * **A signing secret is never in React.** It is typed into `ui/secret-field.tsx`; whether anything
 * was typed is all the form knows until the person confirms, when the value is taken out of the
 * field, which empties it, for the one request. The old screen kept it in component state.
 *
 * Task ids: M27.8.12, M27.8.5, M27.16.1
 */

import { useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure, FieldProblem } from "../../api/errors";
import { ConfirmDialog, Drawer, Fact, FactList } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { SecretField, useSecret } from "../../components/ui/secret-field";
import { FailureNotice } from "../../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../../ui/FieldProblems";
import {
  REGISTER_API_PATH,
  REGISTRATION_FORMATS,
  blankRegistrationProblems,
  blankSecretProblems,
  registrationBody,
  secretApiPath,
  secretBody,
  secretFormat,
  switchOffApiPath,
  type WebhooksBody,
} from "../webhooksQuery";
import { ACT_LABELS } from "./webhookActions";

export const REGISTER_DESCRIPTION = "Tell a system outside the company when something happens here.";
export const REPLACE_DESCRIPTION = "A new signing secret for this subscriber. Nothing else about it changes.";
export const ID_LABEL = "Id";
export const ENDPOINT_LABEL = "Address it is told at";
export const KINDS_LABEL = "Told about";
export const SECRET_LABEL = "Signing secret";
export const NEW_SECRET_LABEL = "New signing secret";
export const KEEP_LABEL = "Change nothing";
export const NOT_REGISTERED = "The subscriber was not registered";
export const NOT_REPLACED = "The secret was not replaced";
export const NOT_SWITCHED_OFF = "The subscriber was not switched off";

const REGISTER_FORM = "webhook-register";
const REPLACE_FORM = "webhook-replace";

function readTold(payload: unknown): string {
  if (typeof payload !== "object" || payload === null) {
    return "";
  }
  const told = (payload as { told?: unknown }).told;
  return typeof told === "string" ? told : "";
}

export function RegisterDrawer({
  page,
  onClose,
  onDone,
}: {
  readonly page: WebhooksBody;
  readonly onClose: () => void;
  readonly onDone: (told: string) => void;
}) {
  const [id, setId] = useState("");
  const [endpoint, setEndpoint] = useState("");
  const [kinds, setKinds] = useState<readonly string[]>([]);
  const secret = useSecret();
  const [typed, setTyped] = useState(false);
  const [blank, setBlank] = useState<FieldProblem[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const problems: readonly FieldProblem[] = [...blank, ...(failure?.problems ?? [])];

  const ask = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFailure(null);
    // Only whether a secret was typed is known here; its value stays in the field.
    const found = blankRegistrationProblems(id, endpoint, kinds, typed ? "typed" : "");
    setBlank(found);
    setAsking(found.length === 0);
  };

  const send = () => {
    const body = registrationBody(id, endpoint, kinds, secret.take());
    setTyped(false);
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(REGISTER_API_PATH, { method: "POST", body });
      setBusy(false);
      setAsking(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      onDone(readTold(result.data));
    })();
  };

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
            {KEEP_LABEL}
          </Button>
          <Button type="submit" form={REGISTER_FORM} disabled={busy}>
            {ACT_LABELS.reviewRegistration}
          </Button>
        </>
      }
    >
      <div className="flex min-w-0 flex-col gap-3">
        {failure === null ? null : (
          <FailureNotice failure={failure} title={NOT_REGISTERED} fields={["subscriber_id", "endpoint", "kinds", "secret"]} />
        )}
        <form
          id={REGISTER_FORM}
          aria-label={ACT_LABELS.register}
          className="flex flex-col gap-4"
          noValidate
          autoComplete="off"
          onSubmit={ask}
        >
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${REGISTER_FORM}-id`}>{ID_LABEL}</Label>
            <Input
              id={`${REGISTER_FORM}-id`}
              name="subscriber_id"
              value={id}
              spellCheck={false}
              disabled={busy}
              {...problemAttributes(problems, REGISTER_FORM, "subscriber_id")}
              onChange={(event) => {
                setId(event.target.value);
              }}
            />
            <p className="m-0 text-[12.5px] leading-snug text-dim">{REGISTRATION_FORMATS.subscriber_id}</p>
            <FieldProblems problems={problems} form={REGISTER_FORM} names="subscriber_id" />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor={`${REGISTER_FORM}-endpoint`}>{ENDPOINT_LABEL}</Label>
            <Input
              id={`${REGISTER_FORM}-endpoint`}
              name="endpoint"
              type="url"
              value={endpoint}
              spellCheck={false}
              disabled={busy}
              {...problemAttributes(problems, REGISTER_FORM, "endpoint")}
              onChange={(event) => {
                setEndpoint(event.target.value);
              }}
            />
            <p className="m-0 text-[12.5px] leading-snug text-dim">{REGISTRATION_FORMATS.endpoint}</p>
            <FieldProblems problems={problems} form={REGISTER_FORM} names="endpoint" />
          </div>
          <fieldset className="m-0 flex flex-col gap-2 border-0 p-0">
            <legend className="mb-1 text-sm font-medium text-ink">{KINDS_LABEL}</legend>
            {page.kinds.map((kind) => (
              <label key={kind} className="flex min-h-11 items-center gap-2 text-[13px] text-ink sm:min-h-7">
                <input
                  type="checkbox"
                  name="kinds"
                  className="size-4"
                  checked={kinds.includes(kind)}
                  disabled={busy}
                  {...problemAttributes(problems, REGISTER_FORM, "kinds")}
                  onChange={(event) => {
                    setKinds(event.target.checked ? [...kinds, kind] : kinds.filter((one) => one !== kind));
                  }}
                />
                <span className="font-mono text-[12px]">{kind}</span>
              </label>
            ))}
            <p className="m-0 text-[12.5px] leading-snug text-dim">{REGISTRATION_FORMATS.kinds}</p>
            <FieldProblems problems={problems} form={REGISTER_FORM} names="kinds" />
          </fieldset>
          <SecretField
            secret={secret}
            label={SECRET_LABEL}
            stored={false}
            description={secretFormat(page.secret_minimum)}
            disabled={busy}
            onPresenceChange={setTyped}
          />
          <FieldProblems problems={problems} form={REGISTER_FORM} names="secret" />
        </form>
      </div>
      <ConfirmDialog
        open={asking}
        question={`Register ${id} to be told at ${endpoint}?`}
        consequence={page.registering}
        details={
          <FactList>
            <Fact label={KINDS_LABEL}>{kinds.join(", ")}</Fact>
          </FactList>
        }
        confirmLabel={ACT_LABELS.reviewRegistration}
        cancelLabel={KEEP_LABEL}
        busy={busy}
        onConfirm={send}
        onCancel={() => {
          setAsking(false);
        }}
      />
    </Drawer>
  );
}

export function ReplaceSecretDrawer({
  page,
  subscriberId,
  onClose,
  onDone,
}: {
  readonly page: WebhooksBody;
  readonly subscriberId: string;
  readonly onClose: () => void;
  readonly onDone: (told: string) => void;
}) {
  const secret = useSecret();
  const [typed, setTyped] = useState(false);
  const [blank, setBlank] = useState<FieldProblem[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const problems: readonly FieldProblem[] = [...blank, ...(failure?.problems ?? [])];

  const ask = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFailure(null);
    const found = blankSecretProblems(typed ? "typed" : "");
    setBlank(found);
    setAsking(found.length === 0);
  };

  const send = () => {
    const body = secretBody(secret.take());
    setTyped(false);
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(secretApiPath(subscriberId), { method: "POST", body });
      setBusy(false);
      setAsking(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      onDone(readTold(result.data));
    })();
  };

  return (
    <Drawer
      open
      onOpenChange={(open) => {
        if (!open && !busy) {
          onClose();
        }
      }}
      title={`${ACT_LABELS.replace}: ${subscriberId}`}
      description={REPLACE_DESCRIPTION}
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            {KEEP_LABEL}
          </Button>
          <Button type="submit" form={REPLACE_FORM} disabled={busy}>
            {ACT_LABELS.replace}
          </Button>
        </>
      }
    >
      <div className="flex min-w-0 flex-col gap-3">
        {failure === null ? null : <FailureNotice failure={failure} title={NOT_REPLACED} fields={["secret"]} />}
        <form id={REPLACE_FORM} aria-label={`${ACT_LABELS.replace} of ${subscriberId}`} className="flex flex-col gap-4" noValidate onSubmit={ask}>
          <SecretField
            secret={secret}
            label={NEW_SECRET_LABEL}
            stored
            description={secretFormat(page.secret_minimum)}
            disabled={busy}
            onPresenceChange={setTyped}
          />
          <FieldProblems problems={problems} form={REPLACE_FORM} names="secret" />
        </form>
      </div>
      <ConfirmDialog
        open={asking}
        question={`Replace the signing secret of ${subscriberId}?`}
        consequence={page.replacing}
        confirmLabel={ACT_LABELS.replace}
        cancelLabel={KEEP_LABEL}
        busy={busy}
        onConfirm={send}
        onCancel={() => {
          setAsking(false);
        }}
      />
    </Drawer>
  );
}

export function SwitchOffDialog({
  page,
  subscriberId,
  onClose,
  onDone,
}: {
  readonly page: WebhooksBody;
  readonly subscriberId: string;
  readonly onClose: () => void;
  readonly onDone: (told: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const send = () => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(switchOffApiPath(subscriberId), { method: "POST" });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      onDone(readTold(result.data));
    })();
  };
  return (
    <ConfirmDialog
      open
      question={`Switch off ${subscriberId}?`}
      consequence={page.switching_off}
      details={failure === null ? undefined : <FailureNotice failure={failure} title={NOT_SWITCHED_OFF} />}
      confirmLabel={ACT_LABELS.switchOff}
      cancelLabel={KEEP_LABEL}
      busy={busy}
      onConfirm={send}
      onCancel={onClose}
    />
  );
}
