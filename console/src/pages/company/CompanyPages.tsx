/**
 * The whole company, as a Super Admin reads it: everything in the install, all its activity, and
 * what it spent. Three tabs of one menu entry, each drawing one answer from `brain.company_routes`.
 *
 * **Every row, figure and filter value on these pages is the API's.** The department and person
 * filters are written into the page's own address and sent as query parameters, so the API narrows
 * after its own visibility check and the page draws what came back; nothing is filtered, counted
 * or totalled here (`companyQuery.ts`). **A control appears only where the answer offers it**: a
 * filter with no values offered is not drawn, and a figure the API withheld is said to be withheld
 * rather than drawn as nought.
 *
 * Task ids: M33.1.1.1, M33.1.1.2, M33.1.1.3
 */

import { useId, useState, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useResource } from "../../api/useResource";
import {
  EmptyState,
  EntityTable,
  FailureState,
  LoadingState,
  PageHeader,
  SectionCard,
  StatCard,
  StatsStrip,
  type EntityColumn,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { actorWords, subjectWords, whatWords } from "../audit/auditWords";
import { when, type AuditRow } from "../auditQuery";
import {
  ACTIVITY_PATH,
  activityApiPath,
  CONSUMPTION_WINDOWS,
  consumptionApiPath,
  DEFAULT_WINDOW,
  ESTATE_PATH,
  estateApiPath,
  keepChosen,
  KIND_WORDS,
  narrowedTo,
  ORDER_WORDS,
  ORDERS,
  PARAMETERS,
  readActivity,
  readConsumption,
  readEstate,
  type EstateItem,
} from "../companyQuery";
import { moneyWords } from "../spendQuery";

export const COMPANY_CRUMB = "Whole company";

export const ESTATE_HEADING = "Everything";
export const ESTATE_LEDE = "Every agent, skill, document and connector you may see, by department and by person.";
export const ACTIVITY_HEADING = "Activity";
export const ACTIVITY_LEDE = "Everything people did that you may read, newest first, by department and by person.";
export const CONSUMPTION_HEADING = "Consumption";
export const CONSUMPTION_LEDE = "What the company spent, and how it divides between departments.";

export const DEPARTMENT_FILTER = "Department";
export const PERSON_FILTER = "Person";
export const KIND_FILTER = "Kind";
export const WINDOW_FILTER = "Period";
export const ORDER_FILTER = "Order";
export const SEARCH_LABEL = "Search the activity";
export const EVERY_DEPARTMENT = "Every department";
export const EVERYBODY = "Everybody";
export const EVERY_KIND = "Everything";
export const FILTERS_LABEL = "Narrow the company view";
export const CLEAR_FILTERS = "Clear the filters";

export const LOADING_ESTATE = "Reading what the company holds.";
export const LOADING_ACTIVITY = "Reading the activity.";
export const LOADING_CONSUMPTION = "Reading what the company spent.";

export const NOTHING_HERE = "Nothing to show";
export const NOTHING_HERE_MORE = "Nothing you may see matches these filters.";
export const NO_ACTIVITY = "No activity to show";
export const NO_ACTIVITY_MORE = "Nothing you may read matches these filters.";
export const OLDER = "Show older entries";
export const NEWEST = "Back to the newest";

export const WITHHELD = "Not shown to you";
export const WITHHELD_MORE =
  "The company's spend is everybody's, and your budget permission covers less than everybody, so no figure is shown rather than a partial one.";
export const SPENT_LABEL = "Spent";
export const FIGURES_LABEL = "Company consumption";
export const BY_DEPARTMENT = "By department";
export const NOTHING_SPENT = "Nothing was spent in this period.";
export const INCOMPLETE = "More runs were recorded in this period than one reading takes, so this figure leaves out the oldest of them.";
export const NO_CEILING = "No company budget is set, so there is no ceiling to measure this against.";

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

/**
 * The department and person filters, each drawn only when the answer offered a value for it. A
 * chosen value is kept offered so a narrowed answer that came back empty still says what it is set
 * to.
 */
function Filters({
  base,
  departments,
  people,
  names,
  kinds,
  searchable = false,
  children,
}: {
  readonly base: string;
  readonly departments: readonly string[];
  readonly people: readonly string[];
  readonly names: Readonly<Record<string, string>>;
  readonly kinds?: readonly string[] | undefined;
  /** The activity route takes a search and an order; the estate's takes neither. */
  readonly searchable?: boolean | undefined;
  readonly children?: ReactNode | undefined;
}) {
  const [search] = useSearchParams();
  const navigate = useNavigate();
  const department = search.get(PARAMETERS.department) ?? "";
  const person = search.get(PARAMETERS.person) ?? "";
  const kind = search.get(PARAMETERS.kind) ?? "";
  const words = search.get(PARAMETERS.search) ?? "";
  const order = search.get(PARAMETERS.order) ?? "";
  const searchId = useId();
  const choose = (name: string) => (value: string) => {
    navigate(narrowedTo(base, search, name, value));
  };
  const offeredDepartments = keepChosen(departments, department);
  const offeredPeople = keepChosen(people, person);
  const narrowed = department !== "" || person !== "" || kind !== "" || words !== "" || order !== "";
  return (
    <form
      role="search"
      aria-label={FILTERS_LABEL}
      className="flex min-w-0 flex-wrap items-center gap-2 empty:hidden"
      onSubmit={(event) => {
        event.preventDefault();
      }}
    >
      {searchable ? (
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
            value={words}
            onChange={(event) => {
              // Replaced rather than pushed, so the back button undoes a filter and not a keystroke.
              navigate(narrowedTo(base, search, PARAMETERS.search, event.target.value), { replace: true });
            }}
          />
        </span>
      ) : null}
      {kinds === undefined ? null : (
        <Choice label={KIND_FILTER} value={kind} onChange={choose(PARAMETERS.kind)}>
          <option value="">{EVERY_KIND}</option>
          {kinds.map((one) => (
            <option key={one} value={one}>
              {KIND_WORDS[one] ?? one}
            </option>
          ))}
        </Choice>
      )}
      {offeredDepartments.length === 0 ? null : (
        <Choice label={DEPARTMENT_FILTER} value={department} onChange={choose(PARAMETERS.department)}>
          <option value="">{EVERY_DEPARTMENT}</option>
          {offeredDepartments.map((one) => (
            <option key={one} value={one}>
              {one}
            </option>
          ))}
        </Choice>
      )}
      {offeredPeople.length === 0 ? null : (
        <Choice label={PERSON_FILTER} value={person} onChange={choose(PARAMETERS.person)}>
          <option value="">{EVERYBODY}</option>
          {offeredPeople.map((one) => (
            <option key={one} value={one}>
              {names[one] ?? one}
            </option>
          ))}
        </Choice>
      )}
      {searchable ? (
        <Choice label={ORDER_FILTER} value={order === "" ? "newest" : order} onChange={choose(PARAMETERS.order)}>
          {ORDERS.map((one) => (
            <option key={one} value={one}>
              {ORDER_WORDS[one]}
            </option>
          ))}
        </Choice>
      ) : null}
      {children}
      {narrowed ? (
        <Button asChild variant="ghost" size="sm" className="min-h-11 text-ink no-underline sm:min-h-8">
          <Link to={base}>{CLEAR_FILTERS}</Link>
        </Button>
      ) : null}
    </form>
  );
}

function Frame({ title, lede, children }: { readonly title: string; readonly lede: string; readonly children: ReactNode }) {
  return (
    <div data-slot="company-page" className="flex min-w-0 flex-col gap-4">
      <PageHeader crumbs={[{ label: COMPANY_CRUMB }, { label: title }]} title={title} lede={lede} />
      {children}
    </div>
  );
}

// ------------------------------------------------------------------------------ the estate

const ESTATE_COLUMNS: readonly EntityColumn<EstateItem>[] = [
  { id: "label", header: "Name", hideable: false, cell: (row) => row.label, text: (row) => row.label },
  { id: "kind", header: "Kind", cell: (row) => KIND_WORDS[row.kind] ?? row.kind, text: (row) => row.kind },
];

export function EstatePage() {
  const [search] = useSearchParams();
  const answer = useResource<unknown>(estateApiPath(search));
  const body = answer.data === null ? null : readEstate(answer.data);

  let content: ReactNode;
  if (answer.failure !== null) {
    content = <FailureState failure={answer.failure} />;
  } else if (answer.busy || body === null) {
    content = <LoadingState label={LOADING_ESTATE} />;
  } else if (body.items.length === 0) {
    content = <EmptyState title={NOTHING_HERE} description={NOTHING_HERE_MORE} />;
  } else {
    content = (
      <EntityTable
        caption={ESTATE_HEADING}
        columns={ESTATE_COLUMNS}
        rows={body.items}
        rowId={(row) => `${row.kind}:${row.item_id}`}
        rowLabel={(row) => row.label}
        exportName="company-estate"
      />
    );
  }
  return (
    <Frame title={ESTATE_HEADING} lede={ESTATE_LEDE}>
      <SectionCard title={ESTATE_HEADING}>
        <div className="flex min-w-0 flex-col gap-3">
          {body === null ? null : (
            <Filters base={ESTATE_PATH} departments={body.departments} people={body.people} names={body.names ?? {}} kinds={body.kinds} />
          )}
          {content}
        </div>
      </SectionCard>
    </Frame>
  );
}

// ---------------------------------------------------------------------------- the activity

export function ActivityPage() {
  const [search] = useSearchParams();
  const [cursor, setCursor] = useState("");
  const filters = search.toString();
  const [heldFor, setHeldFor] = useState(filters);
  if (heldFor !== filters) {
    // A new question starts from the newest entry again.
    setHeldFor(filters);
    setCursor("");
  }
  const answer = useResource<unknown>(activityApiPath(search, cursor));
  const body = answer.data === null ? null : readActivity(answer.data);
  const people = body?.people ?? {};

  const columns: readonly EntityColumn<AuditRow>[] = [
    { id: "at", header: "When", hideable: false, cell: (row) => when(row.at), text: (row) => row.at },
    { id: "who", header: "Who", cell: (row) => actorWords(row.actor_id, people, row.details), text: (row) => row.actor_id },
    { id: "what", header: "What", cell: (row) => whatWords(row.action, row.details), text: (row) => row.action },
    {
      id: "about",
      header: "About",
      cell: (row) => subjectWords(row.subject_kind, row.subject_id, people),
      text: (row) => `${row.subject_kind}:${row.subject_id}`,
    },
  ];

  let content: ReactNode;
  if (answer.failure !== null) {
    content = <FailureState failure={answer.failure} />;
  } else if (answer.busy || body === null) {
    content = <LoadingState label={LOADING_ACTIVITY} />;
  } else if (body.items.length === 0) {
    content = <EmptyState title={NO_ACTIVITY} description={NO_ACTIVITY_MORE} />;
  } else {
    content = (
      <EntityTable
        caption={ACTIVITY_HEADING}
        columns={columns}
        rows={body.items}
        rowId={(row) => `${row.at}:${row.actor_id}:${row.action}:${row.subject_kind}:${row.subject_id}`}
        rowLabel={(row) => whatWords(row.action, row.details)}
        exportName="company-activity"
      />
    );
  }
  const next = body?.next_cursor ?? null;
  return (
    <Frame title={ACTIVITY_HEADING} lede={ACTIVITY_LEDE}>
      <SectionCard title={ACTIVITY_HEADING}>
        <div className="flex min-w-0 flex-col gap-3">
          {body === null ? null : (
            <Filters base={ACTIVITY_PATH} departments={body.departments} people={body.actors} names={people} searchable />
          )}
          {content}
          <div className="flex flex-wrap items-center gap-2 empty:hidden">
            {cursor === "" ? null : (
              <Button
                variant="outline"
                className="min-h-11 sm:min-h-9"
                onClick={() => {
                  setCursor("");
                }}
              >
                {NEWEST}
              </Button>
            )}
            {next === null || answer.busy ? null : (
              <Button
                variant="outline"
                className="min-h-11 sm:min-h-9"
                onClick={() => {
                  setCursor(next);
                }}
              >
                {OLDER}
              </Button>
            )}
          </div>
        </div>
      </SectionCard>
    </Frame>
  );
}

// ------------------------------------------------------------------------- the consumption

export function ConsumptionPage() {
  const [days, setDays] = useState<number>(DEFAULT_WINDOW);
  const answer = useResource<unknown>(consumptionApiPath(days));
  const found = answer.data === null ? null : readConsumption(answer.data);

  let content: ReactNode;
  if (answer.failure !== null) {
    content = <FailureState failure={answer.failure} />;
  } else if (answer.busy || found === null) {
    content = <LoadingState label={LOADING_CONSUMPTION} />;
  } else if (found.withheld) {
    content = <EmptyState title={WITHHELD} description={WITHHELD_MORE} />;
  } else {
    content = (
      <div className="flex min-w-0 flex-col gap-3">
        <StatsStrip label={FIGURES_LABEL} busy={false} failure={null} count={1}>
          <StatCard label={SPENT_LABEL} value={moneyWords(found.spendMinor, found.currency)} />
        </StatsStrip>
        {found.incomplete ? <p className="m-0 text-[12.5px] text-dim">{INCOMPLETE}</p> : null}
        {found.ceilingSet ? null : <p className="m-0 text-[12.5px] text-dim">{NO_CEILING}</p>}
        <SectionCard title={BY_DEPARTMENT}>
          {found.lines.length === 0 ? (
            <p className="m-0 text-sm text-dim">{NOTHING_SPENT}</p>
          ) : (
            <ul aria-label={BY_DEPARTMENT} className="m-0 flex list-none flex-col gap-1 p-0">
              {found.lines.map((one) => (
                <li key={one.department} className="flex min-w-0 justify-between gap-3 text-sm">
                  <span className="min-w-0 [overflow-wrap:anywhere]">{one.department}</span>
                  <span className="tabular-nums">{moneyWords(one.spendMinor, found.currency)}</span>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>
    );
  }
  return (
    <Frame title={CONSUMPTION_HEADING} lede={CONSUMPTION_LEDE}>
      <form
        role="search"
        aria-label={FILTERS_LABEL}
        className="flex min-w-0 flex-wrap items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault();
        }}
      >
        <Choice
          label={WINDOW_FILTER}
          value={String(days)}
          onChange={(value) => {
            setDays(Number(value));
          }}
        >
          {CONSUMPTION_WINDOWS.map((one) => (
            <option key={one} value={String(one)}>
              {`Last ${String(one)} days`}
            </option>
          ))}
        </Choice>
      </form>
      {content}
    </Frame>
  );
}
