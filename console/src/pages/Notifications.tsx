/**
 * Notifications and email: who this product tells what, whether anything sends it yet, the switch
 * that stops a notice, and the email relay with its password and a test message.
 *
 * `docs/screens.html` does not draw this screen, so it takes the design's general shape (a crumb, a
 * heading, a lede, cards holding a table or a form, a note under each saying what not to assume)
 * and every fact on it is a field the API sent: who is told, what about, how, whether it is sent,
 * why a notice has no switch, and what each write will do.
 *
 * **Every write is confirmed in the API's words.** Switching a notice, saving the relay, keeping its
 * password and sending a test message each open `ConfirmAction` with the sentence the route served.
 * A success says what changed; a refusal is the API's problems beside their fields, or its message.
 *
 * **The password is typed into a plain text field and forgotten the moment it is sent.** A password
 * field is refused by `scripts/check-boundaries.mjs`, so the field is `autoComplete="off"` and
 * `spellCheck={false}`, and the value leaves the page's state as soon as the request does.
 *
 * Task ids: M27.8.11, M27.8.5
 */

import { useCallback, useState, type FormEvent } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { ConfirmAction } from "../components/ConfirmAction";
import { FailureNotice } from "../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../ui/FieldProblems";
import { Notice } from "../ui/Notice";
import { SOMETHING_DID_NOT_WORK } from "./Overview";
import {
  PASSWORD_API_PATH,
  NOTIFICATIONS_API_PATH,
  RELAY_API_PATH,
  TRIAL_API_PATH,
  blankPasswordProblems,
  blankRelayProblems,
  blankTrialProblems,
  noticeApiPath,
  passwordBody,
  passwordSentence,
  portNumber,
  readNotifications,
  relayBody,
  sentSentence,
  switchBody,
  trialBody,
  when,
  type NoticeRow,
  type NotificationsBody,
} from "./notificationsQuery";
import type { Problem } from "./webhooksQuery";

export const NOTIFICATIONS_HEADING = "Notifications and email";
export const NOTIFICATIONS_CRUMB = "Operate › Notifications and email";
export const NOTIFICATIONS_LEDE =
  "Who this install tells what, how, and whether anything sends it yet; the switch that stops a " +
  "notice; and the email relay mail is sent through.";

export const READING_NOTIFICATIONS = "Reading who is told what.";
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";
export const NO_SWITCH = "No switch";
export const RELAY_NOT_SAVED = "No relay is saved.";
export const NO_NOTICES = "No notice is listed.";

export const SWITCH_OFF_LABEL = "Switch off";
export const SWITCH_ON_LABEL = "Switch on";
export const SAVE_RELAY_LABEL = "Save relay";
export const KEEP_PASSWORD_LABEL = "Save password";
export const SEND_TRIAL_LABEL = "Send test message";
export const KEEP_LABEL = "Change nothing";

/**
 * The names this screen's inputs are sent under. Every one is unique across its three forms, so one
 * list of problems serves all of them; a switch sends `on`, which no input holds, and a problem with
 * it is listed under the notice.
 */
const NOTIFICATION_FIELDS: readonly string[] = ["host", "port", "security", "sender", "username", "password", "to"];
const NOTIFICATIONS_FORM = "notifications";

type Pending =
  | { readonly kind: "switch"; readonly row: NoticeRow; readonly on: boolean }
  | {
      readonly kind: "relay";
      readonly host: string;
      readonly port: number;
      readonly security: string;
      readonly sender: string;
      readonly username: string;
    }
  | { readonly kind: "password"; readonly password: string }
  | { readonly kind: "trial"; readonly to: string };

function readTold(payload: unknown): string {
  if (typeof payload !== "object" || payload === null) {
    return "";
  }
  const told = (payload as { told?: unknown }).told;
  return typeof told === "string" ? told : "";
}

function NoticeTable({
  page,
  busy,
  onSwitch,
}: {
  readonly page: NotificationsBody;
  readonly busy: boolean;
  readonly onSwitch: (row: NoticeRow, on: boolean) => void;
}) {
  return (
    <section className="card">
      <h2>Who is told what</h2>
      {page.notices.length === 0 ? <p className="note">{NO_NOTICES}</p> : null}
      <div className="grid__scroll">
        <table className="grid__table" aria-label="Notices">
          <thead>
            <tr>
              <th scope="col">Notice</th>
              <th scope="col">Who is told</th>
              <th scope="col">About</th>
              <th scope="col">How</th>
              <th scope="col">Today</th>
              <th scope="col">Switch</th>
            </tr>
          </thead>
          <tbody>
            {page.notices.map((row) => (
              <tr key={row.kind}>
                <td>{row.title}</td>
                <td>{row.told}</td>
                <td>{row.about}</td>
                <td>{row.how}</td>
                <td>{sentSentence(row)}</td>
                <td>
                  {row.switchable ? (
                    <>
                      {row.on ? "On" : "Off"}
                      {row.changed_by === null ? null : (
                        <>
                          {", by "}
                          <code>{row.changed_by}</code> {when(row.changed_at)}
                        </>
                      )}{" "}
                      <button
                        type="button"
                        className="button"
                        disabled={busy}
                        aria-label={`${row.on ? SWITCH_OFF_LABEL : SWITCH_ON_LABEL}: ${row.title}`}
                        onClick={() => {
                          onSwitch(row, !row.on);
                        }}
                      >
                        {row.on ? SWITCH_OFF_LABEL : SWITCH_ON_LABEL}
                      </button>
                    </>
                  ) : (
                    <>
                      {NO_SWITCH}: {row.fixed_because}
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="note">{page.ships_on}</p>
      <p className="note">{page.only_the_last_change_is_kept}</p>
      <p className="note">{page.subscribers}</p>
    </section>
  );
}

function NotificationsPageBody({
  page,
  onChanged,
}: {
  readonly page: NotificationsBody;
  readonly onChanged: (sentence: string) => void;
}) {
  const email = page.email;
  const [host, setHost] = useState(email.host ?? "");
  const [port, setPort] = useState(email.port === null ? "587" : String(email.port));
  const [security, setSecurity] = useState<string>(email.security ?? "starttls");
  const [sender, setSender] = useState(email.sender ?? "");
  const [username, setUsername] = useState(email.username ?? "");
  const [password, setPassword] = useState("");
  const [to, setTo] = useState("");
  const [pending, setPending] = useState<Pending | null>(null);
  const [blank, setBlank] = useState<Problem[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const problems: readonly Problem[] = [...blank, ...(failure?.problems ?? [])];
  const [busy, setBusy] = useState(false);

  const send = useCallback(
    (asked: Pending) => {
      setBusy(true);
      // The password leaves the page's state before the request does. See the module note.
      setPassword("");
      void (async () => {
        const result =
          asked.kind === "switch"
            ? await request<unknown>(noticeApiPath(asked.row.kind), { method: "POST", body: switchBody(asked.on) })
            : asked.kind === "relay"
              ? await request<unknown>(RELAY_API_PATH, {
                  method: "POST",
                  body: relayBody(asked.host, asked.port, asked.security, asked.sender, asked.username),
                })
              : asked.kind === "password"
                ? await request<unknown>(PASSWORD_API_PATH, { method: "POST", body: passwordBody(asked.password) })
                : await request<unknown>(TRIAL_API_PATH, { method: "POST", body: trialBody(asked.to) });
        setBusy(false);
        setPending(null);
        if (!result.ok) {
          // Drawn whole: the notice with the API's message and reference, and each problem beside
          // the input it names.
          setBlank([]);
          setFailure(result.failure);
          return;
        }
        setBlank([]);
        setFailure(null);
        const told = readTold(result.data);
        onChanged(
          told !== ""
            ? told
            : asked.kind === "switch"
              ? `${asked.row.title} is switched ${asked.on ? "on" : "off"}.`
              : "The relay is saved.",
        );
      })();
    },
    [onChanged],
  );

  function saveRelay(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFailure(null);
    const found = blankRelayProblems(host, port, sender);
    setBlank(found);
    const number = portNumber(port);
    if (found.length > 0 || number === null) {
      return;
    }
    setPending({ kind: "relay", host, port: number, security, sender, username });
  }

  function keepPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFailure(null);
    const found = blankPasswordProblems(password);
    setBlank(found);
    if (found.length > 0) {
      return;
    }
    setPending({ kind: "password", password });
  }

  function sendTrial(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFailure(null);
    const found = blankTrialProblems(to);
    setBlank(found);
    if (found.length > 0) {
      return;
    }
    setPending({ kind: "trial", to });
  }

  const cancel = () => {
    setPending(null);
  };
  const confirmation =
    pending === null ? null : pending.kind === "switch" ? (
      <ConfirmAction
        question={`Switch ${pending.on ? "on" : "off"} "${pending.row.title}"?`}
        consequence={pending.on ? page.switching_on : page.switching_off}
        confirmLabel={pending.on ? SWITCH_ON_LABEL : SWITCH_OFF_LABEL}
        cancelLabel={KEEP_LABEL}
        busy={busy}
        onConfirm={() => {
          send(pending);
        }}
        onCancel={cancel}
      />
    ) : pending.kind === "relay" ? (
      <ConfirmAction
        question={`Send mail through ${pending.host}, port ${String(pending.port)}, from ${pending.sender}?`}
        consequence={page.saving_email}
        confirmLabel={SAVE_RELAY_LABEL}
        cancelLabel={KEEP_LABEL}
        busy={busy}
        onConfirm={() => {
          send(pending);
        }}
        onCancel={cancel}
      />
    ) : pending.kind === "password" ? (
      <ConfirmAction
        question="Replace the relay's password?"
        consequence={page.keeping_password}
        confirmLabel={KEEP_PASSWORD_LABEL}
        cancelLabel={KEEP_LABEL}
        busy={busy}
        onConfirm={() => {
          send(pending);
        }}
        onCancel={cancel}
      />
    ) : (
      <ConfirmAction
        question={`Send a test message to ${pending.to}?`}
        consequence={page.sending_trial}
        confirmLabel={SEND_TRIAL_LABEL}
        cancelLabel={KEEP_LABEL}
        busy={busy}
        onConfirm={() => {
          send(pending);
        }}
        onCancel={cancel}
      />
    );

  return (
    <>
      {failure === null ? null : <FailureNotice failure={failure} fields={NOTIFICATION_FIELDS} />}
      {confirmation}

      <NoticeTable
        page={page}
        busy={busy}
        onSwitch={(row, on) => {
          setPending({ kind: "switch", row, on });
        }}
      />

      <section className="card">
        <h2>Email relay</h2>
        <p className="note">{page.email_used_for}</p>
        {email.configured ? (
          <dl className="fields" aria-label="The saved relay">
            <dt>Relay</dt>
            <dd>
              <code>{email.host}</code>, port {email.port}, {email.security}
            </dd>
            <dt>Sender</dt>
            <dd>
              <code>{email.sender}</code>
            </dd>
            <dt>Saved by</dt>
            <dd>
              <code>{email.changed_by}</code> {when(email.changed_at)}
            </dd>
          </dl>
        ) : (
          <p className="note">{RELAY_NOT_SAVED}</p>
        )}
        <form className="form" aria-label="Save the relay" onSubmit={saveRelay}>
          <label className="control-label">
            Host{" "}
            <input
              className="form-control"
              type="text"
              name="host"
              value={host}
              {...problemAttributes(problems, NOTIFICATIONS_FORM, "host")}
              onChange={(event) => {
                setHost(event.target.value);
              }}
            />
          </label>
          <FieldProblems problems={problems} form={NOTIFICATIONS_FORM} names="host" />
          <label className="control-label">
            Port{" "}
            <input
              className="form-control"
              type="text"
              inputMode="numeric"
              name="port"
              value={port}
              {...problemAttributes(problems, NOTIFICATIONS_FORM, "port")}
              onChange={(event) => {
                setPort(event.target.value);
              }}
            />
          </label>
          <FieldProblems problems={problems} form={NOTIFICATIONS_FORM} names="port" />
          <label className="control-label">
            Security{" "}
            <select
              className="form-control"
              name="security"
              value={security}
              {...problemAttributes(problems, NOTIFICATIONS_FORM, "security")}
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
          </label>
          <FieldProblems problems={problems} form={NOTIFICATIONS_FORM} names="security" />
          <p className="field-description">{page.plain_smtp_refused}</p>
          <label className="control-label">
            Sender address{" "}
            <input
              className="form-control"
              type="email"
              name="sender"
              value={sender}
              {...problemAttributes(problems, NOTIFICATIONS_FORM, "sender")}
              onChange={(event) => {
                setSender(event.target.value);
              }}
            />
          </label>
          <FieldProblems problems={problems} form={NOTIFICATIONS_FORM} names="sender" />
          <label className="control-label">
            User name{" "}
            <input
              className="form-control"
              type="text"
              autoComplete="off"
              name="username"
              value={username}
              {...problemAttributes(problems, NOTIFICATIONS_FORM, "username")}
              onChange={(event) => {
                setUsername(event.target.value);
              }}
            />
          </label>
          <FieldProblems problems={problems} form={NOTIFICATIONS_FORM} names="username" />
          <div className="form-actions">
            <button type="submit" className="button" disabled={busy}>
              {SAVE_RELAY_LABEL}
            </button>
          </div>
        </form>
      </section>

      <section className="card">
        <h2>Relay password</h2>
        <p>{passwordSentence(email)}</p>
        {email.password.vault === "ready" ? null : <p className="note">{email.password.vault_told}</p>}
        <form className="form" aria-label="Save the relay's password" onSubmit={keepPassword}>
          <label className="control-label">
            Password{" "}
            <input
              className="form-control"
              type="text"
              autoComplete="off"
              spellCheck={false}
              name="password"
              value={password}
              {...problemAttributes(problems, NOTIFICATIONS_FORM, "password")}
              onChange={(event) => {
                setPassword(event.target.value);
              }}
            />
          </label>
          <FieldProblems problems={problems} form={NOTIFICATIONS_FORM} names="password" />
          <p className="field-description">It is kept in the vault and never shown again.</p>
          <div className="form-actions">
            <button type="submit" className="button" disabled={busy}>
              {KEEP_PASSWORD_LABEL}
            </button>
          </div>
        </form>
      </section>

      <section className="card">
        <h2>Send a test message</h2>
        <form className="form" aria-label="Send a test message" onSubmit={sendTrial}>
          <label className="control-label">
            Send it to{" "}
            <input
              className="form-control"
              type="email"
              name="to"
              value={to}
              {...problemAttributes(problems, NOTIFICATIONS_FORM, "to")}
              onChange={(event) => {
                setTo(event.target.value);
              }}
            />
          </label>
          <FieldProblems problems={problems} form={NOTIFICATIONS_FORM} names="to" />
          <div className="form-actions">
            <button type="submit" className="button" disabled={busy}>
              {SEND_TRIAL_LABEL}
            </button>
          </div>
        </form>
      </section>
    </>
  );
}

function NotificationsList({ onChanged }: { readonly onChanged: (sentence: string) => void }) {
  const answer = useResource<unknown>(NOTIFICATIONS_API_PATH);
  if (answer.failure) {
    return <FailureNotice failure={answer.failure} />;
  }
  if (answer.busy) {
    return (
      <p className="note" role="status">
        {READING_NOTIFICATIONS}
      </p>
    );
  }
  const page = readNotifications(answer.data);
  if (page === null) {
    return (
      <Notice title={SOMETHING_DID_NOT_WORK}>
        <p>The answer about notifications was not in a shape this screen can read.</p>
      </Notice>
    );
  }
  return <NotificationsPageBody page={page} onChanged={onChanged} />;
}

export function Notifications() {
  // A counter rather than a boolean, so two changes in a row read the page twice. Never rendered.
  const [generation, setGeneration] = useState(0);
  const [changed, setChanged] = useState<string | null>(null);
  const onChanged = useCallback((sentence: string) => {
    setChanged(sentence);
    setGeneration((current) => current + 1);
  }, []);

  return (
    <article className="page">
      <p className="note">{NOTIFICATIONS_CRUMB}</p>
      <h1>{NOTIFICATIONS_HEADING}</h1>
      <p className="lede">{NOTIFICATIONS_LEDE}</p>
      {changed === null ? null : (
        <p className="note" role="status">
          {changed}
        </p>
      )}
      <NotificationsList key={generation} onChanged={onChanged} />
    </article>
  );
}
