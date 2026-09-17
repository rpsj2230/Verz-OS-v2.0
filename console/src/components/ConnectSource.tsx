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
 * **A refusal is drawn whole.** The notice carries the API's message and reference, each problem
 * is drawn beside the input it names, and a problem naming none of them is listed under the
 * notice. A setting answers to its own name, which is what the connectors routes' own documents
 * use, and to its place in the body, `settings.` and the name, which is what a validation refusal
 * of the body uses.
 *
 * Task ids: M42.6.5, M42.5.9, M27.8.5
 */

import { useState, type FormEvent } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import {
  blankConnectionProblems,
  blankSettings,
  connectionBody,
  CONNECTORS_API_PATH,
  readTold,
  type Connectable,
  type Problem,
} from "../pages/connectorsQuery";
import { FailureNotice } from "../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../ui/FieldProblems";
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

/** Every name a setting's input answers to: its own, and its place in the body. */
function settingNames(name: string): readonly string[] {
  return [name, `settings.${name}`];
}

export function ConnectSource({ source, confirmation, keyMaxChars, keyBlank, onConnected }: ConnectSourceProps) {
  const [settings, setSettings] = useState<Record<string, string>>(() => blankSettings(source));
  const [key, setKey] = useState("");
  const [pending, setPending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [blank, setBlank] = useState<Problem[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const problems: readonly Problem[] = [...blank, ...(failure?.problems ?? [])];

  const prefix = `connect-${source.name}`;
  const fields = ["connector", "credential", ...source.settings.flatMap((one) => settingNames(one.name))];

  function ask(event: FormEvent<HTMLFormElement>): void {
    // Never a native submission: a GET with the key in the query string.
    event.preventDefault();
    setFailure(null);
    // Blank fields are said beside their fields, in the API's words, before anything is confirmed
    // or sent. See `blankConnectionProblems`.
    const found = blankConnectionProblems(source, settings, key, keyBlank);
    setBlank(found);
    if (found.length > 0) {
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
        setBlank([]);
        setFailure(result.failure);
        return;
      }
      setBlank([]);
      setFailure(null);
      setSettings(blankSettings(source));
      onConnected(readTold(result.data));
    })();
  }

  return (
    <div className="form" aria-label={connectLabel(source)} role="group">
      {failure === null ? null : <FailureNotice failure={failure} title={NOT_CONNECTED} fields={fields} />}
      <FieldProblems problems={problems} form={prefix} names="connector" />
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
              name={`settings.${one.name}`}
              value={settings[one.name] ?? ""}
              maxLength={one.max_chars}
              autoComplete="off"
              spellCheck={false}
              {...problemAttributes(problems, prefix, settingNames(one.name))}
              disabled={busy || pending}
              onChange={(event) => {
                setSettings({ ...settings, [one.name]: event.target.value });
              }}
            />
            <p className="field-description">{one.hint}</p>
            <FieldProblems problems={problems} form={prefix} names={settingNames(one.name)} />
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
            name="credential"
            value={key}
            maxLength={keyMaxChars}
            autoComplete="off"
            spellCheck={false}
            {...problemAttributes(problems, prefix, "credential")}
            disabled={busy || pending}
            onChange={(event) => {
              setKey(event.target.value);
            }}
          />
          <p className="field-description">{source.credential_hint}</p>
          <FieldProblems problems={problems} form={prefix} names="credential" />
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
