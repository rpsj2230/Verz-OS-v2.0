/**
 * Sessions: who is signed in now, and the control to end one.
 *
 * `docs/screens.html` SCREEN 10, People and Grants, is where the design puts what happens to a
 * person's sign-ins, and this screen sits beside it in Govern. The layout is that screen's: the
 * crumb, the filter bar, one card holding the list, and the hint under it saying the one thing a
 * reader must not assume. Revoking a grant does not close a session that is already open, which is
 * why the control exists at all.
 *
 * **Ending one is confirmed, and the confirmation says what happens in the API's words.** The
 * panel names the person and the sign-in and carries `brain.session_routes`' sentence: the session
 * is refused from its next request, no grant is removed, and the person may sign in again. A
 * success says what was ended and when the database recorded it; a failure is the API's sentence.
 *
 * **The reader's own session has no control and says why.** Ending it would refuse the request
 * after the one that ended it, which is signing out with extra steps and no way back to this page.
 *
 * **Nothing here decides who may see or end a session.** `endable` came from `brain.console.govern.
 * may_end` on the server and only decides whether a button is drawn. The route decides again.
 *
 * **A write is followed by a fresh request**, keyed on a counter, for `People.tsx`' reason: the
 * list shows what the database holds, not what this page sent.
 *
 * Task ids: M27.7.10
 */

import { useCallback, useState, type ChangeEvent } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { ConfirmAction } from "../components/ConfirmAction";
import { Notice } from "../ui/Notice";
import {
  END_SESSION_API_PATH,
  NO_SESSION_FILTERS,
  SORT_LABELS,
  SORTS,
  endQuestion,
  endingBody,
  narrowed,
  offeredDepartments,
  offeredPeople,
  readSessionsPage,
  sessionsApiPath,
  when,
  type SessionFilters,
  type SessionRow,
  type Sort,
} from "./sessionsQuery";
import { SOMETHING_DID_NOT_WORK } from "./Overview";

export const SESSIONS_HEADING = "Sessions";
export const SESSIONS_CRUMB = "Govern › Sessions";
export const SESSIONS_LEDE =
  "Who is signed in now, from when, and until when at the latest. Taking a grant away does not " +
  "close a session that is already open; ending the session does.";

/** The four states. */
export const READING_SESSIONS = "Reading who is signed in.";
export const NO_SESSIONS = "There are no sessions to show.";
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";

/** A full load. A fact about there being more, and never a figure. */
export const MORE_SESSIONS = "This list came back full, so there are more sessions than it shows.";

/** Nothing on the page matches the filters chosen. About the page, not the company. */
export const NONE_MATCH = "No session on this page matches these filters.";

/** What the reader's own row says instead of a control. */
export const YOUR_SESSION = "This is the session you are using. Sign out to end it.";

export const END_LABEL = "End session";
export const KEEP_LABEL = "Keep it";

export const SESSIONS_LABEL = "Sessions signed in now";
export const FILTERS_LABEL = "Narrow the sessions";
export const ALL_DEPARTMENTS = "All departments";
export const EVERYONE = "Everyone";

/** What a success says: whose, and the instant the database recorded. */
export function endedSentence(row: SessionRow, endedAt: string): string {
  return `${row.display_name}'s session was ended at ${when(endedAt)}. The next request made with it is refused.`;
}

function Failure({ failure }: { readonly failure: ApiFailure }) {
  return (
    <Notice
      title={failure.status === 0 ? THE_BRAIN_COULD_NOT_BE_REACHED : SOMETHING_DID_NOT_WORK}
      traceId={failure.traceId}
    >
      <p>{failure.message}</p>
    </Notice>
  );
}

function readEndedAt(payload: unknown): string | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const ended = (payload as { ended_at?: unknown }).ended_at;
  return typeof ended === "string" ? ended : null;
}

function SessionList({ onEnded }: { readonly onEnded: (sentence: string) => void }) {
  const answer = useResource<unknown>(sessionsApiPath());
  const [filters, setFilters] = useState<SessionFilters>(NO_SESSION_FILTERS);
  const [confirming, setConfirming] = useState<SessionRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);

  const end = useCallback(
    (row: SessionRow) => {
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(END_SESSION_API_PATH, {
          method: "POST",
          body: endingBody(row),
        });
        setBusy(false);
        if (!result.ok) {
          setFailure(result.failure);
          setConfirming(null);
          return;
        }
        setFailure(null);
        setConfirming(null);
        onEnded(endedSentence(row, readEndedAt(result.data) ?? ""));
      })();
    },
    [onEnded],
  );

  if (answer.failure) {
    return <Failure failure={answer.failure} />;
  }
  if (answer.busy) {
    return (
      <p className="note" role="status">
        {READING_SESSIONS}
      </p>
    );
  }

  const page = readSessionsPage(answer.data);
  const shown = narrowed(page.sessions, filters);
  const set = (name: keyof SessionFilters) => (event: ChangeEvent<HTMLSelectElement>) => {
    setFilters({ ...filters, [name]: event.target.value });
  };

  return (
    <>
      {page.sessions.length === 0 ? null : (
        <form className="form" aria-label={FILTERS_LABEL} onSubmit={(event) => event.preventDefault()}>
          <label className="control-label">
            Department{" "}
            <select className="form-control" value={filters.department} onChange={set("department")}>
              <option value="">{ALL_DEPARTMENTS}</option>
              {offeredDepartments(page.sessions).map((one) => (
                <option key={one} value={one}>
                  {one}
                </option>
              ))}
            </select>
          </label>
          <label className="control-label">
            Person{" "}
            <select className="form-control" value={filters.person} onChange={set("person")}>
              <option value="">{EVERYONE}</option>
              {offeredPeople(page.sessions).map((one) => (
                <option key={one.id} value={one.id}>
                  {one.name}
                </option>
              ))}
            </select>
          </label>
          <label className="control-label">
            Order{" "}
            <select
              className="form-control"
              value={filters.sort}
              onChange={(event) => {
                setFilters({ ...filters, sort: event.target.value as Sort });
              }}
            >
              {SORTS.map((one) => (
                <option key={one} value={one}>
                  {SORT_LABELS[one]}
                </option>
              ))}
            </select>
          </label>
        </form>
      )}

      {failure === null ? null : <Failure failure={failure} />}

      {confirming === null ? null : (
        <ConfirmAction
          question={endQuestion(confirming)}
          consequence={page.ending}
          confirmLabel={END_LABEL}
          cancelLabel={KEEP_LABEL}
          busy={busy}
          onConfirm={() => {
            end(confirming);
          }}
          onCancel={() => {
            setConfirming(null);
          }}
        />
      )}

      <section className="card">
        <h2>Signed in now</h2>
        {page.sessions.length === 0 ? (
          <p className="note">{NO_SESSIONS}</p>
        ) : shown.length === 0 ? (
          <p className="note">{NONE_MATCH}</p>
        ) : (
          <div className="grid__scroll">
            <table className="grid__table" aria-label={SESSIONS_LABEL}>
              <thead>
                <tr>
                  <th scope="col">Person</th>
                  <th scope="col">Department</th>
                  <th scope="col">Signed in</th>
                  <th scope="col">Ends by</th>
                  <th scope="col">Second factor</th>
                  <th scope="col">Control</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((row) => (
                  <tr key={row.session_id}>
                    <td>
                      {row.display_name} <code>{row.principal_id}</code>
                    </td>
                    <td>{row.department ?? ""}</td>
                    <td>{when(row.signed_in_at)}</td>
                    <td>{when(row.lapses_at)}</td>
                    <td>{row.second_factor ? "Yes" : "No"}</td>
                    <td>
                      {row.yours ? (
                        <span className="note">{YOUR_SESSION}</span>
                      ) : row.endable ? (
                        <button
                          type="button"
                          className="button"
                          aria-label={`${END_LABEL}: ${row.display_name}`}
                          disabled={busy}
                          onClick={() => {
                            setFailure(null);
                            setConfirming(row);
                          }}
                        >
                          {END_LABEL}
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {page.truncated ? <p className="note">{MORE_SESSIONS}</p> : null}
        {page.appears === "" ? null : <p className="note">{page.appears}</p>}
      </section>
    </>
  );
}

export function Sessions() {
  // A counter rather than a boolean, so two endings in a row remount twice. Never rendered.
  const [generation, setGeneration] = useState(0);
  const [ended, setEnded] = useState<string | null>(null);
  const onEnded = useCallback((sentence: string) => {
    setEnded(sentence);
    setGeneration((current) => current + 1);
  }, []);

  return (
    <article className="page">
      <p className="note">{SESSIONS_CRUMB}</p>
      <h1>{SESSIONS_HEADING}</h1>
      <p className="lede">{SESSIONS_LEDE}</p>
      {ended === null ? null : (
        <p className="note" role="status">
          {ended}
        </p>
      )}
      <SessionList key={generation} onEnded={onEnded} />
    </article>
  );
}
