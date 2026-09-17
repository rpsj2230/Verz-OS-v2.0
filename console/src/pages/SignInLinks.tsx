/**
 * Sign-in links: who can sign in, since when, linking an account to a person, and unlinking one.
 *
 * Beside People and grants and Sessions in Govern, which is where `docs/screens.html` SCREEN 10
 * puts who a person is and how they get in. The layout is that screen's: the crumb, one card with
 * the list, a card with the form, and the hint saying what the screen cannot show. The decision
 * about who may open it and what an unlink may do is `brain.console.sign_in_links` and
 * `brain.identity.sign_in_binding`, on the server.
 *
 * **The account is not on this page, and the page says where it is.** The server keeps a one-way
 * fingerprint of the identity provider account and never the account, so a row names the person
 * and the date, and the API's sentence says the identity provider's user list shows the account.
 * See `signInLinksQuery.AN_ACCOUNT_TYPED_IN_IS_SENT_ONCE_AND_NOT_KEPT` for the form.
 *
 * **Unlinking is confirmed, and the last administrator's link has no control.** The row says why
 * in the API's own sentence instead of drawing a button the store will refuse, and if the refusal
 * happens anyway, because another administrator was unlinked a moment earlier, the 409 carries the
 * same sentence and the page shows it. Unlinking your own link is allowed while another
 * administrator can sign in, and the confirmation says you will be signed out.
 *
 * **Four states and four sentences**, for `docs/admin-console.md`'s reason.
 *
 * **A 409 is still a failure, with its reference.** Its sentence is the one the API's document
 * carries, and it is drawn by `ui/FailureNotice.tsx` in place of the API's message rather than as a
 * note, so the reference is under it like every other refusal.
 *
 * Task ids: M27.7.11, M27.8.5
 */

import { useCallback, useState, type FormEvent } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { ListControls, NOTHING_MATCHES, ShowMore } from "../components/ListControls";
import { narrows } from "../components/listing";
import { useListing } from "../components/useListing";
import { ConfirmAction } from "../components/ConfirmAction";
import { FailureNotice } from "../ui/FailureNotice";
import { FieldProblems, problemAttributes } from "../ui/FieldProblems";
import {
  LINK_API_PATH,
  UNLINK_API_PATH,
  linkOutcome,
  linkProblems,
  linkedOn,
  LINKS_API_PATH,
  LINK_FILTERS,
  LINK_SORTS,
  readLinksPage,
  unlinkSentence,
  type LinkRow,
} from "./signInLinksQuery";

export const LINKS_HEADING = "Sign-in links";
export const LINKS_CRUMB = "Govern › Sign-in links";
export const LINKS_LEDE =
  "Which people can sign in, and since when. Link an identity provider account to a person, or " +
  "unlink one to stop that account signing in as them.";

/** The four states. */
export const READING_LINKS = "Reading who can sign in.";
export const NO_LINKS = "There are no sign-in links to show.";
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";

export const MORE_LINKS = "This list came back full, so there are more links than it shows.";
export const NONE_MATCH = NOTHING_MATCHES;

/** What the last administrator's row says in place of a control. */
export const KEPT = "Kept: the last administrator who can sign in.";

export const UNLINK_LABEL = "Unlink";
export const CONFIRM_UNLINK_LABEL = "Unlink this sign-in";
export const KEEP_LABEL = "Keep it";
export const YOUR_OWN_LINK =
  "This is your own sign-in link. You will be signed out on your next request.";

export const LINKS_LABEL = "People who can sign in";
export const FIND_LABEL = "Find a person who can sign in";
export const LINK_FORM_LABEL = "Link an account to a person";
export const ACCOUNT_LABEL = "Identity provider account ID";
export const PERSON_LABEL = "Person ID";
export const LINK_BUTTON = "Link this account";

export function unlinkQuestion(row: LinkRow): string {
  return `Unlink ${row.display_name}'s sign-in?`;
}

/** The names the link form's two inputs are sent under, and the prefix of the lists beside them. */
const LINK_FIELDS: readonly string[] = ["subject", "principal_id"];
const LINK_FORM = "sign-in-link";

/** A failure, and the sentence its own document carried when it was a 409. */
interface Refused {
  readonly failure: ApiFailure;
  readonly sentence?: string;
}

function RefusedNotice({ refused, fields }: { readonly refused: Refused; readonly fields?: readonly string[] }) {
  return (
    <FailureNotice
      failure={refused.failure}
      {...(refused.sentence === undefined ? {} : { sentence: refused.sentence })}
      {...(fields === undefined ? {} : { fields })}
    />
  );
}

function LinkForm({ onLinked }: { readonly onLinked: (sentence: string) => void }) {
  const [subject, setSubject] = useState("");
  const [principalId, setPrincipalId] = useState("");
  const [problems, setProblems] = useState<readonly string[]>([]);
  const [failure, setFailure] = useState<Refused | null>(null);
  const [busy, setBusy] = useState(false);
  const refusedProblems = failure?.failure.problems ?? [];

  const submit = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const found = linkProblems(subject, principalId);
      setProblems(found);
      setFailure(null);
      if (found.length > 0) {
        return;
      }
      const body = { subject, principal_id: principalId.trim() };
      // Emptied before the answer, whatever it is. See AN_ACCOUNT_TYPED_IN_IS_SENT_ONCE_AND_NOT_KEPT.
      setSubject("");
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(LINK_API_PATH, { method: "POST", body });
        setBusy(false);
        if (result.ok) {
          const sentence = linkOutcome(result.data) ?? "";
          setPrincipalId("");
          onLinked(sentence);
          return;
        }
        const refusal = result.failure.status === 409 ? linkOutcome(result.body) : null;
        setFailure(refusal === null ? { failure: result.failure } : { failure: result.failure, sentence: refusal });
      })();
    },
    [subject, principalId, onLinked],
  );

  return (
    <section className="card">
      <h2>{LINK_FORM_LABEL}</h2>
      <form className="form" aria-label={LINK_FORM_LABEL} onSubmit={submit}>
        <label className="control-label">
          {ACCOUNT_LABEL}{" "}
          <input
            className="form-control"
            type="text"
            name="subject"
            autoComplete="off"
            spellCheck={false}
            value={subject}
            {...problemAttributes(refusedProblems, LINK_FORM, "subject")}
            onChange={(event) => {
              setSubject(event.target.value);
            }}
          />
        </label>
        <FieldProblems problems={refusedProblems} form={LINK_FORM} names="subject" />
        <label className="control-label">
          {PERSON_LABEL}{" "}
          <input
            className="form-control"
            type="text"
            name="principal_id"
            autoComplete="off"
            spellCheck={false}
            value={principalId}
            {...problemAttributes(refusedProblems, LINK_FORM, "principal_id")}
            onChange={(event) => {
              setPrincipalId(event.target.value);
            }}
          />
        </label>
        <FieldProblems problems={refusedProblems} form={LINK_FORM} names="principal_id" />
        {problems.length === 0 ? null : (
          <ul className="form__problems" role="status">
            {problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        )}
        <div className="form-actions">
          <button type="submit" className="button" disabled={busy}>
            {LINK_BUTTON}
          </button>
        </div>
      </form>
      {failure === null ? null : <RefusedNotice refused={failure} fields={LINK_FIELDS} />}
    </section>
  );
}

function LinkList({
  version,
  onUnlinked,
}: {
  readonly version: number;
  readonly onUnlinked: (sentence: string) => void;
}) {
  const listing = useListing<LinkRow>(LINKS_API_PATH, { choices: LINK_FILTERS, version });
  const [confirming, setConfirming] = useState<LinkRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Refused | null>(null);

  const unlink = useCallback(
    (row: LinkRow) => {
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(UNLINK_API_PATH, {
          method: "POST",
          body: { principal_id: row.principal_id },
        });
        setBusy(false);
        setConfirming(null);
        if (result.ok) {
          onUnlinked(unlinkSentence(result.data));
          return;
        }
        const refusal = result.failure.status === 409 ? unlinkSentence(result.body) : "";
        setFailure(refusal === "" ? { failure: result.failure } : { failure: result.failure, sentence: refusal });
      })();
    },
    [onUnlinked],
  );

  const page = readLinksPage(listing.body);
  const shown = page.links;

  return (
    <>
      <ListControls label={FIND_LABEL} listing={listing} choices={LINK_FILTERS} sorts={LINK_SORTS} />
      {failure === null ? null : <RefusedNotice refused={failure} />}
      {confirming === null ? null : (
        <ConfirmAction
          question={unlinkQuestion(confirming)}
          consequence={page.unlinking}
          {...(confirming.yours ? { warning: YOUR_OWN_LINK } : {})}
          confirmLabel={CONFIRM_UNLINK_LABEL}
          cancelLabel={KEEP_LABEL}
          busy={busy}
          onConfirm={() => {
            unlink(confirming);
          }}
          onCancel={() => {
            setConfirming(null);
          }}
        />
      )}
      <section className="card">
        <h2>{LINKS_LABEL}</h2>
        {listing.failure ? (
          <FailureNotice failure={listing.failure} />
        ) : listing.busy ? (
          <p className="note" role="status">
            {READING_LINKS}
          </p>
        ) : shown.length === 0 ? (
          <p className="note">{narrows(listing.question) ? NONE_MATCH : NO_LINKS}</p>
        ) : (
          <>
            <div className="grid__scroll">
              <table className="grid__table" aria-label={LINKS_LABEL}>
                <thead>
                  <tr>
                    <th scope="col">Person</th>
                    <th scope="col">Department</th>
                    <th scope="col">Linked on</th>
                    <th scope="col">Control</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((row) => (
                    <tr key={row.principal_id}>
                      <td>
                        {row.display_name} <code>{row.principal_id}</code>
                      </td>
                      <td>{row.department ?? ""}</td>
                      <td>{linkedOn(row.linked_at)}</td>
                      <td>
                        {row.last_administrator ? (
                          <span className="note">{KEPT}</span>
                        ) : (
                          <button
                            type="button"
                            className="button"
                            aria-label={`${UNLINK_LABEL}: ${row.display_name}`}
                            disabled={busy}
                            onClick={() => {
                              setFailure(null);
                              setConfirming(row);
                            }}
                          >
                            {UNLINK_LABEL}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ShowMore listing={listing} />
          </>
        )}
        {page.truncated ? <p className="note">{MORE_LINKS}</p> : null}
        {page.links.some((row) => row.last_administrator) ? (
          <p className="note">{page.lastAdministrator}</p>
        ) : null}
        {page.account === "" ? null : <p className="hint note">{page.account}</p>}
      </section>
    </>
  );
}

export function SignInLinks() {
  const [version, setVersion] = useState(0);
  const [said, setSaid] = useState<string | null>(null);
  const changed = useCallback((sentence: string) => {
    setSaid(sentence);
    setVersion((current) => current + 1);
  }, []);

  return (
    <article className="page">
      <p className="note">{LINKS_CRUMB}</p>
      <h1>{LINKS_HEADING}</h1>
      <p className="lede">{LINKS_LEDE}</p>
      {said === null || said === "" ? null : (
        <p className="note" role="status">
          {said}
        </p>
      )}
      <LinkList version={version} onUnlinked={changed} />
      <LinkForm onLinked={changed} />
    </article>
  );
}
