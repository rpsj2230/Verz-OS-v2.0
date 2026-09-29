/**
 * Adoption, the third view of Usage and cost: who is using this, and which departments have gone
 * quiet.
 *
 * **Every department the reader may see has a line, zero included**, which is `adoptionQuery.ts`'
 * `A_ZERO_IS_A_LINE_AND_NOT_AN_ABSENCE`: whether a line appears is a fact about the reader's reach,
 * so a quiet department is listed as quiet rather than tidied away, and the quiet ones are the
 * answer to "who has stopped".
 *
 * **Two reads, each owning its half.** The figures and the quiet departments come from the usage
 * report over the same period, whose department lines are whole for this reader and whose question
 * total is the API's. The list is the adoption route's, paged, searched, filtered and ordered on the
 * server (`brain.listing`), so it is never a total: a full page says there is more and never how
 * many.
 *
 * What was removed from the old page: the period as a drop-down of four including a year (now the
 * three every Report page offers), and the lede explaining both figures.
 *
 * Task ids: M27.7.17, M27.8.6, M27.16.1
 */

import { useState } from "react";
import type { ApiFailure } from "../../api/errors";
import { useResource } from "../../api/useResource";
import { FETCHING_MORE, NOTHING_MATCHES, SHOW_MORE } from "../../components/ListControls";
import { narrows, NO_QUESTION } from "../../components/listing";
import { useListing } from "../../components/useListing";
import {
  Chip,
  EmptyState,
  EntityTable,
  FailureState,
  ListToolbar,
  LoadingState,
  RESET_LABEL,
  SectionCard,
  StatCard,
  StatsStrip,
  type EntityColumn,
} from "../../components/kit";
import { Button } from "../../components/ui/button";
import { countWords } from "../agents/agentStats";
import {
  ADOPTION_API_PATH,
  ADOPTION_FILTERS,
  ADOPTION_SORTS,
  DAYS_PARAMETER,
  readAdoptionPage,
  type AdoptionLineRow,
} from "../adoptionQuery";
import { readUsage, usageApiPath, type UsageBody } from "../usageQuery";
import { USAGE_AND_COST } from "./UsagePage";
import {
  BarList,
  DEFAULT_PERIOD,
  Quiet,
  REPORTS_CRUMB,
  ReportHeader,
  counted,
  periodWords,
  sheetOf,
  type ReportPeriod,
} from "./reportParts";

export const ADOPTION_HEADING = "Adoption";
export const ADOPTION_LEDE = "Who is using this, and which departments have gone quiet.";
export const ADOPTION_CRUMBS = [REPORTS_CRUMB, { label: USAGE_AND_COST, to: "/usage" }, { label: ADOPTION_HEADING }];

export const FIGURES_LABEL = "Adoption figures";
export const QUESTIONS_LABEL = "Questions";
export const PEOPLE_LABEL = "People asking";
export const ASKING_LABEL = "Departments asking";
export const QUIET_LABEL = "Quiet departments";
export const NO_QUESTION_IN_PERIOD = "no question in this period";

export const QUIET_HEADING = "Quiet departments";
export const QUIET_LEDE = "Departments where nobody asked a question in this period.";
export const NONE_QUIET = "Every department asked at least one question.";
export const PEOPLE_HEADING = "People asking, by department";
export const LIST_HEADING = "All departments";
export const FILTERS_LABEL = "Narrow the departments";
export const LOADING_ADOPTION = "Loading adoption.";
export const NO_ADOPTION = "No department to show";
export const NO_ADOPTION_MORE = "A department appears here once it is in the directory and you may read its usage.";

/** A page that came back full. A fact about there being more, and never a figure. */
export const MORE_DEPARTMENTS = "There are more departments than this page shows.";

export const COLUMNS: readonly EntityColumn<AdoptionLineRow>[] = [
  { id: "department", header: "Department", hideable: false, cell: (row) => row.department, text: (row) => row.department },
  { id: "questions", header: "Questions", align: "end", cell: (row) => countWords(row.questions), text: (row) => String(row.questions) },
  { id: "people", header: "People", align: "end", cell: (row) => countWords(row.people), text: (row) => String(row.people) },
];

function Figures({ usage }: { readonly usage: UsageBody }) {
  const cards = [];
  if (usage.questions !== null) {
    cards.push(<StatCard key="questions" label={QUESTIONS_LABEL} value={countWords(usage.questions)} />);
  }
  if (usage.people !== null) {
    cards.push(<StatCard key="people" label={PEOPLE_LABEL} value={countWords(usage.people.length)} />);
  }
  if (usage.departments !== null) {
    const asking = usage.departments.filter((one) => one.questions > 0).length;
    cards.push(<StatCard key="asking" label={ASKING_LABEL} value={countWords(asking)} />);
    cards.push(
      <StatCard
        key="quiet"
        label={QUIET_LABEL}
        value={countWords(usage.departments.length - asking)}
        sub={NO_QUESTION_IN_PERIOD}
      />,
    );
  }
  return <>{cards}</>;
}

function FigureStrip({ usage, busy, failure }: { readonly usage: UsageBody | null; readonly busy: boolean; readonly failure: ApiFailure | null }) {
  const count = usage === null ? 0 : [usage.questions !== null, usage.people !== null, usage.departments !== null, usage.departments !== null].filter(Boolean).length;
  if (!busy && failure === null && count === 0) {
    return null;
  }
  return (
    <StatsStrip label={FIGURES_LABEL} busy={busy} failure={failure} count={count}>
      {usage === null ? null : <Figures usage={usage} />}
    </StatsStrip>
  );
}

function Departments({ lines }: { readonly lines: NonNullable<UsageBody["departments"]> }) {
  const quiet = lines.filter((one) => one.questions === 0);
  const asking = [...lines].filter((one) => one.people > 0).sort((a, b) => b.people - a.people);
  return (
    <div className="[display:grid] min-w-0 items-start gap-4 xl:grid-cols-2">
      <SectionCard title={QUIET_HEADING} lede={QUIET_LEDE}>
        {quiet.length === 0 ? (
          <Quiet>{NONE_QUIET}</Quiet>
        ) : (
          <ul aria-label={QUIET_HEADING} className="m-0 flex list-none flex-wrap gap-1.5 p-0">
            {quiet.map((one) => (
              <li key={one.department} className="min-w-0 max-w-full">
                <Chip>{one.department}</Chip>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
      <SectionCard title={PEOPLE_HEADING}>
        {asking.length === 0 ? (
          <Quiet>Nobody asked a question in this period.</Quiet>
        ) : (
          <BarList
            caption={PEOPLE_HEADING}
            keyHeading="Department"
            valueHeading="People asking"
            limit={10}
            bars={asking.map((one) => ({
              key: one.department,
              label: one.department,
              value: one.people,
              figure: counted(one.people, "person", "people"),
            }))}
          />
        )}
      </SectionCard>
    </div>
  );
}

export function AdoptionPage() {
  const [period, setPeriod] = useState<ReportPeriod>(DEFAULT_PERIOD);
  const usage = useResource<unknown>(usageApiPath(period));
  const usageBody = usage.data === null ? null : readUsage(usage.data);
  const listing = useListing<AdoptionLineRow>(ADOPTION_API_PATH, {
    choices: ADOPTION_FILTERS,
    extra: { [DAYS_PARAMETER]: String(period) },
  });
  const page = readAdoptionPage(listing.body);

  let list;
  if (listing.failure !== null) {
    list = <FailureState failure={listing.failure} />;
  } else if (listing.busy) {
    list = <LoadingState label={LOADING_ADOPTION} />;
  } else if (page.lines.length === 0) {
    list = narrows(listing.question) ? (
      <EmptyState
        title={NOTHING_MATCHES}
        description="Change the search or clear a filter."
        action={
          <Button
            variant="outline"
            onClick={() => {
              listing.ask({ ...NO_QUESTION, sort: listing.question.sort });
            }}
          >
            {RESET_LABEL}
          </Button>
        }
      />
    ) : (
      <EmptyState title={NO_ADOPTION} description={NO_ADOPTION_MORE} />
    );
  } else {
    list = (
      <EntityTable
        caption={LIST_HEADING}
        columns={COLUMNS}
        rows={page.lines}
        rowId={(row) => row.department}
        rowLabel={(row) => row.department}
      />
    );
  }

  const drawn = !listing.busy && listing.failure === null && page.lines.length > 0;
  return (
    <div data-slot="report-page" className="flex min-w-0 flex-col gap-4">
      <ReportHeader
        crumbs={ADOPTION_CRUMBS}
        title={ADOPTION_HEADING}
        lede={`${ADOPTION_LEDE} ${periodWords(period)}.`}
        period={period}
        onPeriod={setPeriod}
        sheets={
          drawn
            ? [
                sheetOf(
                  LIST_HEADING,
                  `adoption-${String(period)}-days`,
                  COLUMNS.map((one) => ({ header: one.header, text: one.text ?? (() => "") })),
                  page.lines,
                ),
              ]
            : []
        }
      />
      <FigureStrip usage={usageBody} busy={usage.busy} failure={usage.failure} />
      {usageBody === null || usageBody.departments === null || usage.busy || usage.failure !== null ? null : (
        <Departments lines={usageBody.departments} />
      )}
      <SectionCard title={LIST_HEADING}>
        <div className="flex min-w-0 flex-col gap-3">
          <ListToolbar label={FILTERS_LABEL} listing={listing} choices={ADOPTION_FILTERS} sorts={ADOPTION_SORTS} />
          {list}
          <div className="flex flex-wrap items-center gap-2 empty:hidden">
            {listing.moreFailure === null ? null : <FailureState failure={listing.moreFailure} />}
            {listing.fetchingMore ? (
              <p role="status" className="m-0 text-[12.5px] text-dim">
                {FETCHING_MORE}
              </p>
            ) : null}
            {listing.more ? (
              <Button
                variant="outline"
                className="min-h-11 sm:min-h-9"
                disabled={listing.fetchingMore}
                onClick={() => {
                  listing.showMore();
                }}
              >
                {SHOW_MORE}
              </Button>
            ) : null}
          </div>
          {drawn && listing.more ? <Quiet>{MORE_DEPARTMENTS}</Quiet> : null}
        </div>
      </SectionCard>
    </div>
  );
}
