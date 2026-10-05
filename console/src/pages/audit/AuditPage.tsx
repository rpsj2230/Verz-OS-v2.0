/**
 * The Audit log on the shared page kit: every entry this reader may read, newest first, narrowed by
 * what happened, what it was about, who did it and when.
 *
 * **A row is a sentence a person can read.** Who by name, what by the change the entry records, and
 * what it was about by name or kind, which opens that subject's page with everything recorded about
 * it (`AuditSubjectPage.tsx`). The old table printed principal ids and a fragment per action ("placed
 * or lifted"), which the owner could not read; see `auditWords.ts`.
 *
 * **Nothing here decides who may see an entry.** The API answers from `brain.audit.view.AuditView`
 * and this page draws what came back, with no count anywhere. The filters offer the product's own
 * vocabulary and the people on the rows already shown, for
 * `auditQuery.A_FILTER_OFFERS_WHAT_THE_ANSWER_CARRIED`'s reason, and the people are offered by name.
 *
 * **The address is the state**, as it was: the filters and the order are query parameters, so a
 * colleague can be sent the view, and the back button undoes a filter. An old link that opened a
 * subject's history as `?subject=kind:id` is sent to that subject's page.
 *
 * **Verifying the ledger has its own page** (`VerifyPage.tsx`), reached from the header: it is a
 * check somebody runs, not something to read past on the way to the entries.
 *
 * Task ids: M27.7.13, M27.8.6, M27.16.1
 */

import { ScrollText, ShieldCheck, X } from "lucide-react";
import { useEffect, useId, useState, type ReactNode } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { EmptyState, FailureState, LoadingState, PageHeader } from "../../components/kit";
import { SEARCH_LABEL } from "../../components/ListControls";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import {
  ADDRESS_PARAMETERS,
  AUDIT_PATH,
  DEFAULT_FILTERS,
  filtersFrom,
  offeredActors,
  ORDER_LABELS,
  ORDERS,
  PERIOD_LABELS,
  PERIODS,
  subjectAddress,
  subjectFrom,
  withFilter,
  type AuditFilters,
  type LedgerPage,
} from "../auditQuery";
import { TRACE_PAGE_PATH } from "../traceQuery";
import { ACTION_LABELS, kindWords, NO_NAME } from "./auditWords";
import { LedgerTable } from "./LedgerTable";
import { useLedger } from "./useLedger";

export const AUDIT_HEADING = "Audit log";
export const AUDIT_LEDE = "Who changed what, and when. Open what an entry is about to read everything recorded about it.";

export const READING_THE_LEDGER = "Reading the ledger.";
export const ENTRIES_LABEL = "Audit entries";
export const FILTERS_LABEL = "Narrow the ledger";
export const VERIFY_LINK = "Verify the ledger";
export const TRACE_LINK = "Read a run's trace";
export const EXPORT_LINK = "Export the trail";
/** Where a whole-window export of the trail is taken, with its reason, on Import and export. */
export const EXPORT_ADDRESS = "/import-export";

export const ALL_ACTIONS = "Anything";
export const ALL_KINDS = "Anything";
export const EVERYONE = "Anybody";
export const WHAT_FILTER = "What";
export const ABOUT_FILTER = "About";
export const WHO_FILTER = "Who";
export const WHEN_FILTER = "When";
export const ORDER_FILTER = "Order";
export const RESET_FILTERS = "Clear the filters";

/** The empty states. The first is for the ledger as it opens; the second for a narrowed question. */
export const NO_ENTRIES = "No entries in this period";
export const NO_ENTRIES_MORE = "Entries appear here as people grant and remove access and change settings. Choose a longer period to read further back.";
export const NOTHING_MATCHES = "No entry matches these filters";
export const NOTHING_MATCHES_MORE = "Change a filter, or clear them to read the last seven days.";
export const ALL_TIME = "Read all time";

/** Whether the reader has narrowed the ledger beyond how it opens. The order narrows nothing. */
export function narrowed(filters: AuditFilters, defaults: AuditFilters = DEFAULT_FILTERS): boolean {
  return (
    filters.search.trim() !== "" ||
    filters.action !== "" ||
    filters.kind !== "" ||
    filters.actor !== "" ||
    filters.period !== defaults.period
  );
}

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

/** A chosen value kept offered, so a narrowed list that came back empty still says what it is set to. */
export function withChosen(values: readonly string[], chosen: string): readonly string[] {
  return chosen === "" || values.includes(chosen) ? values : [chosen, ...values];
}

/**
 * The ledger's controls: a search, what happened, what it was about, who, when and the order. On a
 * subject's own page the subject is fixed, so the About choice is left out and every address is the
 * subject's.
 */
export function Toolbar({
  filters,
  actions,
  kinds,
  actors,
  people,
  search,
  base = AUDIT_PATH,
  defaults = DEFAULT_FILTERS,
}: {
  readonly filters: AuditFilters;
  readonly actions: readonly string[];
  readonly kinds: readonly string[] | null;
  readonly actors: readonly string[];
  readonly people: Readonly<Record<string, string>>;
  readonly search: URLSearchParams;
  readonly base?: string | undefined;
  readonly defaults?: AuditFilters | undefined;
}) {
  const navigate = useNavigate();
  const searchId = useId();
  const choose = (name: string) => (value: string) => {
    navigate(withFilter(search, name, value, base));
  };
  return (
    <form
      role="search"
      aria-label={FILTERS_LABEL}
      className="flex min-w-0 flex-wrap items-center gap-2"
      onSubmit={(event) => {
        event.preventDefault();
      }}
    >
      <span className="relative flex w-full min-w-0 items-center sm:w-64">
        <label htmlFor={searchId} className="sr-only">
          {SEARCH_LABEL}
        </label>
        <Input
          id={searchId}
          type="search"
          className="h-11 sm:h-8"
          maxLength={120}
          placeholder="Search the entries"
          value={filters.search}
          onChange={(event) => {
            // Replaced rather than pushed, so the back button undoes a filter and not a keystroke.
            navigate(withFilter(search, ADDRESS_PARAMETERS.search, event.target.value, base), { replace: true });
          }}
        />
      </span>
      <Choice label={WHAT_FILTER} value={filters.action} onChange={choose(ADDRESS_PARAMETERS.action)}>
        <option value="">{ALL_ACTIONS}</option>
        {withChosen(actions, filters.action).map((one) => (
          <option key={one} value={one}>
            {ACTION_LABELS[one] ?? one}
          </option>
        ))}
      </Choice>
      {kinds === null ? null : (
        <Choice label={ABOUT_FILTER} value={filters.kind} onChange={choose(ADDRESS_PARAMETERS.kind)}>
          <option value="">{ALL_KINDS}</option>
          {withChosen(kinds, filters.kind).map((one) => (
            <option key={one} value={one}>
              {kindWords(one)}
            </option>
          ))}
        </Choice>
      )}
      <Choice label={WHO_FILTER} value={filters.actor} onChange={choose(ADDRESS_PARAMETERS.actor)}>
        <option value="">{EVERYONE}</option>
        {actors.map((one) => (
          <option key={one} value={one}>
            {people[one] ?? NO_NAME}
          </option>
        ))}
      </Choice>
      <Choice label={WHEN_FILTER} value={filters.period} onChange={choose(ADDRESS_PARAMETERS.period)}>
        {PERIODS.map((one) => (
          <option key={one} value={one}>
            {PERIOD_LABELS[one]}
          </option>
        ))}
      </Choice>
      <Choice label={ORDER_FILTER} value={filters.order} onChange={choose(ADDRESS_PARAMETERS.order)}>
        {ORDERS.map((one) => (
          <option key={one} value={one}>
            {ORDER_LABELS[one]}
          </option>
        ))}
      </Choice>
      {narrowed(filters, defaults) ? (
        <Button asChild variant="ghost" size="sm" className="min-h-11 text-ink no-underline sm:min-h-8">
          <Link to={base}>
            {RESET_FILTERS} <X aria-hidden />
          </Link>
        </Button>
      ) : null}
    </form>
  );
}

/**
 * The entries for the filters in the address. `useLedger` starts again from the first page when
 * they change; the toolbar stays drawn meanwhile, offering what the last answer carried, so the box
 * somebody is typing in is never taken away by the request their typing started.
 */
function Entries({ filters, search }: { readonly filters: AuditFilters; readonly search: URLSearchParams }) {
  const ledger = useLedger(filters);
  const [offers, setOffers] = useState<LedgerPage | null>(null);
  useEffect(() => {
    if (ledger.first !== null) {
      setOffers(ledger.first);
    }
  }, [ledger.first]);

  let body: ReactNode;
  if (ledger.failure !== null) {
    body = <FailureState failure={ledger.failure} />;
  } else if (ledger.busy) {
    body = <LoadingState label={READING_THE_LEDGER} />;
  } else if (ledger.rows.length === 0) {
    body = narrowed(filters) ? (
      <EmptyState
        title={NOTHING_MATCHES}
        description={NOTHING_MATCHES_MORE}
        action={
          <Button asChild variant="outline" className="text-ink no-underline">
            <Link to={AUDIT_PATH}>{RESET_FILTERS}</Link>
          </Button>
        }
      />
    ) : (
      <EmptyState
        title={NO_ENTRIES}
        description={NO_ENTRIES_MORE}
        icon={<ScrollText aria-hidden />}
        action={
          <Button asChild variant="outline" className="text-ink no-underline">
            <Link to={withFilter(search, ADDRESS_PARAMETERS.period, "all")}>{ALL_TIME}</Link>
          </Button>
        }
      />
    );
  } else {
    body = (
      <LedgerTable
        ledger={ledger}
        caption={ENTRIES_LABEL}
        exportName="audit-log"
        moreLabel={filters.order === "newest" ? "Show older entries" : "Show newer entries"}
        whoCell={(row, name) =>
          ledger.people[row.actor_id] === undefined ? (
            name
          ) : (
            <Link
              to={withFilter(search, ADDRESS_PARAMETERS.actor, row.actor_id)}
              title={`Only entries by ${name}`}
              className="text-ink underline-offset-4 hover:text-acc-text hover:underline"
            >
              {name}
            </Link>
          )
        }
      />
    );
  }

  return (
    <section aria-label={ENTRIES_LABEL} className="flex min-w-0 flex-col gap-3 rounded-md border border-line bg-panel p-3 sm:p-4">
      <Toolbar
        filters={filters}
        actions={offers?.actions ?? []}
        kinds={offers?.kinds ?? []}
        actors={offers === null ? withChosen([], filters.actor) : offeredActors(offers, filters.actor)}
        people={{ ...(offers?.people ?? {}), ...ledger.people }}
        search={search}
      />
      {body}
    </section>
  );
}

export function AuditPage() {
  const [search] = useSearchParams();
  const subject = subjectFrom(search);
  if (subject !== null) {
    return <Navigate replace to={subjectAddress(subject.kind, subject.id)} />;
  }
  const filters = filtersFrom(search);
  return (
    <div data-slot="list-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader
        crumbs={[{ label: AUDIT_HEADING }]}
        title={AUDIT_HEADING}
        lede={AUDIT_LEDE}
        actions={
          <>
            <Button asChild variant="outline" size="sm" className="min-h-11 text-ink no-underline sm:min-h-8">
              <Link to={TRACE_PAGE_PATH}>{TRACE_LINK}</Link>
            </Button>
            <Button asChild variant="outline" size="sm" className="min-h-11 text-ink no-underline sm:min-h-8">
              <Link to={EXPORT_ADDRESS}>{EXPORT_LINK}</Link>
            </Button>
          </>
        }
        primary={
          <Button asChild size="sm" className="min-h-11 no-underline sm:min-h-8">
            <Link to={`${AUDIT_PATH}/verify`}>
              <ShieldCheck aria-hidden /> {VERIFY_LINK}
            </Link>
          </Button>
        }
      />
      <Entries filters={filters} search={search} />
    </div>
  );
}
