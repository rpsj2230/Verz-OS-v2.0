/**
 * The acts on the Notifications page that change something: a notice's switch, the relay's
 * configuration, its password, a test message, and removing the relay.
 *
 * **Every write is sent from a confirmation, in the API's words.** Each opens `kit/ConfirmDialog`
 * with the sentence `brain.notification_routes` serves for it (`switching_off`, `switching_on`,
 * `saving_email`, `keeping_password`, `sending_trial`, `removing_email`), so the words a person
 * agrees to are the words of the system that does it.
 *
 * **Every field says what it accepts before anything is sent** (`notificationsQuery.RELAY_FORMATS`),
 * a blank one is said beside it in the API's own blank sentence before a confirmation opens, and
 * whatever the API still refuses is drawn beside the field it names.
 *
 * **The password is never in React.** It is typed into `ui/secret-field.tsx`; the form knows only
 * whether something was typed until the person confirms, when it is taken out of the field for the
 * one request. The old screen kept it in component state.
 *
 * **Removing the relay retires its configuration and keeps the password** (`POST .../removal`),
 * which the confirmation says in the API's words; it is offered only while a relay is saved.
 *
 * Task ids: M27.8.11, M27.8.5, M27.16.1
 */

import { useState, type FormEvent } from "react";
import { request } from "../../api/client";
import type { ApiFailure, FieldProblem } from "../../api/errors";
import { ConfirmDialog, Drawer } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { SecretField, useSecret } from "../../components/ui/secret-field";
import { FailureNotice } from "../../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../../ui/FieldProblems";
import {
  PASSWORD_API_PATH,
  RELAY_API_PATH,
  RELAY_FORMATS,
  REMOVAL_API_PATH,
  TRIAL_API_PATH,
  blankPasswordProblems,
  blankRelayProblems,
  blankTrialProblems,
  noticeApiPath,
  passwordBody,
  portNumber,
  relayBody,
  switchBody,
  trialBody,
  type NoticeRow,
  type NotificationsBody,
} from "../notificationsQuery";

export const SAVE_RELAY_LABEL = "Save relay";
export const EDIT_RELAY_LABEL = "Edit relay";
export const SET_UP_RELAY_LABEL = "Set up relay";
export const PASSWORD_LABEL = "Replace password";
export const SAVE_PASSWORD_LABEL = "Save password";
export const TRIAL_LABEL = "Send test message";
export const REMOVE_LABEL = "Remove relay";
export const SWITCH_OFF_LABEL = "Switch off";
export const SWITCH_ON_LABEL = "Switch on";
export const KEEP_LABEL = "Change nothing";
export const RELAY_DESCRIPTION = "Where this install's mail is sent through.";
export const PASSWORD_DESCRIPTION = "The password for the relay's user name. Nothing else changes.";
export const TRIAL_DESCRIPTION = "One test message through the saved relay, sent once for each saved configuration.";
export const NOT_DONE = "Nothing was changed";

const RELAY_FORM = "relay-save";
const PASSWORD_FORM = "relay-password";
const TRIAL_FORM = "relay-trial";

function readTold(payload: unknown): string {
  if (typeof payload !== "object" || payload === null) {
    return "";
  }
  const told = (payload as { told?: unknown }).told;
  return typeof told === "string" ? told : "";
}

/** One labelled text field with what it accepts under it and its problems beside it. */
function TextField({
  form,
  name,
  label,
  format,
  value,
  onChange,
  problems,
  busy,
  type = "text",
  inputMode,
}: {
  readonly form: string;
  readonly name: string;
  readonly label: string;
  readonly format: string;
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly problems: readonly FieldProblem[];
  readonly busy: boolean;
  readonly type?: string | undefined;
  readonly inputMode?: "numeric" | undefined;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <Label htmlFor={`${form}-${name}`}>{label}</Label>
      <Input
        id={`${form}-${name}`}
        name={name}
        type={type}
        inputMode={inputMode}
        value={value}
        autoComplete="off"
        spellCheck={false}
        disabled={busy}
        {...problemAttributes(problems, form, name)}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
      <p className="m-0 text-[12.5px] leading-snug text-dim">{format}</p>
      <FieldProblems problems={problems} form={form} names={name} />
    </div>
  );
}

function Footer({ form, label, busy, onClose }: { readonly form: string; readonly label: string; readonly busy: boolean; readonly onClose: () => void }) {
  return (
    <>
      <Button variant="outline" onClick={onClose} disabled={busy}>
        {KEEP_LABEL}
      </Button>
      <Button type="submit" form={form} disabled={busy}>
        {label}
      </Button>
    </>
  );
}

export function RelayDrawer({
  page,
  onClose,
  onDone,
}: {
  readonly page: NotificationsBody;
  readonly onClose: () => void;
  readonly onDone: (told: string) => void;
}) {
  const email = page.email;
  const [host, setHost] = useState(email.host ?? "");
  const [port, setPort] = useState(email.port === null ? "587" : String(email.port));
  const [security, setSecurity] = useState<string>(email.security ?? "starttls");
  // A relay nobody has saved starts from the install's branded sender.
  const [sender, setSender] = useState(email.sender ?? email.branded_sender);
  const [username, setUsername] = useState(email.username ?? "");
  const [blank, setBlank] = useState<FieldProblem[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const problems: readonly FieldProblem[] = [...blank, ...(failure?.problems ?? [])];
  const number = portNumber(port);

  const ask = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFailure(null);
    const found = blankRelayProblems(host, port, sender);
    setBlank(found);
    setAsking(found.length === 0 && number !== null);
  };

  const send = () => {
    if (number === null) {
      return;
    }
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(RELAY_API_PATH, {
        method: "POST",
        body: relayBody(host, number, security, sender, username),
      });
      setBusy(false);
      setAsking(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      onDone(readTold(result.data) || "The relay is saved.");
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
      title={email.configured ? EDIT_RELAY_LABEL : SET_UP_RELAY_LABEL}
      description={RELAY_DESCRIPTION}
      footer={<Footer form={RELAY_FORM} label={SAVE_RELAY_LABEL} busy={busy} onClose={onClose} />}
    >
      <div className="flex min-w-0 flex-col gap-3">
        {failure === null ? null : (
          <FailureNotice failure={failure} title={NOT_DONE} fields={["host", "port", "security", "sender", "username"]} />
        )}
        <form id={RELAY_FORM} aria-label="Save the relay" className="flex flex-col gap-4" noValidate autoComplete="off" onSubmit={ask}>
          <TextField form={RELAY_FORM} name="host" label="Host" format={RELAY_FORMATS.host} value={host} onChange={setHost} problems={problems} busy={busy} />
          <TextField
            form={RELAY_FORM}
            name="port"
            label="Port"
            format={RELAY_FORMATS.port}
            value={port}
            onChange={setPort}
            problems={problems}
            busy={busy}
            inputMode="numeric"
          />
          <div className="flex min-w-0 flex-col gap-2">
            <Label htmlFor={`${RELAY_FORM}-security`}>Security</Label>
            <select
              id={`${RELAY_FORM}-security`}
              name="security"
              className="h-11 rounded-md border border-input bg-panel px-2.5 text-sm text-ink sm:h-9"
              value={security}
              disabled={busy}
              {...problemAttributes(problems, RELAY_FORM, "security")}
              onChange={(event) => {
                setSecurity(event.target.value);
              }}
            >
              {page.securities.map((one) => (
                <option key={one} value={one}>
                  {one === "starttls" ? "STARTTLS" : "TLS"}
                </option>
              ))}
            </select>
            <p className="m-0 text-[12.5px] leading-snug text-dim">{page.plain_smtp_refused}</p>
            <FieldProblems problems={problems} form={RELAY_FORM} names="security" />
          </div>
          <TextField
            form={RELAY_FORM}
            name="sender"
            label="Sender address"
            format={RELAY_FORMATS.sender}
            value={sender}
            onChange={setSender}
            problems={problems}
            busy={busy}
            type="email"
          />
          <TextField
            form={RELAY_FORM}
            name="username"
            label="User name"
            format={RELAY_FORMATS.username}
            value={username}
            onChange={setUsername}
            problems={problems}
            busy={busy}
          />
        </form>
      </div>
      <ConfirmDialog
        open={asking}
        question={`Send mail through ${host}, port ${port}, from ${sender}?`}
        consequence={page.saving_email}
        confirmLabel={SAVE_RELAY_LABEL}
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

export function PasswordDrawer({
  page,
  onClose,
  onDone,
}: {
  readonly page: NotificationsBody;
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
    // Only whether a password was typed is known here; its value stays in the field.
    const found = blankPasswordProblems(typed ? "typed" : "");
    setBlank(found);
    setAsking(found.length === 0);
  };

  const send = () => {
    const body = passwordBody(secret.take());
    setTyped(false);
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(PASSWORD_API_PATH, { method: "POST", body });
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
      title={PASSWORD_LABEL}
      description={PASSWORD_DESCRIPTION}
      footer={<Footer form={PASSWORD_FORM} label={SAVE_PASSWORD_LABEL} busy={busy} onClose={onClose} />}
    >
      <div className="flex min-w-0 flex-col gap-3">
        {failure === null ? null : <FailureNotice failure={failure} title={NOT_DONE} fields={["password"]} />}
        <form id={PASSWORD_FORM} aria-label="Save the relay's password" className="flex flex-col gap-4" noValidate onSubmit={ask}>
          <SecretField
            secret={secret}
            label="Password"
            stored={page.email.password.held === true}
            description={RELAY_FORMATS.password}
            disabled={busy}
            onPresenceChange={setTyped}
          />
          <FieldProblems problems={problems} form={PASSWORD_FORM} names="password" />
        </form>
      </div>
      <ConfirmDialog
        open={asking}
        question="Replace the relay's password?"
        consequence={page.keeping_password}
        confirmLabel={SAVE_PASSWORD_LABEL}
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

export function TrialDrawer({
  page,
  onClose,
  onDone,
}: {
  readonly page: NotificationsBody;
  readonly onClose: () => void;
  readonly onDone: (told: string) => void;
}) {
  const [to, setTo] = useState("");
  const [blank, setBlank] = useState<FieldProblem[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const problems: readonly FieldProblem[] = [...blank, ...(failure?.problems ?? [])];

  const ask = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFailure(null);
    const found = blankTrialProblems(to);
    setBlank(found);
    setAsking(found.length === 0);
  };

  const send = () => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(TRIAL_API_PATH, { method: "POST", body: trialBody(to) });
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
      title={TRIAL_LABEL}
      description={TRIAL_DESCRIPTION}
      footer={<Footer form={TRIAL_FORM} label={TRIAL_LABEL} busy={busy} onClose={onClose} />}
    >
      <div className="flex min-w-0 flex-col gap-3">
        {failure === null ? null : <FailureNotice failure={failure} title={NOT_DONE} fields={["to"]} />}
        <form id={TRIAL_FORM} aria-label="Send a test message" className="flex flex-col gap-4" noValidate onSubmit={ask}>
          <TextField form={TRIAL_FORM} name="to" label="Send it to" format={RELAY_FORMATS.to} value={to} onChange={setTo} problems={problems} busy={busy} type="email" />
        </form>
      </div>
      <ConfirmDialog
        open={asking}
        question={`Send a test message to ${to}?`}
        consequence={page.sending_trial}
        confirmLabel={TRIAL_LABEL}
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

export function RemoveRelayDialog({
  page,
  onClose,
  onDone,
}: {
  readonly page: NotificationsBody;
  readonly onClose: () => void;
  readonly onDone: (told: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const send = () => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(REMOVAL_API_PATH, { method: "POST" });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      onDone("The relay is removed.");
    })();
  };
  return (
    <ConfirmDialog
      open
      question={`Remove the relay ${page.email.host ?? ""}?`}
      consequence={page.removing_email}
      details={failure === null ? undefined : <FailureNotice failure={failure} title={NOT_DONE} />}
      confirmLabel={REMOVE_LABEL}
      cancelLabel={KEEP_LABEL}
      busy={busy}
      onConfirm={send}
      onCancel={onClose}
    />
  );
}

export function NoticeSwitchDialog({
  page,
  row,
  onClose,
  onDone,
}: {
  readonly page: NotificationsBody;
  readonly row: NoticeRow;
  readonly onClose: () => void;
  readonly onDone: (told: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const on = !row.on;
  const send = () => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(noticeApiPath(row.kind), { method: "POST", body: switchBody(on) });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      onDone(`${row.title} is switched ${on ? "on" : "off"}.`);
    })();
  };
  return (
    <ConfirmDialog
      open
      question={`Switch ${on ? "on" : "off"} "${row.title}"?`}
      consequence={on ? page.switching_on : page.switching_off}
      details={failure === null ? undefined : <FailureNotice failure={failure} title={NOT_DONE} />}
      confirmLabel={on ? SWITCH_ON_LABEL : SWITCH_OFF_LABEL}
      cancelLabel={KEEP_LABEL}
      busy={busy}
      onConfirm={send}
      onCancel={onClose}
    />
  );
}
