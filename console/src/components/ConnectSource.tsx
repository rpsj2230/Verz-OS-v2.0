/**
 * Connecting one source: its settings and its key, confirmed, sent once, and every problem drawn
 * beside the field it names.
 *
 * Written once and used twice, by the Connectors screen and by first run's step after the
 * appointment, so the setup wizard connects a source through exactly the request, the
 * confirmation and the refusals the console does. A second form would be a second place for the
 * key to be kept too long.
 *
 * **The credential is asked for in its source's shape** (`CredentialField`, M11.7.7): a key typed,
 * a key file chosen or a database user's name and password, sent as the one `credential` field.
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
 * **The settings, and never the key, can start from what was typed before.** The Connectors
 * screen's connect flow keeps a source's settings while its dialog is closed (`kit/flowMemory.ts`),
 * so it hands them back here and hears each change; first run passes neither and starts blank.
 *
 * **A source consented to by OAuth has one more step after it is connected (M11.8.6).** Its form
 * takes the application's client id as a setting and its client secret as the key, and once the
 * connection is made the form gives way to "Connect with" the vendor: the API holds a consent and
 * answers the vendor's own page, and this tab goes there. The person signs in at the vendor, never
 * here, and the vendor sends them back to `pages/ConnectorConsent.tsx`. See
 * `pages/connectors/consentAtVendor.ts`.
 *
 * Task ids: M42.6.5, M42.5.9, M27.8.5, M27.11.9, M11.7.7, M11.8.6
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
import { consentPath, connectWithLabel, returnAddress, type ConsentStarted } from "../pages/connectors/consentAtVendor";
import { ConfirmAction } from "./ConfirmAction";
import { Button } from "./ui/button";
import { CredentialField, credentialFor, credentialGiven } from "./CredentialField";
import { useSecret } from "./ui/secret-field";

/** The heading over a refusal that is not a problem with a field. */
export const NOT_CONNECTED = "The source was not connected";

/** The heading over a consent the API would not start. */
export const NOT_SENT_TO_THE_VENDOR = "The vendor was not asked";

/** The button that leaves the consent for later, which the source's page offers again. */
export const CONSENT_LATER = "Later";

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
  /** The settings to start from, typed earlier in the same flow. Never a key. */
  readonly startSettings?: Readonly<Record<string, string>> | undefined;
  /** Told the settings after every change, so a flow can keep them while its dialog is closed. */
  readonly onSettingsChange?: ((settings: Readonly<Record<string, string>>) => void) | undefined;
}

/** Every name a setting's input answers to: its own, and its place in the body. */
function settingNames(name: string): readonly string[] {
  return [name, `settings.${name}`];
}

export function ConnectSource({
  source,
  confirmation,
  keyMaxChars,
  keyBlank,
  onConnected,
  startSettings,
  onSettingsChange,
}: ConnectSourceProps) {
  const [settings, setSettings] = useState<Record<string, string>>(() => ({ ...blankSettings(source), ...startSettings }));
  const [key, setKey] = useState("");
  // A database user's password is typed into the kit's secret field and never held here.
  const password = useSecret();
  const [passwordPresent, setPasswordPresent] = useState(false);
  const [pending, setPending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [blank, setBlank] = useState<Problem[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  // Set once a source consented to by OAuth is connected: the API's sentence, kept for "Later".
  const [consenting, setConsenting] = useState<string | null>(null);
  const [consentFailure, setConsentFailure] = useState<ApiFailure | null>(null);
  const problems: readonly Problem[] = [...blank, ...(failure?.problems ?? [])];

  const prefix = `connect-${source.name}`;
  const fields = ["connector", "credential", ...source.settings.flatMap((one) => settingNames(one.name))];

  function ask(event: FormEvent<HTMLFormElement>): void {
    // Never a native submission: a GET with the key in the query string.
    event.preventDefault();
    setFailure(null);
    // Blank fields are said beside their fields, in the API's words, before anything is confirmed
    // or sent. See `blankConnectionProblems`.
    const given = credentialGiven(source.credential_shape, key, passwordPresent) ? "given" : "";
    const found = blankConnectionProblems(source, settings, given, keyBlank);
    setBlank(found);
    if (found.length > 0) {
      return;
    }
    setPending(true);
  }

  function send(): void {
    const body = connectionBody(source, settings, credentialFor(source.credential_shape, key, password));
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
      if (source.consent_with) {
        setConsenting(readTold(result.data));
        return;
      }
      onConnected(readTold(result.data));
    })();
  }

  function consent(): void {
    setBusy(true);
    setConsentFailure(null);
    void (async () => {
      const body = { return_address: returnAddress(window.location.origin) };
      const result = await request<ConsentStarted>(consentPath(source.name), { method: "POST", body });
      if (!result.ok) {
        setBusy(false);
        setConsentFailure(result.failure);
        return;
      }
      // To the vendor's own page, in this tab. See `pages/connectors/consentAtVendor.ts`.
      window.location.assign(result.data.address);
    })();
  }

  if (consenting !== null && source.consent_with) {
    return (
      <div className="form" aria-label={connectWithLabel(source.consent_with)} role="group">
        {consentFailure === null ? null : (
          <FailureNotice failure={consentFailure} title={NOT_SENT_TO_THE_VENDOR} />
        )}
        <p>{consenting}</p>
        <p className="field-description">{source.consent_told}</p>
        <div className="form-actions">
          <Button type="button" disabled={busy} onClick={consent}>
            {connectWithLabel(source.consent_with)}
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={busy}
            onClick={() => {
              onConnected(consenting);
            }}
          >
            {CONSENT_LATER}
          </Button>
        </div>
      </div>
    );
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
                const next = { ...settings, [one.name]: event.target.value };
                setSettings(next);
                onSettingsChange?.(next);
              }}
            />
            <p className="field-description">{one.hint}</p>
            <FieldProblems problems={problems} form={prefix} names={settingNames(one.name)} />
          </div>
        ))}
        <div className="rjsf-field">
          <label
            className="control-label"
            htmlFor={source.credential_shape === "database_user" ? `${prefix}-credential-user` : `${prefix}-credential`}
          >
            {source.credential_label}
          </label>
          <CredentialField
            shape={source.credential_shape}
            id={`${prefix}-credential`}
            maxChars={Math.max(keyMaxChars, source.credential_max_chars)}
            value={key}
            onChange={setKey}
            secret={password}
            onPasswordPresence={setPasswordPresent}
            disabled={busy || pending}
            problemProps={problemAttributes(problems, prefix, "credential")}
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
                <dd>{credentialGiven(source.credential_shape, key, passwordPresent) ? KEY_SUPPLIED : KEY_NOT_GIVEN}</dd>
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
