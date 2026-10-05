/**
 * A source's credential, asked for in the shape the source issues it (M11.7.7).
 *
 * The API says which shape each source takes (`ConnectableView.credential_shape`): one pasted key,
 * a key file chosen as a file, or a database user typed as a name and a password. Until
 * 2026-09-30 every source took a pasted key, so the two that did not could only be connected at the
 * server. See `brain.connectors.declaration.A_CREDENTIAL_IS_ASKED_FOR_IN_THE_SHAPE_THE_SOURCE_ISSUES_IT`.
 *
 * **Whatever the shape, the request sends one string**, its one `credential` field: the key, the
 * file's text, or the user and password as one JSON object, which `credentialFor` builds at the
 * moment the request is built. The API judges it in its shape and keeps it in the vault whole, so
 * nothing here decides what makes a credential good.
 *
 * **A password is the kit's secret field and is never held by React.** It is typed into
 * `ui/secret-field.tsx`, masked, and taken out of the field by `credentialFor` in the same call that
 * empties it, as the key drawer takes a key (`tests/secret-inputs.test.ts`). The user's name and a
 * key are plain text, with autocomplete and spell checking off. **A key file is read and never
 * drawn**: the field says a file is chosen, and the file's name is the browser's own.
 *
 * Task ids: M11.7.7
 */

import { useEffect, useRef } from "react";
import { SecretField, type SecretHandle } from "./ui/secret-field";

/** What the key file field says once a file is chosen. Never the file. */
export const FILE_CHOSEN = "A file is chosen. It is sent once and never shown.";

/** The two halves of a database user, as the form labels them. */
export const USER_LABEL = "User name";
export const PASSWORD_LABEL = "Password";

/**
 * The credential the request sends, built at the moment it is built. A password is taken out of
 * its field here, which empties the field. Empty when nothing was given.
 */
export function credentialFor(shape: string, typed: string, secret: SecretHandle): string {
  if (shape !== "database_user") {
    return typed;
  }
  const password = secret.take();
  return typed === "" && password === "" ? "" : JSON.stringify({ user: typed, password });
}

/** Whether anything was given, for the blank check before the confirmation opens. */
export function credentialGiven(shape: string, typed: string, passwordPresent: boolean): boolean {
  return typed.trim() !== "" || (shape === "database_user" && passwordPresent);
}

interface CredentialFieldProps {
  readonly shape: string;
  /** The id of the field the form's label points at: the key, the file, or the user's name. */
  readonly id: string;
  readonly maxChars: number;
  /** The key, the file's text or the user's name, as typed. Empty is nothing given. */
  readonly value: string;
  readonly onChange: (value: string) => void;
  /** The handle a database user's password is typed into and taken from. */
  readonly secret: SecretHandle;
  readonly onPasswordPresence: (present: boolean) => void;
  readonly disabled: boolean;
  /** The `aria-*` attributes the form's problems give this field (`ui/FieldProblems`). */
  readonly problemProps: { readonly "aria-invalid"?: true; readonly "aria-describedby"?: string };
}

export function CredentialField({
  shape,
  id,
  maxChars,
  value,
  onChange,
  secret,
  onPasswordPresence,
  disabled,
  problemProps,
}: CredentialFieldProps) {
  const file = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    // The owner cleared the credential, which it does as the request leaves: let the file go too.
    if (value === "" && file.current !== null) {
      file.current.value = "";
    }
  }, [value]);

  if (shape === "key_file") {
    return (
      <>
        <input
          ref={file}
          id={id}
          className="form-control"
          type="file"
          name="credential"
          accept="application/json,.json"
          disabled={disabled}
          {...problemProps}
          onChange={(event) => {
            const chosen = event.target.files?.[0];
            if (chosen === undefined) {
              onChange("");
              return;
            }
            void chosen.text().then((text) => {
              onChange(text);
            });
          }}
        />
        {value === "" ? null : <p className="field-description">{FILE_CHOSEN}</p>}
      </>
    );
  }
  if (shape === "database_user") {
    return (
      <div className="fields">
        <label className="control-label" htmlFor={`${id}-user`}>
          {USER_LABEL}
        </label>
        <input
          id={`${id}-user`}
          className="form-control"
          type="text"
          name="credential.user"
          value={value}
          maxLength={maxChars}
          autoComplete="off"
          spellCheck={false}
          disabled={disabled}
          {...problemProps}
          onChange={(event) => {
            onChange(event.target.value);
          }}
        />
        <SecretField
          id={`${id}-password`}
          secret={secret}
          label={PASSWORD_LABEL}
          stored={false}
          disabled={disabled}
          invalid={problemProps["aria-invalid"] === true}
          onPresenceChange={onPasswordPresence}
          {...(problemProps["aria-describedby"] === undefined ? {} : { describedBy: problemProps["aria-describedby"] })}
        />
      </div>
    );
  }
  return (
    <input
      id={id}
      className="form-control"
      type="text"
      name="credential"
      value={value}
      maxLength={maxChars}
      autoComplete="off"
      spellCheck={false}
      disabled={disabled}
      {...problemProps}
      onChange={(event) => {
        onChange(event.target.value);
      }}
    />
  );
}
