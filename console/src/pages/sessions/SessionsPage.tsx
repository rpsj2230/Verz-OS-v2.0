/**
 * Sessions, on the shared page kit: who is signed in now, and ending one session or several.
 *
 * Taking a grant away does not close a session that is already open, which is why this page
 * exists. Each ending is confirmed in the API's own sentence. Several are ended by one confirmed
 * request that the route runs as that many single endings, and the page then says what came of
 * each, because a bulk act whose partial failure goes unsaid is the unsafe version. The reader's
 * own session has no control: ending it is signing out.
 *
 * Removed in the rebuild: the principal id beside every name, the crumb and lede paragraphs that
 * restated the design, the separate "Signed in now" card, the tick column and its own button (the
 * kit's selection and bulk bar do both), and the served "when a session appears" note under a
 * full list, which is now the empty state's sentence.
 *
 * Task ids: M27.7.10, M27.8.6, M27.16.1
 */

import { MonitorSmartphone } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import type { FilterChoice } from "../../components/listing";
import { useListing } from "../../components/useListing";
import { Chip, ConfirmDialog, ListPage, Note, type EntityColumn } from "../../components/kit";
import { Button } from "../../components/ui/button";
import { FailureNotice } from "../../ui/FailureNotice";
import {
  END_SELECTED_QUESTION,
  END_SESSIONS_API_PATH,
  END_SESSION_API_PATH,
  MOST_ENDED_AT_ONCE,
  SESSIONS_API_PATH,
  SESSION_FILTERS,
  SESSION_SORTS,
  endQuestion,
  endedSentence,
  endingBody,
  endingLine,
  endingsBody,
  factorWords,
  outcomeLine,
  readEndedAt,
  readOutcomes,
  readSessionsPage,
  tickable,
  when,
  type SessionRow,
} from "../sessionsQuery";

export const SESSIONS_HEADING = "Sessions";
export const SESSIONS_LEDE = "Who is signed in now, and until when.";
export const PEOPLE_AND_ACCESS = "People and access";

export const LOADING_SESSIONS = "Loading sessions.";
export const NO_SESSIONS = "No sessions to show";
/** Said when the API sent no sentence of its own about when a session appears. */
export const APPEARS_FALLBACK = "A session appears here from the first request it makes.";
/** A full load. A fact about there being more, and never a figure. */
export const MORE_SESSIONS = "There are more sessions than one list can hold. Search or filter to find the rest.";

export const SESSIONS_LIST_LABEL = "Sessions signed in now";
export const FILTERS_LABEL = "Narrow the sessions";
export const SEARCH_HINT = "Search by name or department";

export const PERSON_COLUMN = "Person";
export const SIGNED_IN_COLUMN = "Signed in";
export const ENDS_BY_COLUMN = "Ends by";
export const SECOND_FACTOR_COLUMN = "Second factor";
export const DEPARTMENT_COLUMN = "Department";

/** The reader's own row carries this instead of a control. */
export const YOUR_SESSION = "Your session";
export const YOUR_SESSION_WHY = "Sign out to end the session you are using.";

export const END_LABEL = "End session";
export const KEEP_LABEL = "Keep it";
export const END_SELECTED_LABEL = "End sessions";
export const KEEP_ALL_LABEL = "Keep them";
/** Said when more are selected than one request may carry. A bound, not a count of anything. */
export const TOO_MANY = `At most ${String(MOST_ENDED_AT_ONCE)} at once.`;
/** Said in the bulk confirmation about selected rows that are not ended. */
export const LEFT_AS_THEY_ARE = "Left as they are, because they cannot be ended from here:";
/** The consequence when the API sent no sentence of its own. */
export const ENDING_FALLBACK = "The next request made with the session is refused. No access is taken away.";
export const NOT_ENDED = "The session was not ended";
export const NOT_ENDED_SEVERAL = "The sessions were not ended";

type Pending =
  | { readonly kind: "one"; readonly row: SessionRow }
  | {
      readonly kind: "several";
      readonly rows: readonly SessionRow[];
      readonly skipped: readonly SessionRow[];
      readonly clear: () => void;
    };

export function SessionsPage() {
  // Asked again under a new version after a write, so the list shows what the database holds.
  const [version, setVersion] = useState(0);
  const [told, setTold] = useState<readonly string[]>([]);
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const listing = useListing<SessionRow>(SESSIONS_API_PATH, { choices: SESSION_FILTERS, version });
  const page = useMemo(() => readSessionsPage(listing.body), [listing.body]);
  const rows = page.sessions;

  // The Person filter's options are principal ids from rows drawn; they are shown by name, from
  // every row drawn so far, so an option does not turn into an id once a filter hides its row.
  const [names, setNames] = useState<ReadonlyMap<string, string>>(new Map());
  useEffect(() => {
    setNames((known) => {
      if (rows.every((row) => known.get(row.principal_id) === row.display_name)) {
        return known;
      }
      const next = new Map(known);
      for (const row of rows) {
        next.set(row.principal_id, row.display_name);
      }
      return next;
    });
  }, [rows]);
  const choices: readonly FilterChoice<SessionRow>[] = SESSION_FILTERS.map((choice) =>
    choice.column === "principal_id" ? { ...choice, describe: (value: string) => names.get(value) ?? value } : choice,
  );

  function done(sentences: readonly string[]): void {
    setPending(null);
    setFailure(null);
    setTold(sentences);
    setVersion((count) => count + 1);
  }

  function cancel(): void {
    setPending(null);
    setFailure(null);
  }

  function endOne(row: SessionRow): void {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(END_SESSION_API_PATH, { method: "POST", body: endingBody(row) });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      done([endedSentence(row, readEndedAt(result.data))]);
    })();
  }

  function endSeveral(chosen: readonly SessionRow[], clear: () => void): void {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(END_SESSIONS_API_PATH, { method: "POST", body: endingsBody(chosen) });
      setBusy(false);
      if (!result.ok) {
        setFailure(result.failure);
        return;
      }
      clear();
      const byId = new Map(chosen.map((one) => [one.session_id, one]));
      done(readOutcomes(result.data).map((one) => outcomeLine(byId.get(one.session_id), one)));
    })();
  }

  const consequence = page.ending === "" ? ENDING_FALLBACK : page.ending;

  const columns: readonly EntityColumn<SessionRow>[] = [
    {
      id: "person",
      header: PERSON_COLUMN,
      hideable: false,
      cell: (row) => (
        <span className="flex min-w-[10rem] flex-col gap-0.5">
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-ink">{row.display_name}</span>
            {row.yours ? (
              <Chip tone="brand" title={YOUR_SESSION_WHY}>
                {YOUR_SESSION}
              </Chip>
            ) : null}
          </span>
          {row.department === null ? null : <span className="text-[12px] text-dim">{row.department}</span>}
        </span>
      ),
      text: (row) => row.display_name,
    },
    {
      id: "signed_in",
      header: SIGNED_IN_COLUMN,
      cell: (row) => <span className="tabular-nums">{when(row.signed_in_at)}</span>,
      text: (row) => when(row.signed_in_at),
    },
    {
      id: "ends_by",
      header: ENDS_BY_COLUMN,
      cell: (row) => <span className="tabular-nums">{when(row.lapses_at)}</span>,
      text: (row) => when(row.lapses_at),
    },
    {
      id: "second_factor",
      header: SECOND_FACTOR_COLUMN,
      cell: factorWords,
      text: factorWords,
    },
    {
      id: "department",
      header: DEPARTMENT_COLUMN,
      hidden: true,
      cell: (row) => row.department ?? null,
      text: (row) => row.department ?? "",
    },
  ];

  return (
    <>
      <ListPage
        crumbs={[{ label: PEOPLE_AND_ACCESS, to: "/people" }, { label: SESSIONS_HEADING }]}
        title={SESSIONS_HEADING}
        lede={SESSIONS_LEDE}
        notice={
          told.length === 0 ? null : (
            <div role="status" className="flex flex-col gap-1">
              {told.map((sentence, index) => (
                <Note key={`${String(index)} ${sentence}`}>{sentence}</Note>
              ))}
            </div>
          )
        }
        listing={listing}
        rows={rows}
        filtersLabel={FILTERS_LABEL}
        choices={choices}
        sorts={SESSION_SORTS}
        searchHint={SEARCH_HINT}
        caption={SESSIONS_LIST_LABEL}
        columns={columns}
        rowId={(row) => row.session_id}
        rowLabel={(row) => row.display_name}
        rowActions={(row) =>
          tickable(row) ? (
            <Button
              variant="outline"
              size="sm"
              className="min-h-11 whitespace-nowrap sm:min-h-8"
              aria-label={`${END_LABEL}: ${row.display_name}`}
              disabled={busy}
              onClick={() => {
                setTold([]);
                setFailure(null);
                setPending({ kind: "one", row });
              }}
            >
              {END_LABEL}
            </Button>
          ) : null
        }
        bulkActions={(selected, clear) => {
          const endable = selected.filter(tickable);
          const tooMany = endable.length > MOST_ENDED_AT_ONCE;
          return (
            <>
              {tooMany ? <span className="text-[12.5px] text-dim">{TOO_MANY}</span> : null}
              <Button
                size="sm"
                variant="outline"
                disabled={busy || endable.length === 0 || tooMany}
                onClick={() => {
                  setTold([]);
                  setFailure(null);
                  setPending({ kind: "several", rows: endable, skipped: selected.filter((row) => !tickable(row)), clear });
                }}
              >
                {END_SELECTED_LABEL}
              </Button>
            </>
          );
        }}
        exportName="sessions"
        loading={LOADING_SESSIONS}
        emptyTitle={NO_SESSIONS}
        emptyDescription={page.appears === "" ? APPEARS_FALLBACK : page.appears}
        emptyIcon={<MonitorSmartphone aria-hidden />}
        footer={page.truncated ? <Note>{MORE_SESSIONS}</Note> : null}
      />
      {pending?.kind === "one" ? (
        <ConfirmDialog
          open
          question={endQuestion(pending.row)}
          consequence={consequence}
          details={failure === null ? undefined : <FailureNotice failure={failure} title={NOT_ENDED} />}
          confirmLabel={END_LABEL}
          cancelLabel={KEEP_LABEL}
          busy={busy}
          onConfirm={() => {
            endOne(pending.row);
          }}
          onCancel={cancel}
        />
      ) : null}
      {pending?.kind === "several" ? (
        <ConfirmDialog
          open
          question={END_SELECTED_QUESTION}
          consequence={consequence}
          details={
            <div className="flex min-w-0 flex-col gap-2">
              <ul className="m-0 flex list-disc flex-col gap-1 pl-5">
                {pending.rows.map((one) => (
                  <li key={one.session_id}>{endingLine(one)}</li>
                ))}
              </ul>
              {pending.skipped.length === 0 ? null : (
                <p className="m-0 text-[12.5px] text-dim">
                  {LEFT_AS_THEY_ARE} {pending.skipped.map((one) => one.display_name).join(", ")}.
                </p>
              )}
              {failure === null ? null : <FailureNotice failure={failure} title={NOT_ENDED_SEVERAL} />}
            </div>
          }
          confirmLabel={END_SELECTED_LABEL}
          cancelLabel={KEEP_ALL_LABEL}
          busy={busy}
          onConfirm={() => {
            endSeveral(pending.rows, pending.clear);
          }}
          onCancel={cancel}
        />
      ) : null}
    </>
  );
}
