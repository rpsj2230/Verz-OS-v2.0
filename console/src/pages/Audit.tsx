/**
 * Audit: the ledger, as far as this reader may read it, newest first and narrowable.
 *
 * `docs/screens.html` puts Audit last in the Govern section of the company console, and its
 * overview draws the Activity card this screen is the whole of: a time, who acted, and a sentence
 * saying what they did to what. The design gives the ledger no screen of its own, so the layout is
 * that card's, as a table, under the filter bar every screen in the design carries. The
 * `brain.console.auditor` history of one subject opens beside it, because "who gave her that, and
 * who took it away" is the question an auditor brings.
 *
 * **Nothing here decides who may see an entry.** The API answers from `brain.audit.view.AuditView`
 * and this page renders what came back. An entry the reader may not read is not on the page, and
 * the page says once, in words, that it would not be, without a number anywhere. See
 * `auditQuery.A_FILTER_OFFERS_WHAT_THE_ANSWER_CARRIED` for what the filters offer.
 *
 * **Four states and four sentences.** Loading, nothing to show, the Brain not reachable, and the
 * API refusing, which `docs/admin-console.md` requires to be different sentences. A refusal is the
 * API's own words: a 404 here means this reader may not open the screen, and saying so would be
 * the console explaining a refusal it cannot tell from an absence.
 *
 * **More entries are fetched, not paged.** "Show older entries" asks for the next page from the
 * cursor and appends it, and disappears when the API sends no cursor. A page may come back short
 * with a cursor when the server stopped reading, and the button is still offered, because the
 * cursor is the only statement about whether there is more.
 *
 * Task ids: M27.7.13
 */

import { useCallback, useMemo, useState, type ChangeEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { request } from "../api/client";
import type { ApiFailure } from "../api/errors";
import { useResource } from "../api/useResource";
import { Notice } from "../ui/Notice";
import {
  ADDRESS_PARAMETERS,
  ORDER_LABELS,
  ORDERS,
  PERIOD_LABELS,
  PERIODS,
  auditApiPath,
  filtersFrom,
  historyAddress,
  historyApiPath,
  offeredActors,
  phraseFor,
  readHistory,
  readLedgerPage,
  subjectFrom,
  subjectLabel,
  when,
  withFilter,
  type AuditFilters,
  type AuditRow,
  type LedgerPage,
} from "./auditQuery";
import { SOMETHING_DID_NOT_WORK } from "./Overview";

export const AUDIT_HEADING = "Audit";

/** Where the screen sits, in the design's own crumb. */
export const AUDIT_CRUMB = "Govern › Audit";

export const AUDIT_LEDE =
  "Who changed what anybody may do, and when: grants, refusals, leash changes, sign-in links " +
  "and sessions ended. Open a subject to read every change to what it may do.";

/** Said once, under the filters, and never as a number. */
export const WITHHELD_ENTRIES_ARE_NOT_LISTED =
  "An entry you may not read is not listed here, and nothing on this page says whether there " +
  "are any. The filters offer the actions and kinds the product records and the people on the " +
  "entries shown.";

/** The four states. */
export const READING_THE_LEDGER = "Reading the ledger.";
export const NO_ENTRIES = "There are no entries to show for these filters.";
export const THE_BRAIN_COULD_NOT_BE_REACHED = "The Brain could not be reached";

/** The end of the list, which is a fact about this reader's view and not about the ledger. */
export const NO_MORE_ENTRIES = "There are no further entries to show for these filters.";

/** One subject's history. */
export const NO_PERMISSION_CHANGES = "There are no permission changes to show for this subject.";
export const HISTORY_FILLED_A_PAGE =
  "This history filled a whole page, so earlier changes are not shown. Narrow the ledger by " +
  "period to read them.";

/** The accessible names. */
export const ENTRIES_LABEL = "Audit entries";
export const HISTORY_LABEL = "Permission history";
export const FILTERS_LABEL = "Narrow the ledger";

/** Everything, when a filter is not chosen. */
export const ALL_ACTIONS = "All actions";
export const ALL_KINDS = "All kinds";
export const EVERYONE = "Everyone";

/** The words over one failure. Unreachable and refused are two different sentences. */
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

function Details({ details }: { readonly details: Readonly<Record<string, string>> }) {
  const entries = Object.entries(details);
  if (entries.length === 0) {
    return null;
  }
  return (
    <ul className="roster">
      {entries.map(([name, value]) => (
        <li key={name}>
          <code>{name}</code> {value}
        </li>
      ))}
    </ul>
  );
}

function Filters({
  filters,
  page,
  search,
}: {
  readonly filters: AuditFilters;
  readonly page: LedgerPage;
  readonly search: URLSearchParams;
}) {
  const navigate = useNavigate();
  const choose = useCallback(
    (name: string) => (event: ChangeEvent<HTMLSelectElement>) => {
      navigate(withFilter(search, name, event.target.value));
    },
    [navigate, search],
  );
  const actions = page.actions.includes(filters.action) || filters.action === ""
    ? page.actions
    : [filters.action, ...page.actions];
  const kinds = page.kinds.includes(filters.kind) || filters.kind === ""
    ? page.kinds
    : [filters.kind, ...page.kinds];

  return (
    <form className="form" aria-label={FILTERS_LABEL} onSubmit={(event) => event.preventDefault()}>
      <label className="control-label">
        Action{" "}
        <select
          className="form-control"
          value={filters.action}
          onChange={choose(ADDRESS_PARAMETERS.action)}
        >
          <option value="">{ALL_ACTIONS}</option>
          {actions.map((one) => (
            <option key={one} value={one}>
              {one}
            </option>
          ))}
        </select>
      </label>
      <label className="control-label">
        About{" "}
        <select
          className="form-control"
          value={filters.kind}
          onChange={choose(ADDRESS_PARAMETERS.kind)}
        >
          <option value="">{ALL_KINDS}</option>
          {kinds.map((one) => (
            <option key={one} value={one}>
              {one}
            </option>
          ))}
        </select>
      </label>
      <label className="control-label">
        Who{" "}
        <select
          className="form-control"
          value={filters.actor}
          onChange={choose(ADDRESS_PARAMETERS.actor)}
        >
          <option value="">{EVERYONE}</option>
          {offeredActors(page, filters.actor).map((one) => (
            <option key={one} value={one}>
              {one}
            </option>
          ))}
        </select>
      </label>
      <label className="control-label">
        When{" "}
        <select
          className="form-control"
          value={filters.period}
          onChange={choose(ADDRESS_PARAMETERS.period)}
        >
          {PERIODS.map((one) => (
            <option key={one} value={one}>
              {PERIOD_LABELS[one]}
            </option>
          ))}
        </select>
      </label>
      <label className="control-label">
        Order{" "}
        <select
          className="form-control"
          value={filters.order}
          onChange={choose(ADDRESS_PARAMETERS.order)}
        >
          {ORDERS.map((one) => (
            <option key={one} value={one}>
              {ORDER_LABELS[one]}
            </option>
          ))}
        </select>
      </label>
    </form>
  );
}

function Rows({
  rows,
  search,
}: {
  readonly rows: readonly AuditRow[];
  readonly search: URLSearchParams;
}) {
  return (
    <div className="grid__scroll">
      <table className="grid__table" aria-label={ENTRIES_LABEL}>
        <thead>
          <tr>
            <th scope="col">When</th>
            <th scope="col">Who</th>
            <th scope="col">What</th>
            <th scope="col">About</th>
            <th scope="col">Details</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.at}-${row.action}-${row.subject_kind}-${row.subject_id}-${row.actor_id}`}>
              <td>{when(row.at)}</td>
              <td>
                <Link to={withFilter(search, ADDRESS_PARAMETERS.actor, row.actor_id)}>
                  {row.actor_id}
                </Link>
              </td>
              <td>{phraseFor(row.action)}</td>
              <td>
                <Link to={historyAddress(search, row.subject_kind, row.subject_id)}>
                  {subjectLabel(row.subject_kind, row.subject_id)}
                </Link>
              </td>
              <td>
                <Details details={row.details} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * The ledger for one set of filters. Keyed by them, so a change starts again from the first page
 * rather than appending a different question's answers to the last one's.
 */
function Ledger({ filters, search }: { readonly filters: AuditFilters; readonly search: URLSearchParams }) {
  // The instant the period is measured from is fixed when the filters are, so fetching more does
  // not move the window under the pages already shown.
  const now = useMemo(() => new Date(), []);
  const first = useResource<unknown>(auditApiPath(filters, now, null));
  const [more, setMore] = useState<readonly LedgerPage[]>([]);
  const [fetching, setFetching] = useState(false);
  const [moreFailure, setMoreFailure] = useState<ApiFailure | null>(null);

  const firstPage = readLedgerPage(first.data);
  const pages = [firstPage, ...more];
  const last = pages[pages.length - 1] ?? firstPage;
  const rows = pages.flatMap((one) => one.rows);

  const fetchMore = useCallback(() => {
    if (last.nextCursor === null) {
      return;
    }
    setFetching(true);
    void (async () => {
      const result = await request<unknown>(auditApiPath(filters, now, last.nextCursor));
      setFetching(false);
      if (!result.ok) {
        setMoreFailure(result.failure);
        return;
      }
      setMoreFailure(null);
      setMore((earlier) => [...earlier, readLedgerPage(result.data)]);
    })();
  }, [filters, now, last.nextCursor]);

  if (first.failure) {
    return <Failure failure={first.failure} />;
  }
  if (first.busy) {
    return (
      <p className="note" role="status">
        {READING_THE_LEDGER}
      </p>
    );
  }

  return (
    <>
      <Filters filters={filters} page={firstPage} search={search} />
      <section className="card">
        <h2>Entries</h2>
        {rows.length === 0 ? <p className="note">{NO_ENTRIES}</p> : <Rows rows={rows} search={search} />}
        {moreFailure === null ? null : <Failure failure={moreFailure} />}
        {last.nextCursor === null ? (
          rows.length === 0 ? null : <p className="note">{NO_MORE_ENTRIES}</p>
        ) : (
          <button type="button" className="button" onClick={fetchMore} disabled={fetching}>
            {filters.order === "newest" ? "Show older entries" : "Show newer entries"}
          </button>
        )}
      </section>
    </>
  );
}

function History({
  kind,
  id,
  search,
}: {
  readonly kind: string;
  readonly id: string;
  readonly search: URLSearchParams;
}) {
  const answer = useResource<unknown>(historyApiPath(kind, id));
  const history = readHistory(answer.data);

  return (
    <section className="card" aria-label={HISTORY_LABEL}>
      <h2>Permission history of {subjectLabel(kind, id)}</h2>
      <p>
        <Link to={withFilter(search, ADDRESS_PARAMETERS.subject, "")}>Close this history</Link>
      </p>
      {answer.failure ? <Failure failure={answer.failure} /> : null}
      {answer.busy ? (
        <p className="note" role="status">
          {READING_THE_LEDGER}
        </p>
      ) : null}
      {!answer.busy && !answer.failure && history.events.length === 0 ? (
        <p className="note">{NO_PERMISSION_CHANGES}</p>
      ) : null}
      {history.events.length === 0 ? null : (
        <div className="grid__scroll">
          <table className="grid__table">
            <thead>
              <tr>
                <th scope="col">When</th>
                <th scope="col">Who</th>
                <th scope="col">What</th>
                <th scope="col">Details</th>
              </tr>
            </thead>
            <tbody>
              {history.events.map((event) => (
                <tr key={`${event.at}-${event.action}-${event.actor_id}`}>
                  <td>{when(event.at)}</td>
                  <td>{event.actor_id}</td>
                  <td>{phraseFor(event.action)}</td>
                  <td>
                    <Details details={event.details} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {history.full ? <p className="note">{HISTORY_FILLED_A_PAGE}</p> : null}
    </section>
  );
}

export function Audit() {
  const [search] = useSearchParams();
  const filters = filtersFrom(search);
  const subject = subjectFrom(search);
  // The ledger is keyed by its filters and not by the open subject, so opening a history does
  // not throw away the pages already fetched beneath it.
  const ledgerKey = [filters.action, filters.kind, filters.actor, filters.period, filters.order].join(
    "|",
  );

  return (
    <article className="page">
      <p className="note">{AUDIT_CRUMB}</p>
      <h1>{AUDIT_HEADING}</h1>
      <p className="lede">{AUDIT_LEDE}</p>
      <p className="note">{WITHHELD_ENTRIES_ARE_NOT_LISTED}</p>
      {subject === null ? null : <History kind={subject.kind} id={subject.id} search={search} />}
      <Ledger key={ledgerKey} filters={filters} search={search} />
    </article>
  );
}
