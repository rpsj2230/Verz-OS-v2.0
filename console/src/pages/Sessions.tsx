/**
 * Sessions: who is signed in now, and the control to end one or several.
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
 * **Ending several is one confirmation listing each session and what happens to it**, and one
 * request that the route runs as that many single endings. The page then says, per session, whether
 * it was ended, because a bulk act whose partial failure is not stated is the unsafe version.
 *
 * **The reader's own session has no control and no box, and says why.** Ending it would refuse the
 * request after the one that ended it, which is signing out with extra steps and no way back.
 *
 * **Nothing here decides who may see or end a session.** `endable` came from `brain.console.govern.
 * may_end` on the server and only decides whether a button or a box is drawn. The route decides
 * again, per session.
 *
 * **The search, the filters, the order and "Show more" are requests** (`components/useListing.ts`),
 * and a write asks for the first page again with the same question, for `People.tsx`' reason: the
 * list shows what the database holds, not what this page sent.
 *
 * Task ids: M27.7.10, M27.8.6
 */

import { useCallback, useState } from "react";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { ConfirmAction } from "../components/ConfirmAction";
import { ListControls, NOTHING_MATCHES, ShowMore } from "../components/ListControls";
import { narrows } from "../components/listing";
import { useListing } from "../components/useListing";
import { Notice } from "../ui/Notice";
import {
  END_SELECTED_QUESTION,
  END_SESSIONS_API_PATH,
  END_SESSION_API_PATH,
  MOST_ENDED_AT_ONCE,
  SESSIONS_API_PATH,
  SESSION_FILTERS,
  SESSION_SORTS,
  endQuestion,
  endingBody,
  endingLine,
  endingsBody,
  outcomeLine,
  readOutcomes,
  readSessionsPage,
  tickable,
  when,
  type SessionRow,
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

/** Nothing matches the search and filters chosen. About the reader's own sessions. */
export const NONE_MATCH = NOTHING_MATCHES;

/** What the reader's own row says instead of a control. */
export const YOUR_SESSION = "This is the session you are using. Sign out to end it.";

export const END_LABEL = "End session";
export const KEEP_LABEL = "Keep it";
export const END_SELECTED_LABEL = "End the ticked sessions";
export const KEEP_ALL_LABEL = "Keep them";
export const TICK_LABEL = "Tick to end";
/** Said when more are ticked than one request may carry. A bound, not a count of anything. */
export const TOO_MANY_TICKED =
  "One request ends at most fifty sessions. Untick some and end the rest afterwards.";

export const SESSIONS_LABEL = "Sessions signed in now";
export const FILTERS_LABEL = "Narrow the sessions";

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

function SessionList({
  version,
  onEnded,
}: {
  readonly version: number;
  readonly onEnded: (sentences: readonly string[]) => void;
}) {
  const listing = useListing<SessionRow>(SESSIONS_API_PATH, { choices: SESSION_FILTERS, version });
  const [confirming, setConfirming] = useState<SessionRow | null>(null);
  const [confirmingTicked, setConfirmingTicked] = useState(false);
  const [ticked, setTicked] = useState<ReadonlySet<string>>(new Set());
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
        onEnded([endedSentence(row, readEndedAt(result.data) ?? "")]);
      })();
    },
    [onEnded],
  );

  const endTicked = useCallback(
    (rows: readonly SessionRow[]) => {
      setBusy(true);
      void (async () => {
        const result = await request<unknown>(END_SESSIONS_API_PATH, {
          method: "POST",
          body: endingsBody(rows),
        });
        setBusy(false);
        setConfirmingTicked(false);
        if (!result.ok) {
          setFailure(result.failure);
          return;
        }
        setFailure(null);
        setTicked(new Set());
        const byId = new Map(rows.map((one) => [one.session_id, one]));
        onEnded(readOutcomes(result.data).map((one) => outcomeLine(byId.get(one.session_id), one)));
      })();
    },
    [onEnded],
  );

  const names = new Map(listing.rows.map((one) => [one.principal_id, one.display_name]));
  const choices = SESSION_FILTERS.map((choice) =>
    choice.column === "principal_id"
      ? { ...choice, describe: (value: string) => names.get(value) ?? value }
      : choice,
  );
  const page = readSessionsPage(listing.body);
  const tickedRows = page.sessions.filter((one) => ticked.has(one.session_id) && tickable(one));
  const toggle = (row: SessionRow) => {
    const next = new Set(ticked);
    if (next.has(row.session_id)) {
      next.delete(row.session_id);
    } else {
      next.add(row.session_id);
    }
    setTicked(next);
  };

  return (
    <>
      <ListControls label={FILTERS_LABEL} listing={listing} choices={choices} sorts={SESSION_SORTS} />

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

      {!confirmingTicked ? null : (
        <ConfirmAction
          question={END_SELECTED_QUESTION}
          consequence={page.ending}
          details={
            <ul className="confirm__items">
              {tickedRows.map((one) => (
                <li key={one.session_id}>{endingLine(one)}</li>
              ))}
            </ul>
          }
          confirmLabel={END_SELECTED_LABEL}
          cancelLabel={KEEP_ALL_LABEL}
          busy={busy}
          onConfirm={() => {
            endTicked(tickedRows);
          }}
          onCancel={() => {
            setConfirmingTicked(false);
          }}
        />
      )}

      <section className="card">
        <h2>Signed in now</h2>
        {listing.failure ? (
          <Failure failure={listing.failure} />
        ) : listing.busy ? (
          <p className="note" role="status">
            {READING_SESSIONS}
          </p>
        ) : page.sessions.length === 0 ? (
          <p className="note">{narrows(listing.question) ? NONE_MATCH : NO_SESSIONS}</p>
        ) : (
          <>
            <div className="grid__scroll">
              <table className="grid__table" aria-label={SESSIONS_LABEL}>
                <thead>
                  <tr>
                    <th scope="col">{TICK_LABEL}</th>
                    <th scope="col">Person</th>
                    <th scope="col">Department</th>
                    <th scope="col">Signed in</th>
                    <th scope="col">Ends by</th>
                    <th scope="col">Second factor</th>
                    <th scope="col">Control</th>
                  </tr>
                </thead>
                <tbody>
                  {page.sessions.map((row) => (
                    <tr key={row.session_id}>
                      <td>
                        {tickable(row) ? (
                          <input
                            type="checkbox"
                            aria-label={`${TICK_LABEL}: ${row.display_name}`}
                            checked={ticked.has(row.session_id)}
                            disabled={busy}
                            onChange={() => {
                              toggle(row);
                            }}
                          />
                        ) : null}
                      </td>
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
            {tickedRows.length > MOST_ENDED_AT_ONCE ? <p className="note">{TOO_MANY_TICKED}</p> : null}
            {page.sessions.some(tickable) ? (
              <div className="form-actions">
                <button
                  type="button"
                  className="button"
                  disabled={busy || tickedRows.length === 0 || tickedRows.length > MOST_ENDED_AT_ONCE}
                  onClick={() => {
                    setFailure(null);
                    setConfirmingTicked(true);
                  }}
                >
                  {END_SELECTED_LABEL}
                </button>
              </div>
            ) : null}
            <ShowMore listing={listing} />
          </>
        )}
        {page.truncated ? <p className="note">{MORE_SESSIONS}</p> : null}
        {page.appears === "" ? null : <p className="note">{page.appears}</p>}
      </section>
    </>
  );
}

export function Sessions() {
  // A counter, so two endings in a row ask twice. Never rendered.
  const [version, setVersion] = useState(0);
  const [ended, setEnded] = useState<readonly string[]>([]);
  const onEnded = useCallback((sentences: readonly string[]) => {
    setEnded(sentences);
    setVersion((current) => current + 1);
  }, []);

  return (
    <article className="page">
      <p className="note">{SESSIONS_CRUMB}</p>
      <h1>{SESSIONS_HEADING}</h1>
      <p className="lede">{SESSIONS_LEDE}</p>
      {ended.length === 0 ? null : (
        <div role="status">
          {ended.map((sentence, index) => (
            <p className="note" key={`${String(index)}-${sentence}`}>
              {sentence}
            </p>
          ))}
        </div>
      )}
      <SessionList version={version} onEnded={onEnded} />
    </article>
  );
}
