/**
 * Connecting one source: its settings and its key, confirmed, sent once, and every problem drawn
 * beside the field it names.
 *
 * Written once and used twice, by the Connectors screen and by first run's step after the
 * appointment, so the setup wizard connects a source through exactly the request, the
 * confirmation and the refusals the console does. A second form would be a second place for the
 * key to be kept too long.
 *
 * **The key is typed into a plain text field and cleared before the request leaves.** A password
 * field is refused by `scripts/check-boundaries.mjs`, for the reason written there, so the field
 * is `autoComplete="off"` and `spellCheck={false}` as the Webhooks screen's secret is, and the key
 * leaves this component's state as soon as the request is sent, whatever comes back. See
 * `pages/connectorsQuery.ts`' `A_KEY_IS_SENT_ONCE_AND_KEPT_BY_NOBODY_HERE`.
 *
 * **The confirmation names what is agreed to in the API's words, and never the key.** The
 * settings typed are listed, because they are what the source will be pinned to; the key is said
 * to be supplied and nothing more.
 *
 * **Nothing here decides who may connect.** A form is offered for a source the API said this
 * reader may connect, and the API decides again.
 *
 * Task ids: M42.6.5, M42.5.9
 */

import { useState, type FormEvent } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import {
  blankConnectionProblems,
  blankSettings,
  connectionBody,
  CONNECTORS_API_PATH,
  problemsFor,
  readProblems,
  readTold,
  type Connectable,
  type Problem,
} from "../pages/connectorsQuery";
import { Notice } from "../ui/Notice";
import { ConfirmAction } from "./ConfirmAction";

/** The heading over a refusal that is not a problem with a field. */
export const NOT_CONNECTED = "The source was not connected";

/** The button that changes nothing on the confirmation. */
export const KEEP_UNCONNECTED = "Connect nothing";

/** What the key is shown as on the confirmation. Never the key. */
export const KEY_SUPPLIED = "Supplied, and never shown again";

/** What a blank key is shown as on the confirmation, so the API's refusal is not a surprise. */
export const KEY_NOT_GIVEN = "Not given";

/** The label of the button that opens the confirmation, and of the one that confirms. */
export function connectLabel(source: Connectable): string {
  return `Connect ${source.label}`;
}

interface ConnectSourceProps {
  readonly source: Connectable;
  /** The API's sentence for what connecting agrees to. */
  readonly confirmation: string;
  /** The longest key the API accepts, carried only as the field's own `maxLength`. */
  readonly keyMaxChars: number;
  /** The API's sentence for a key left blank, said before the confirmation opens. */
  readonly keyBlank: string;
  /** Called with the API's sentence once the source is connected. */
  readonly onConnected: (told: string) => void;
}

function FieldProblems({
  problems,
  field,
  id,
}: {
  readonly problems: readonly Problem[];
  readonly field: string;
  readonly id: string;
}) {
  const found = problemsFor(problems, field);
  if (found.length === 0) {
    return null;
  }
  return (
    <ul id={id} className="field-description first-run__problem">
      {found.map((one) => (
        <li key={one}>{one}</li>
      ))}
    </ul>
  );
}

export function ConnectSource({ source, confirmation, keyMaxChars, keyBlank, onConnected }: ConnectSourceProps) {
  const [settings, setSettings] = useState<Record<string, string>>(() => blankSettings(source));
  const [key, setKey] = useState("");
  const [pending, setPending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problems, setProblems] = useState<Problem[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const prefix = `connect-${source.name}`;

  function ask(event: FormEvent<HTMLFormElement>): void {
    // Never a native submission: a GET with the key in the query string.
    event.preventDefault();
    setFailure(null);
    // Blank fields are said beside their fields, in the API's words, before anything is confirmed
    // or sent. See `blankConnectionProblems`.
    const blank = blankConnectionProblems(source, settings, key, keyBlank);
    setProblems(blank);
    if (blank.length > 0) {
      return;
    }
    setPending(true);
  }

  function send(): void {
    const body = connectionBody(source, settings, key);
    setBusy(true);
    // The key leaves this component's state before the request does. See the module note.
    setKey("");
    void (async () => {
      const result = await request<unknown>(CONNECTORS_API_PATH, { method: "POST", body });
      setBusy(false);
      setPending(false);
      if (!result.ok) {
        const found = result.failure.status === 422 ? readProblems(result.body) : null;
        setProblems(found ?? []);
        setFailure(found === null ? result.failure : null);
        return;
      }
      setProblems([]);
      setFailure(null);
      setSettings(blankSettings(source));
      onConnected(readTold(result.data));
    })();
  }

  const described = (field: string) =>
    problemsFor(problems, field).length > 0 ? { "aria-describedby": `${prefix}-${field}-problem` } : {};

  return (
    <div className="form" aria-label={connectLabel(source)} role="group">
      {failure === null ? null : (
        <Notice title={NOT_CONNECTED} traceId={failure.traceId}>
          <p>{failure.message}</p>
        </Notice>
      )}
      <FieldProblems problems={problems} field="connector" id={`${prefix}-connector-problem`} />
      <form className="form" noValidate autoComplete="off" onSubmit={ask}>
        {source.settings.map((one) => (
          <div className="rjsf-field" key={one.name}>
            <label className="control-label" htmlFor={`${prefix}-${one.name}`}>
              {one.label}
            </label>
            <input
              id={`${prefix}-${one.name}`}
              className="form-control"
              type="text"
              value={settings[one.name] ?? ""}
              maxLength={one.max_chars}
              autoComplete="off"
              spellCheck={false}
              aria-invalid={problemsFor(problems, one.name).length > 0}
              {...described(one.name)}
              disabled={busy || pending}
              onChange={(event) => {
                setSettings({ ...settings, [one.name]: event.target.value });
              }}
            />
            <p className="field-description">{one.hint}</p>
            <FieldProblems problems={problems} field={one.name} id={`${prefix}-${one.name}-problem`} />
          </div>
        ))}
        <div className="rjsf-field">
          <label className="control-label" htmlFor={`${prefix}-credential`}>
            {source.credential_label}
          </label>
          <input
            id={`${prefix}-credential`}
            className="form-control"
            type="text"
            value={key}
            maxLength={keyMaxChars}
            autoComplete="off"
            spellCheck={false}
            aria-invalid={problemsFor(problems, "credential").length > 0}
            {...described("credential")}
            disabled={busy || pending}
            onChange={(event) => {
              setKey(event.target.value);
            }}
          />
          <p className="field-description">{source.credential_hint}</p>
          <FieldProblems problems={problems} field="credential" id={`${prefix}-credential-problem`} />
        </div>
        {pending ? null : (
          <div className="form-actions">
            <button type="submit" className="button" disabled={busy}>
              {connectLabel(source)}
            </button>
          </div>
        )}
      </form>
      {!pending ? null : (
        <ConfirmAction
          question={`${connectLabel(source)}?`}
          consequence={confirmation}
          details={
            <dl className="fields" aria-label={`What ${source.label} will be connected with`}>
              {source.settings.map((one) => (
                <div className="fields__row" key={one.name}>
                  <dt>{one.label}</dt>
                  <dd>
                    <code>{settings[one.name] ?? ""}</code>
                  </dd>
                </div>
              ))}
              <div className="fields__row">
                <dt>{source.credential_label}</dt>
                <dd>{key.trim() === "" ? KEY_NOT_GIVEN : KEY_SUPPLIED}</dd>
              </div>
            </dl>
          }
          confirmLabel={connectLabel(source)}
          cancelLabel={KEEP_UNCONNECTED}
          busy={busy}
          onConfirm={send}
          onCancel={() => {
            setPending(false);
          }}
        />
      )}
    </div>
  );
}
