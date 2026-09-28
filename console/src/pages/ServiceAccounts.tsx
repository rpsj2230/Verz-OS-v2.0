/**
 * Service accounts: an integration registered, given a key shown once, its key revoked, and the
 * account retired.
 *
 * In Govern beside Sign-in links, because it is the other way something signs in: a person through
 * the identity provider, an integration with a key. `docs/screens.html` does not draw it, so the
 * layout is the design's general one: the crumb, a card with the list, a card with each form, and the
 * API's own sentences under the list. The decision about who may open it and whose account is whose
 * is `brain.service_account_routes`, on the server; a person without `admin:credential` is told the
 * screen is not found, which is what every control in this console says.
 *
 * **The key is shown once, whole, with a copy button, and never again.** It is drawn from the issue's
 * answer and from nothing else, kept in this page's state only until the person presses that they
 * have kept it, and the listing beneath carries its handle alone. See
 * `serviceAccountsQuery.A_KEY_IS_SHOWN_ONCE_AND_NEVER_READ_BACK`.
 *
 * **Revoking a key and retiring an account are confirmed**, and each confirmation says what stops
 * working. Registering and issuing end nothing that exists, so they are not.
 *
 * **Rotation is two controls in order, not a third.** Issue a new key, move the integration to it,
 * revoke the old one. A single "rotate" press would either revoke a key somebody is still using or
 * leave two live keys the person believes are one, so the page says the order in words instead.
 *
 * Rejected: an owner field on the registration form. The route takes the owner from the caller and a
 * field would be a control that lends somebody else's reach. See
 * `serviceAccountsQuery.AN_ACCOUNT_IS_ALWAYS_THE_CALLERS_OWN`.
 *
 * Task ids: M27.11.5, M27.15.26
 */

import { useCallback, useState, type FormEvent } from "react";
import { request } from "../api/client";
import type { ApiFailure, FieldProblem } from "../api/errors";
import { ConfirmAction } from "../components/ConfirmAction";
import { ListControls, NOTHING_MATCHES, ShowMore } from "../components/ListControls";
import { narrows } from "../components/listing";
import { useListing } from "../components/useListing";
import { FailureNotice } from "../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../ui/FieldProblems";
import {
  ACCOUNT_FILTERS,
  ACCOUNT_SORTS,
  CEILING_RULE,
  ID_SHAPE,
  ISSUE_KEY_API_PATH,
  RETIRE_ACCOUNT_API_PATH,
  REVOKE_KEY_API_PATH,
  ROTATION,
  SERVICE_ACCOUNTS_API_PATH,
  accountName,
  blankKeyProblems,
  blankRegistrationProblems,
  keyBody,
  keysOf,
  readAccounts,
  readIssuedKey,
  registrationBody,
  retirementBody,
  revocationBody,
  toldBy,
  when,
  type AccountRow,
  type IssuedKeyBody,
  type KeyRow,
} from "./serviceAccountsQuery";

export const ACCOUNTS_HEADING = "Service accounts";
export const ACCOUNTS_CRUMB = "Govern › Service accounts";
export const ACCOUNTS_LEDE =
  "Integrations that call the Brain with a key rather than a person signing in. Register one, " +
  "issue it a key, revoke a key, or retire the account.";

/** The four states. */
export const READING_ACCOUNTS = "Reading your service accounts.";
export const NO_ACCOUNTS = "You have no service accounts. Register one below.";
export const NO_KEYS = "None of your accounts has a live key.";
export const MORE_ACCOUNTS = "This list came back full, so you have more accounts than it shows.";
export const NONE_MATCH = NOTHING_MATCHES;
export const FIND_LABEL = "Find a service account";

export const ACCOUNTS_LABEL = "Your service accounts";
export const KEYS_LABEL = "Live keys";

export const ISSUE_LABEL = "Issue a key";
export const REVOKE_LABEL = "Revoke";
export const RETIRE_LABEL = "Retire";
export const CONFIRM_REVOKE_LABEL = "Revoke key";
export const CONFIRM_RETIRE_LABEL = "Retire account";
export const KEEP_LABEL = "Keep it";
export const CANCEL_LABEL = "Cancel";

export const REVOKING =
  "The key is refused from its next use, and an integration still using it stops working.";
export const RETIRING =
  "The account and every key it has are refused from their next use. A retired account cannot be " +
  "brought back; register a new one instead.";

export const REGISTER_FORM_LABEL = "Register a service account";
export const REGISTER_BUTTON = "Register account";
export const ID_LABEL = "Account ID";
export const NAME_LABEL = "Name";
export const CEILING_LABEL = "Capabilities it may use";
export const ENDS_LABEL = "Stops working after";
export const SUBJECT_LABEL = "Identity provider client subject (optional)";

export const ISSUE_BUTTON = "Issue key";
export const KEY_NAME_LABEL = "Key name";
export const KEY_ENDS_LABEL = "Key stops working after";

export const NEW_KEY_HEADING = "The new key";
export const COPY_LABEL = "Copy key";
export const COPIED = "Copied.";
export const COPY_UNAVAILABLE = "This browser would not copy it. Select the key and copy it by hand.";
export const KEPT_LABEL = "I have kept it";

export function revokeQuestion(account: AccountRow, key: KeyRow): string {
  return `Revoke the key ${key.handle} of ${accountName(account)}?`;
}

export function retireQuestion(account: AccountRow): string {
  return `Retire ${accountName(account)}?`;
}

export function registered(clientId: string, notHeld: readonly string[]): string {
  const said = `${clientId} is registered. Issue it a key to use it.`;
  return notHeld.length === 0
    ? said
    : `${said} You do not hold ${notHeld.join(", ")} now, so it cannot use ${notHeld.length === 1 ? "that" : "those"} yet.`;
}

const REGISTER_FORM = "service-account";
const REGISTER_FIELDS: readonly string[] = ["client_id", "label", "ceiling", "not_after", "subject"];
const KEY_FORM = "service-account-key";
const KEY_FIELDS: readonly string[] = ["client_id", "label", "not_after"];

/** What a confirmation is about to do. */
type Pending =
  | { readonly kind: "revoke"; readonly account: AccountRow; readonly key: KeyRow }
  | { readonly kind: "retire"; readonly account: AccountRow };

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
    <section className="card" aria-label={NEW_KEY_HEADING}>
      <h2>{NEW_KEY_HEADING}</h2>
      <p>
        For <code>{issued.client_id}</code>, handle <code>{issued.handle}</code>, until{" "}
        {when(issued.lapses_at)}.
      </p>
      <p>
        <code aria-label="Key">{issued.key}</code>
      </p>
      <p className="note">{issued.shown_once}</p>
      {copied === null ? null : (
        <p className="note" role="status">
          {copied}
        </p>
      )}
      <div className="form-actions">
        <button type="button" className="button" onClick={copy}>
          {COPY_LABEL}
        </button>{" "}
        <button type="button" className="button" onClick={onKept}>
          {KEPT_LABEL}
        </button>
      </div>
    </section>
  );
}

function IssueForm({
  account,
  onIssued,
  onCancel,
}: {
  readonly account: AccountRow;
  readonly onIssued: (issued: IssuedKeyBody) => void;
  readonly onCancel: () => void;
}) {
  const [label, setLabel] = useState("");
  const [lapsesOn, setLapsesOn] = useState("");
  const [blank, setBlank] = useState<readonly FieldProblem[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);
  const problems = [...blank, ...(failure?.problems ?? [])];

  const issue = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      setFailure(null);
      const found = blankKeyProblems(lapsesOn);
      setBlank(found);
      if (found.length > 0) {
        return;
      }
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(ISSUE_KEY_API_PATH, {
          method: "POST",
          body: keyBody(account.client_id, label, lapsesOn),
        });
        setBusy(false);
        const issued = result.ok ? readIssuedKey(result.data) : null;
        if (issued !== null) {
          onIssued(issued);
          return;
        }
        if (!result.ok) {
          setFailure(result.failure);
        }
      })();
    },
    [account.client_id, label, lapsesOn, onIssued],
  );

  return (
    <section className="card">
      <h2>Issue a key for {accountName(account)}</h2>
      <form className="form" aria-label={`Issue a key for ${accountName(account)}`} onSubmit={issue}>
        <label className="control-label">
          {KEY_NAME_LABEL}{" "}
          <input
            className="form-control"
            type="text"
            name="label"
            autoComplete="off"
            value={label}
            {...problemAttributes(problems, KEY_FORM, "label")}
            onChange={(event) => {
              setLabel(event.target.value);
            }}
          />
        </label>
        <FieldProblems problems={problems} form={KEY_FORM} names="label" />
        <label className="control-label">
          {KEY_ENDS_LABEL}{" "}
          <input
            className="form-control"
            type="date"
            name="not_after"
            value={lapsesOn}
            {...problemAttributes(problems, KEY_FORM, "not_after")}
            onChange={(event) => {
              setLapsesOn(event.target.value);
            }}
          />
        </label>
        <FieldProblems problems={problems} form={KEY_FORM} names="not_after" />
        <p className="field-description">
          The key is shown once, when it is issued. It stops working at the end of this day or of the
          account&apos;s own, whichever is sooner.
        </p>
        <div className="form-actions">
          <button type="button" className="button" onClick={onCancel}>
            {CANCEL_LABEL}
          </button>{" "}
          <button type="submit" className="button" disabled={busy}>
            {ISSUE_BUTTON}
          </button>
        </div>
      </form>
      {failure === null ? null : <FailureNotice failure={failure} fields={KEY_FIELDS} />}
    </section>
  );
}

function RegisterForm({ onRegistered }: { readonly onRegistered: (sentence: string) => void }) {
  const [clientId, setClientId] = useState("");
  const [label, setLabel] = useState("");
  const [ceiling, setCeiling] = useState("");
  const [lapsesOn, setLapsesOn] = useState("");
  const [subject, setSubject] = useState("");
  const [blank, setBlank] = useState<readonly FieldProblem[]>([]);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [busy, setBusy] = useState(false);
  const problems = [...blank, ...(failure?.problems ?? [])];

  const register = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      setFailure(null);
      const found = blankRegistrationProblems(clientId, ceiling, lapsesOn);
      setBlank(found);
      if (found.length > 0) {
        return;
      }
      const body = registrationBody(clientId, label, ceiling, lapsesOn, subject);
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(SERVICE_ACCOUNTS_API_PATH, { method: "POST", body });
        setBusy(false);
        if (result.ok) {
          const notHeld = (result.data as { not_held_now?: unknown }).not_held_now;
          setClientId("");
          setLabel("");
          setCeiling("");
          setLapsesOn("");
          setSubject("");
          onRegistered(registered(body.client_id, Array.isArray(notHeld) ? notHeld.map(String) : []));
          return;
        }
        setFailure(result.failure);
      })();
    },
    [clientId, label, ceiling, lapsesOn, subject, onRegistered],
  );

  return (
    <section className="card">
      <h2>{REGISTER_FORM_LABEL}</h2>
      <form className="form" aria-label={REGISTER_FORM_LABEL} onSubmit={register}>
        <label className="control-label">
          {ID_LABEL}{" "}
          <input
            className="form-control"
            type="text"
            name="client_id"
            autoComplete="off"
            spellCheck={false}
            value={clientId}
            {...problemAttributes(problems, REGISTER_FORM, "client_id")}
            onChange={(event) => {
              setClientId(event.target.value);
            }}
          />
        </label>
        <FieldProblems problems={problems} form={REGISTER_FORM} names="client_id" />
        <p className="field-description">{ID_SHAPE}</p>
        <label className="control-label">
          {NAME_LABEL}{" "}
          <input
            className="form-control"
            type="text"
            name="label"
            autoComplete="off"
            value={label}
            {...problemAttributes(problems, REGISTER_FORM, "label")}
            onChange={(event) => {
              setLabel(event.target.value);
            }}
          />
        </label>
        <FieldProblems problems={problems} form={REGISTER_FORM} names="label" />
        <label className="control-label">
          {CEILING_LABEL}{" "}
          <textarea
            className="form-control"
            name="ceiling"
            rows={4}
            spellCheck={false}
            value={ceiling}
            {...problemAttributes(problems, REGISTER_FORM, "ceiling")}
            onChange={(event) => {
              setCeiling(event.target.value);
            }}
          />
        </label>
        <FieldProblems problems={problems} form={REGISTER_FORM} names="ceiling" />
        <p className="field-description">{CEILING_RULE}</p>
        <label className="control-label">
          {ENDS_LABEL}{" "}
          <input
            className="form-control"
            type="date"
            name="not_after"
            value={lapsesOn}
            {...problemAttributes(problems, REGISTER_FORM, "not_after")}
            onChange={(event) => {
              setLapsesOn(event.target.value);
            }}
          />
        </label>
        <FieldProblems problems={problems} form={REGISTER_FORM} names="not_after" />
        <label className="control-label">
          {SUBJECT_LABEL}{" "}
          <input
            className="form-control"
            type="text"
            name="subject"
            autoComplete="off"
            spellCheck={false}
            value={subject}
            {...problemAttributes(problems, REGISTER_FORM, "subject")}
            onChange={(event) => {
              setSubject(event.target.value);
            }}
          />
        </label>
        <FieldProblems problems={problems} form={REGISTER_FORM} names="subject" />
        <p className="field-description">
          Only for an integration that signs in to the identity provider as a client of its own. Leave
          it empty for one that uses a key from this screen.
        </p>
        <div className="form-actions">
          <button type="submit" className="button" disabled={busy}>
            {REGISTER_BUTTON}
          </button>
        </div>
      </form>
      {failure === null ? null : <FailureNotice failure={failure} fields={REGISTER_FIELDS} />}
    </section>
  );
}

export function ServiceAccounts() {
  const [version, setVersion] = useState(0);
  const [said, setSaid] = useState<string | null>(null);
  const [issuing, setIssuing] = useState<AccountRow | null>(null);
  const [issued, setIssued] = useState<IssuedKeyBody | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const listing = useListing<AccountRow>(SERVICE_ACCOUNTS_API_PATH, { choices: ACCOUNT_FILTERS, version });
  const page = listing.failure || listing.busy ? null : readAccounts(listing.body);
  const accounts = listing.rows;
  const keys = keysOf(accounts);

  const changed = useCallback((sentence: string) => {
    setSaid(sentence);
    setVersion((current) => current + 1);
  }, []);

  const onIssued = useCallback((key: IssuedKeyBody) => {
    setIssuing(null);
    setIssued(key);
    setSaid(null);
    setVersion((current) => current + 1);
  }, []);

  const send = useCallback(
    (asked: Pending) => {
      setBusy(true);
      void (async () => {
        const result =
          asked.kind === "revoke"
            ? await request<unknown>(REVOKE_KEY_API_PATH, { method: "POST", body: revocationBody(asked.key.handle) })
            : await request<unknown>(RETIRE_ACCOUNT_API_PATH, {
                method: "POST",
                body: retirementBody(asked.account.client_id),
              });
        setBusy(false);
        setPending(null);
        if (result.ok) {
          changed(toldBy(result.data));
          return;
        }
        setFailure(result.failure);
      })();
    },
    [changed],
  );

  return (
    <article className="page">
      <p className="note">{ACCOUNTS_CRUMB}</p>
      <h1>{ACCOUNTS_HEADING}</h1>
      <p className="lede">{ACCOUNTS_LEDE}</p>
      {said === null || said === "" ? null : (
        <p className="note" role="status">
          {said}
        </p>
      )}
      {issued === null ? null : (
        <NewKey
          issued={issued}
          onKept={() => {
            setIssued(null);
          }}
        />
      )}
      {failure === null ? null : <FailureNotice failure={failure} />}
      {pending === null ? null : (
        <ConfirmAction
          question={pending.kind === "revoke" ? revokeQuestion(pending.account, pending.key) : retireQuestion(pending.account)}
          consequence={pending.kind === "revoke" ? REVOKING : RETIRING}
          confirmLabel={pending.kind === "revoke" ? CONFIRM_REVOKE_LABEL : CONFIRM_RETIRE_LABEL}
          cancelLabel={KEEP_LABEL}
          busy={busy}
          onConfirm={() => {
            send(pending);
          }}
          onCancel={() => {
            setPending(null);
          }}
        />
      )}
      <ListControls label={FIND_LABEL} listing={listing} choices={ACCOUNT_FILTERS} sorts={ACCOUNT_SORTS} />
      <section className="card">
        <h2>{ACCOUNTS_LABEL}</h2>
        {listing.failure ? (
          <FailureNotice failure={listing.failure} />
        ) : listing.busy ? (
          <p className="note" role="status">
            {READING_ACCOUNTS}
          </p>
        ) : accounts.length === 0 ? (
          <p className="note">{narrows(listing.question) ? NONE_MATCH : NO_ACCOUNTS}</p>
        ) : (
          <>
            <div className="grid__scroll">
              <table className="grid__table" aria-label={ACCOUNTS_LABEL}>
                <thead>
                  <tr>
                    <th scope="col">Account</th>
                    <th scope="col">Capabilities</th>
                    <th scope="col">Stops working</th>
                    <th scope="col">Registered</th>
                    <th scope="col">Controls</th>
                  </tr>
                </thead>
                <tbody>
                  {accounts.map((row) => (
                    <tr key={row.client_id}>
                      <td>
                        {row.label === "" ? null : <>{row.label} </>}
                        <code>{row.client_id}</code>
                      </td>
                      <td>
                        <ul aria-label={`Capabilities of ${accountName(row)}`}>
                          {row.ceiling.map((one) => (
                            <li key={one}>
                              <code>{one}</code>
                              {row.not_held_now.includes(one) ? " (you do not hold it now)" : null}
                            </li>
                          ))}
                        </ul>
                      </td>
                      <td>{when(row.lapses_at)}</td>
                      <td>{when(row.created_at)}</td>
                      <td>
                        <button
                          type="button"
                          className="button"
                          aria-label={`${ISSUE_LABEL}: ${accountName(row)}`}
                          onClick={() => {
                            setFailure(null);
                            setIssuing(row);
                          }}
                        >
                          {ISSUE_LABEL}
                        </button>{" "}
                        <button
                          type="button"
                          className="button"
                          aria-label={`${RETIRE_LABEL}: ${accountName(row)}`}
                          disabled={busy}
                          onClick={() => {
                            setFailure(null);
                            setPending({ kind: "retire", account: row });
                          }}
                        >
                          {RETIRE_LABEL}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ShowMore listing={listing} />
          </>
        )}
        {page?.truncated ? <p className="note">{MORE_ACCOUNTS}</p> : null}
        {page === null ? null : (
          <>
            <p className="hint note">{page.reach}</p>
            <p className="hint note">{page.ownership}</p>
          </>
        )}
      </section>

      {page === null || accounts.length === 0 ? null : (
        <section className="card">
          <h2>{KEYS_LABEL}</h2>
          {keys.length === 0 ? (
            <p className="note">{NO_KEYS}</p>
          ) : (
            <div className="grid__scroll">
              <table className="grid__table" aria-label={KEYS_LABEL}>
                <thead>
                  <tr>
                    <th scope="col">Account</th>
                    <th scope="col">Key</th>
                    <th scope="col">Name</th>
                    <th scope="col">Issued</th>
                    <th scope="col">Stops working</th>
                    <th scope="col">Control</th>
                  </tr>
                </thead>
                <tbody>
                  {keys.map(({ account, key }) => (
                    <tr key={key.handle}>
                      <td>
                        <code>{account.client_id}</code>
                      </td>
                      <td>
                        <code>{key.handle}</code>
                      </td>
                      <td>{key.label}</td>
                      <td>{when(key.issued_at)}</td>
                      <td>{when(key.lapses_at)}</td>
                      <td>
                        <button
                          type="button"
                          className="button"
                          aria-label={`${REVOKE_LABEL}: ${key.handle}`}
                          disabled={busy}
                          onClick={() => {
                            setFailure(null);
                            setPending({ kind: "revoke", account, key });
                          }}
                        >
                          {REVOKE_LABEL}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="hint note">{ROTATION}</p>
        </section>
      )}

      {issuing === null ? null : (
        <IssueForm
          key={issuing.client_id}
          account={issuing}
          onIssued={onIssued}
          onCancel={() => {
            setIssuing(null);
          }}
        />
      )}
      <RegisterForm onRegistered={changed} />
    </article>
  );
}
