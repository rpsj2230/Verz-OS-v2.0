/**
 * Logs, on the page kit: the application's warnings and errors, searched by event name, narrowed by
 * level and period, walked a page at a time, and exported whole.
 *
 * **The address is the state.** The level, the search, the period and the order are query
 * parameters of the console address (`logsQuery.ts`), so an administrator can send a colleague the
 * view they are looking at. The cursor is not, because it is a position in one reader's walk.
 *
 * **The export is the search's rows for the period, not the rows paged to** (M27.15.48). The button
 * asks `GET /logs/export` with the same level, search, window and order, which asks the screen's own
 * decision first, and saves the CSV it answers. The rows are the ones the screen would page through,
 * redacted the same way, and no count of anything is said; a period with more rows than one export
 * carries says only that.
 *
 * **Nothing here hides a value, and nothing here decides who may read.** The API redacted every row
 * on its way into the table and refuses a reader who may not read the log, in its own words.
 *
 * **What was removed.** The breadcrumb as text, the paragraph above the rows explaining redaction
 * (one line under the table now), the "What this screen cannot show" card, and the source position
 * as a default column (it is a column a reader turns on).
 *
 * Task ids: M27.8.14, M27.8.6, M27.15.48, M27.16.1
 */

import { Download } from "lucide-react";
import { useCallback, useId, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { request } from "../../api/client";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import {
  EmptyState,
  EntityTable,
  FailureState,
  LoadingState,
  Note,
  PageHeader,
  saveCsv,
  SectionCard,
  type EntityColumn,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import {
  ADDRESS_PARAMETERS,
  ALL_LEVELS,
  DEBUG_IS_NOT_KEPT,
  ENTRIES_LABEL,
  EXPORT_CUT_OFF,
  EXPORT_LOG,
  EXPORT_LOG_TITLE,
  EXPORT_NOT_SAVED,
  EXPORT_SAVED,
  FILTERS_LABEL,
  filtersFrom,
  INFO_IS_A_SAMPLE,
  keptFor,
  LEVEL_LABELS,
  LEVELS,
  logsApiPath,
  logsExportApiPath,
  LOGS_LABEL,
  LOGS_LEDE,
  MAX_SEARCH_CHARS,
  NAME_NOT_KEPT,
  NAME_NOT_KEPT_WHY,
  NO_ENTRIES,
  NO_ENTRIES_MORE,
  NO_MORE_ENTRIES,
  NO_VALUE_IS_KEPT,
  ORDER_LABELS,
  ORDERS,
  PERIOD_LABELS,
  PERIODS,
  READING_THE_LOG,
  readLogExport,
  readLogPage,
  repeated,
  SEARCH_LABEL,
  SHOW_NEWER,
  SHOW_OLDER,
  WORKER_OUTPUT_IS_NOT_KEPT,
  withFilter,
  type LogEntry,
  type LogFilters,
  type LogPage,
} from "../logsQuery";
import { at, Line, OPERATIONS, UNREADABLE } from "./parts";
import { LevelPill } from "./pills";

const SELECT =
  "h-11 min-w-0 max-w-full rounded-md border border-input bg-panel px-2.5 text-sm text-ink shadow-xs outline-hidden focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring sm:h-8";

function Choice({
  label,
  value,
  onChange,
  children,
}: {
  readonly label: string;
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly children: ReactNode;
}) {
  const id = useId();
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      <label htmlFor={id} className="text-[12.5px] whitespace-nowrap text-dim">
        {label}
      </label>
      <select
        id={id}
        className={SELECT}
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      >
        {children}
      </select>
    </span>
  );
}

function Filters({ filters, search }: { readonly filters: LogFilters; readonly search: URLSearchParams }) {
  const navigate = useNavigate();
  const searchId = useId();
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
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      <form role="search" aria-label={SEARCH_LABEL} className="flex min-w-0 items-center gap-2" onSubmit={submit}>
        <label htmlFor={searchId} className="text-[12.5px] whitespace-nowrap text-dim">
          Event name
        </label>
        <Input
          id={searchId}
          type="search"
          className="h-11 w-full min-w-0 sm:h-8 sm:w-56"
          maxLength={MAX_SEARCH_CHARS}
          value={typed}
          onChange={(event) => {
            setTyped(event.target.value);
          }}
        />
        <Button type="submit" variant="outline" size="sm" className="min-h-11 sm:min-h-8">
          Search
        </Button>
      </form>
      <form
        aria-label={FILTERS_LABEL}
        className="flex min-w-0 flex-wrap items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault();
        }}
      >
        <Choice
          label="Level"
          value={filters.level}
          onChange={(value) => {
            navigate(withFilter(search, ADDRESS_PARAMETERS.level, value));
          }}
        >
          <option value="">{ALL_LEVELS}</option>
          {LEVELS.map((one) => (
            <option key={one} value={one}>
              {LEVEL_LABELS[one]}
            </option>
          ))}
        </Choice>
        <Choice
          label="When"
          value={filters.period}
          onChange={(value) => {
            navigate(withFilter(search, ADDRESS_PARAMETERS.period, value));
          }}
        >
          {PERIODS.map((one) => (
            <option key={one} value={one}>
              {PERIOD_LABELS[one]}
            </option>
          ))}
        </Choice>
        <Choice
          label="Order"
          value={filters.order}
          onChange={(value) => {
            navigate(withFilter(search, ADDRESS_PARAMETERS.order, value));
          }}
        >
          {ORDERS.map((one) => (
            <option key={one} value={one}>
              {ORDER_LABELS[one]}
            </option>
          ))}
        </Choice>
      </form>
    </div>
  );
}

function Fields({ fields }: { readonly fields: Readonly<Record<string, string>> }) {
  const named = Object.entries(fields).sort(([a], [b]) => a.localeCompare(b));
  if (named.length === 0) {
    return null;
  }
  return (
    <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
      {named.map(([name, value]) => (
        <li key={name} className="text-[12px]">
          <span className="font-mono text-dim">{name}</span> {value}
        </li>
      ))}
    </ul>
  );
}

type Keyed = LogEntry & { readonly key: string };

const COLUMNS: readonly EntityColumn<Keyed>[] = [
  { id: "at", header: "When", hideable: false, cell: (row) => at(row.at), text: (row) => row.at },
  {
    id: "level",
    header: "Level",
    cell: (row) => <LevelPill level={row.level} />,
    text: (row) => row.level,
  },
  {
    id: "event",
    header: "Event",
    cell: (row) =>
      row.event === null ? (
        <span className="text-dim" title={NAME_NOT_KEPT_WHY}>
          {NAME_NOT_KEPT}
        </span>
      ) : (
        row.event
      ),
    text: (row) => row.event ?? "",
  },
  {
    id: "reference",
    header: "Reference",
    cell: (row) => (row.reference === null ? null : <code className="font-mono text-[12px]">{row.reference}</code>),
    text: (row) => row.reference ?? "",
  },
  {
    id: "exception",
    header: "Exception",
    cell: (row) => (row.error_type === null ? null : <code className="font-mono text-[12px]">{row.error_type}</code>),
    text: (row) => row.error_type ?? "",
  },
  { id: "repeated", header: "Repeated", cell: (row) => repeated(row.repeats), text: (row) => repeated(row.repeats) },
  { id: "fields", header: "Fields", cell: (row) => <Fields fields={row.fields} /> },
  {
    id: "origin",
    header: "Where",
    hidden: true,
    cell: (row) => (row.origin === null ? null : <code className="font-mono text-[12px]">{row.origin}</code>),
    text: (row) => row.origin ?? "",
  },
];

/** The rows for one set of filters. Keyed by them, so a change starts from the first page again. */
function Entries({ filters, now }: { readonly filters: LogFilters; readonly now: Date }) {
  const first = useResource<unknown>(logsApiPath(filters, now, null));
  const [more, setMore] = useState<readonly LogPage[]>([]);
  const [fetching, setFetching] = useState(false);
  const [moreFailure, setMoreFailure] = useState<ApiFailure | null>(null);

  const firstPage = readLogPage(first.data);
  const pages = firstPage === null ? [] : [firstPage, ...more];
  const last = pages[pages.length - 1] ?? null;
  // Each row keyed by its place in the walk: two identical warnings in one second are two rows.
  const entries: Keyed[] = pages.flatMap((one) => one.entries).map((one, index) => ({ ...one, key: String(index) }));

  const fetchMore = useCallback(() => {
    if (last === null || last.nextCursor === null) {
      return;
    }
    setFetching(true);
    void (async () => {
      const result = await request<unknown>(logsApiPath(filters, now, last.nextCursor));
      setFetching(false);
      if (!result.ok) {
        setMoreFailure(result.failure);
        return;
      }
      setMoreFailure(null);
      const page = readLogPage(result.data);
      if (page !== null) {
        setMore((earlier) => [...earlier, page]);
      }
    })();
  }, [filters, now, last]);

  if (first.failure !== null) {
    return <FailureState failure={first.failure} />;
  }
  if (first.busy) {
    return <LoadingState label={READING_THE_LOG} />;
  }
  if (firstPage === null || last === null) {
    return <p className="m-0 text-sm text-dim">{UNREADABLE}</p>;
  }
  return (
    <>
      {entries.length === 0 ? (
        <EmptyState title={NO_ENTRIES} description={NO_ENTRIES_MORE} />
      ) : (
        <EntityTable<Keyed>
          caption={ENTRIES_LABEL}
          columns={COLUMNS}
          rows={entries}
          rowId={(row) => row.key}
          rowLabel={(row) => row.event ?? NAME_NOT_KEPT}
        />
      )}
      {moreFailure === null ? null : <FailureState failure={moreFailure} />}
      {last.nextCursor === null ? (
        entries.length === 0 ? null : <Line>{NO_MORE_ENTRIES}</Line>
      ) : (
        <div>
          <Button variant="outline" className="min-h-11 sm:min-h-9" onClick={fetchMore} disabled={fetching}>
            {filters.order === "oldest" ? SHOW_NEWER : SHOW_OLDER}
          </Button>
        </div>
      )}
      <div className="flex flex-col gap-1">
        <Line>{NO_VALUE_IS_KEPT}</Line>
        {firstPage.debugIsNotKept ? <Line>{DEBUG_IS_NOT_KEPT}</Line> : null}
        {firstPage.infoIsASample ? <Line>{INFO_IS_A_SAMPLE}</Line> : null}
        {firstPage.workerOutputIsNotKept ? <Line>{WORKER_OUTPUT_IS_NOT_KEPT}</Line> : null}
        {firstPage.keptForDays > 0 ? <Line>{keptFor(firstPage.keptForDays)}</Line> : null}
      </div>
    </>
  );
}

function ExportButton({ filters, now, onDone }: { readonly filters: LogFilters; readonly now: Date; readonly onDone: (told: ReactNode) => void }) {
  const [busy, setBusy] = useState(false);
  const take = useCallback(() => {
    setBusy(true);
    void (async () => {
      const result = await request<unknown>(logsExportApiPath(filters, now));
      setBusy(false);
      if (!result.ok) {
        onDone(<FailureState failure={result.failure} />);
        return;
      }
      const taken = readLogExport(result.data);
      if (taken === null) {
        onDone(<Note>{UNREADABLE}</Note>);
        return;
      }
      const saved = saveCsv(taken.filename, taken.document);
      onDone(
        <div role="status" className="flex flex-col gap-1">
          <Note>{saved ? EXPORT_SAVED : EXPORT_NOT_SAVED}</Note>
          {taken.cutOff ? <Note kind="not-yet">{EXPORT_CUT_OFF}</Note> : null}
        </div>,
      );
    })();
  }, [filters, now, onDone]);
  return (
    <Button variant="outline" size="sm" className="min-h-11 sm:min-h-8" title={EXPORT_LOG_TITLE} disabled={busy} onClick={take}>
      <Download aria-hidden /> {EXPORT_LOG}
    </Button>
  );
}

export function LogsPage() {
  const [search] = useSearchParams();
  const filters = filtersFrom(search);
  const key = [filters.level, filters.event, filters.period, filters.order].join("|");
  // The end of the window is fixed when the filters are, so a page asked later reads the same window.
  // `key` is the dependency on purpose: a new question takes a new instant, a re-render does not.
  const now = useMemo(() => new Date(), [key]);
  const [told, setTold] = useState<ReactNode>(null);

  return (
    <div data-slot="ops-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader
        crumbs={[{ label: OPERATIONS }, { label: LOGS_LABEL }]}
        title={LOGS_LABEL}
        lede={LOGS_LEDE}
        actions={<ExportButton filters={filters} now={now} onDone={setTold} />}
      />
      {told}
      <SectionCard title="Rows" lede="Newest first unless you choose otherwise.">
        <div className="flex min-w-0 flex-col gap-3">
          <Filters key={`filters-${key}`} filters={filters} search={search} />
          <Entries key={key} filters={filters} now={now} />
        </div>
      </SectionCard>
    </div>
  );
}
