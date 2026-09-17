/**
 * Logs: the application's warnings and errors, readable without a shell on the server.
 *
 * Under Operate, after Errors. A search by event name, a level and a period, carried in the address;
 * a table of rows newest first; "Show older entries" from the cursor; and the sentences saying what the
 * log never keeps. Nothing here is a control, and nothing here hides a value: the API redacted every
 * row on its way into the table, and this page draws what it was sent.
 *
 * **Four states and four sentences.** Reading, nothing kept for this search, the Brain not reachable,
 * and the API refusing, which is shown in the API's own words: a reader who may not read the log is
 * told the screen is not theirs, and an empty table is never how that is said.
 *
 * Task ids: M27.8.14
 */

import { useCallback, useMemo, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { Notice } from "../ui/Notice";
import {
  ADDRESS_PARAMETERS,
  ALL_LEVELS,
  DEBUG_IS_NOT_KEPT,
  ENTRIES_LABEL,
  FILTERS_LABEL,
  INFO_IS_A_SAMPLE,
  LEVEL_LABELS,
  LEVELS,
  LOGS_CRUMB,
  LOGS_LABEL,
  LOGS_LEDE,
  MAX_SEARCH_CHARS,
  NAME_NOT_KEPT,
  NAME_NOT_KEPT_WHY,
  NO_ENTRIES,
  NO_MORE_ENTRIES,
  NO_VALUE_IS_KEPT,
  PERIOD_LABELS,
  PERIODS,
  READING_THE_LOG,
  SEARCH_LABEL,
  SHOW_OLDER,
  THE_BRAIN_COULD_NOT_BE_REACHED,
  UNREADABLE_ANSWER,
  WHAT_IS_NOT_HERE_HEADING,
  WORKER_OUTPUT_IS_NOT_KEPT,
  filtersFrom,
  keptFor,
  logsApiPath,
  readLogPage,
  repeated,
  withFilter,
  type Level,
  type LogEntry,
  type LogFilters,
  type LogPage,
} from "./logsQuery";
import { SOMETHING_DID_NOT_WORK } from "./Overview";
import { when } from "./sessionsQuery";

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

function Fields({ fields }: { readonly fields: Readonly<Record<string, string>> }) {
  const named = Object.entries(fields).sort(([a], [b]) => a.localeCompare(b));
  if (named.length === 0) {
    return null;
  }
  return (
    <ul className="roster">
      {named.map(([name, value]) => (
        <li key={name}>
          <code>{name}</code> {value}
        </li>
      ))}
    </ul>
  );
}

function Filters({ filters, search }: { readonly filters: LogFilters; readonly search: URLSearchParams }) {
  const navigate = useNavigate();
  const [typed, setTyped] = useState(filters.event);
  const submit = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      navigate(withFilter(search, ADDRESS_PARAMETERS.event, typed.trim()));
    },
    [navigate, search, typed],
  );

  // Two forms, because a choice beside a submit button reads as part of a write: the search is
  // submitted, and a level or a period is a narrowing that applies as soon as it is chosen.
  return (
    <>
      <form className="form" aria-label={SEARCH_LABEL} onSubmit={submit}>
        <label className="control-label">
          Event name{" "}
          <input
            className="form-control"
            type="search"
            maxLength={MAX_SEARCH_CHARS}
            value={typed}
            onChange={(event) => {
              setTyped(event.target.value);
            }}
          />
        </label>
        <button type="submit" className="button">
          Search
        </button>
      </form>
      <form className="form" aria-label={FILTERS_LABEL} onSubmit={(event) => event.preventDefault()}>
        <label className="control-label">
          Level{" "}
          <select
            className="form-control"
            value={filters.level}
            onChange={(event) => {
              navigate(withFilter(search, ADDRESS_PARAMETERS.level, event.target.value));
            }}
          >
            <option value="">{ALL_LEVELS}</option>
            {LEVELS.map((one) => (
              <option key={one} value={one}>
                {LEVEL_LABELS[one]}
              </option>
            ))}
          </select>
        </label>
        <label className="control-label">
          When{" "}
          <select
            className="form-control"
            value={filters.period}
            onChange={(event) => {
              navigate(withFilter(search, ADDRESS_PARAMETERS.period, event.target.value));
            }}
          >
            {PERIODS.map((one) => (
              <option key={one} value={one}>
                {PERIOD_LABELS[one]}
              </option>
            ))}
          </select>
        </label>
      </form>
    </>
  );
}

function Rows({ entries }: { readonly entries: readonly LogEntry[] }) {
  return (
    <div className="grid__scroll">
      <table className="grid__table" aria-label={ENTRIES_LABEL}>
        <thead>
          <tr>
            <th scope="col">When</th>
            <th scope="col">Level</th>
            <th scope="col">Event</th>
            <th scope="col">Where</th>
            <th scope="col">Reference</th>
            <th scope="col">Exception</th>
            <th scope="col">Repeated</th>
            <th scope="col">Fields</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((row, index) => (
            <tr key={`${row.at}-${row.origin ?? ""}-${String(index)}`}>
              <td>{when(row.at)}</td>
              <td>{LEVEL_LABELS[row.level as Level]}</td>
              <td>{row.event === null ? <span title={NAME_NOT_KEPT_WHY}>{NAME_NOT_KEPT}</span> : row.event}</td>
              <td>{row.origin === null ? "" : <code>{row.origin}</code>}</td>
              <td>{row.reference === null ? "" : <code>{row.reference}</code>}</td>
              <td>{row.error_type === null ? "" : <code>{row.error_type}</code>}</td>
              <td>{repeated(row.repeats)}</td>
              <td>
                <Fields fields={row.fields} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function NotHere({ page }: { readonly page: LogPage }) {
  return (
    <section className="card" aria-labelledby="logs-not-here">
      <h2 id="logs-not-here">{WHAT_IS_NOT_HERE_HEADING}</h2>
      {page.debugIsNotKept ? <p>{DEBUG_IS_NOT_KEPT}</p> : null}
      {page.infoIsASample ? <p>{INFO_IS_A_SAMPLE}</p> : null}
      {page.workerOutputIsNotKept ? <p>{WORKER_OUTPUT_IS_NOT_KEPT}</p> : null}
      {page.keptForDays > 0 ? <p>{keptFor(page.keptForDays)}</p> : null}
    </section>
  );
}

/** The rows for one set of filters. Keyed by them, so a change starts from the first page again. */
function Entries({ filters }: { readonly filters: LogFilters }) {
  const now = useMemo(() => new Date(), []);
  const first = useResource<unknown>(logsApiPath(filters, now, null));
  const [more, setMore] = useState<readonly LogPage[]>([]);
  const [fetching, setFetching] = useState(false);
  const [moreFailure, setMoreFailure] = useState<ApiFailure | null>(null);

  const firstPage = readLogPage(first.data);
  const pages = firstPage === null ? [] : [firstPage, ...more];
  const last = pages[pages.length - 1] ?? null;
  const entries = pages.flatMap((one) => one.entries);

  const fetchMore = useCallback(() => {
    if (last === null || last.nextCursor === null) {
      return;
    }
    setFetching(true);
    void (async () => {
      const result = await request<unknown>(logsApiPath(filters, now, last.nextCursor));
      setFetching(false);
      const page = result.ok ? readLogPage(result.data) : null;
      if (!result.ok) {
        setMoreFailure(result.failure);
        return;
      }
      setMoreFailure(null);
      if (page !== null) {
        setMore((earlier) => [...earlier, page]);
      }
    })();
  }, [filters, now, last]);

  if (first.busy) {
    return (
      <p className="note" role="status">
        {READING_THE_LOG}
      </p>
    );
  }
  if (first.failure) {
    return <Failure failure={first.failure} />;
  }
  if (firstPage === null || last === null) {
    return <p className="note">{UNREADABLE_ANSWER}</p>;
  }

  return (
    <>
      <section className="card">
        <h2>Rows</h2>
        {entries.length === 0 ? <p className="note">{NO_ENTRIES}</p> : <Rows entries={entries} />}
        {moreFailure === null ? null : <Failure failure={moreFailure} />}
        {last.nextCursor === null ? (
          entries.length === 0 ? null : <p className="note">{NO_MORE_ENTRIES}</p>
        ) : (
          <button type="button" className="button" onClick={fetchMore} disabled={fetching}>
            {SHOW_OLDER}
          </button>
        )}
      </section>
      <NotHere page={firstPage} />
    </>
  );
}

export function Logs() {
  const [search] = useSearchParams();
  const filters = filtersFrom(search);
  const key = [filters.level, filters.event, filters.period].join("|");

  return (
    <article className="page">
      <p className="note">{LOGS_CRUMB}</p>
      <h1>{LOGS_LABEL}</h1>
      <p className="lede">{LOGS_LEDE}</p>
      <p className="note">{NO_VALUE_IS_KEPT}</p>
      <Filters key={`filters-${key}`} filters={filters} search={search} />
      <Entries key={key} filters={filters} />
    </article>
  );
}
