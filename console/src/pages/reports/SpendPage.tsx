/**
 * Spend, the second view of Usage and cost: what the period cost, by department, model or lane.
 *
 * **Cost is drawn only where it is recorded.** The report says `cost` is not recorded while nothing
 * writes cost or no model is priced in the install's currency (`brain.report_routes`, the
 * Overview's own rule and sentence), and the page then draws "Not recorded yet" with that sentence
 * and no table, because a report over no cost rows reads 0.00 for a company that has spent money.
 * A report nobody has built says so too. Once a price is set a period with no cost is a measured
 * nought and is drawn as one.
 *
 * **The total is the API's and is never added up here**, which is `spendQuery.ts`'
 * `A_TOTAL_IS_READ_AND_NEVER_ADDED_UP_HERE`. The bars are the lines the API sent, largest first.
 *
 * What was removed from the old page: the freshness word printed as raw text with a UTC instant
 * (now a figure in the install's zone), the sentence explaining automation (now a card's line), and
 * a table that drew 0.00 on every install where nothing had been priced.
 *
 * Task ids: M27.7.15, M27.16.1
 */

import { useState } from "react";
import { useResource } from "../../api/useResource";
import { EmptyState, FailureState, KpiStrip, LoadingState, Note, SectionCard, StatCard } from "../../components/kit";
import { capitalised } from "../overview/overviewQuery";
import {
  SPEND_DIMENSIONS,
  costNotRecorded,
  currencyNotSetHint,
  instantWords,
  moneyWords,
  readSpendReport,
  spendReportPath,
  type SpendReportBody,
} from "../spendQuery";
import { USAGE_AND_COST } from "./UsagePage";
import {
  BarList,
  DEFAULT_PERIOD,
  Quiet,
  REPORTS_CRUMB,
  ReportHeader,
  Switch,
  periodWords,
  sheetOf,
  type ReportPeriod,
  type Sheet,
} from "./reportParts";

export const SPEND_HEADING = "Spend";
export const SPEND_LEDE = "What the questions cost, by department, model or lane.";
export const SPEND_CRUMBS = [REPORTS_CRUMB, { label: USAGE_AND_COST, to: "/usage" }, { label: SPEND_HEADING }];

export const LOADING_SPEND = "Loading spend.";
export const NO_COST_YET = "No cost recorded yet";
export const NOT_BUILT = "The spend report has not been built yet, so there is no figure to show.";
export const NO_COST_IN_PERIOD = "Nothing was spent in this period.";

export const FIGURES_LABEL = "Spend figures";
export const COST_LABEL = "Cost";
export const LARGEST_LABEL = "Largest";
export const AS_OF_LABEL = "Figures as of";
export const WITHOUT_AUTOMATION = "people only, automation not counted";
export const WITH_AUTOMATION = "automation included";
export const DIMENSION_LABEL = "Spend by";

/** The card heading over the bars, by the dimension asked. */
export function byWords(dimension: string): string {
  const label = SPEND_DIMENSIONS.find((one) => one.value === dimension)?.label ?? dimension;
  return `Cost by ${label.toLocaleLowerCase("en-GB")}`;
}

/** The lines as the export saves them. */
export function spendSheets(report: SpendReportBody, period: ReportPeriod): Sheet[] {
  if (costNotRecorded(report) !== null || !report.built) {
    return [];
  }
  return [
    sheetOf(
      byWords(report.dimension),
      `spend-by-${report.dimension}-${String(period)}-days`,
      [
        { header: SPEND_DIMENSIONS.find((one) => one.value === report.dimension)?.label ?? report.dimension, text: (row) => row.key },
        { header: `Cost${currencyNotSetHint(report.currency) === null ? ` (${report.currency})` : ""}`, text: (row) => (row.cost_minor / 100).toFixed(2) },
      ],
      report.lines,
    ),
  ];
}

function Recorded({ report }: { readonly report: SpendReportBody }) {
  const ordered = [...report.lines].sort((a, b) => b.cost_minor - a.cost_minor);
  const [largest] = ordered;
  const hint = currencyNotSetHint(report.currency);
  const cards = [
    <StatCard
      key="cost"
      label={COST_LABEL}
      value={report.total_minor === null ? undefined : moneyWords(report.total_minor, report.currency)}
      sub={report.machine_included ? WITH_AUTOMATION : WITHOUT_AUTOMATION}
    />,
    <StatCard
      key="largest"
      label={LARGEST_LABEL}
      value={largest === undefined ? undefined : largest.key}
      sub={largest === undefined ? undefined : moneyWords(largest.cost_minor, report.currency)}
    />,
    <StatCard
      key="as-of"
      label={AS_OF_LABEL}
      value={report.as_of === null ? undefined : instantWords(report.as_of, report.time_zone)}
      sub={report.freshness}
    />,
  ];
  return (
    <>
      <KpiStrip label={FIGURES_LABEL} count={cards.length}>
        {cards}
      </KpiStrip>
      {hint === null ? null : <Note>{hint}</Note>}
      <SectionCard title={byWords(report.dimension)}>
        {ordered.length === 0 ? (
          <Quiet>{NO_COST_IN_PERIOD}</Quiet>
        ) : (
          <BarList
            caption={byWords(report.dimension)}
            keyHeading={report.dimension}
            valueHeading={COST_LABEL}
            bars={ordered.map((line) => ({
              key: line.key,
              label: line.key,
              value: line.cost_minor,
              figure: moneyWords(line.cost_minor, report.currency),
            }))}
          />
        )}
      </SectionCard>
    </>
  );
}

/** An API reason as a sentence: a capital first and a full stop last, once. */
export function asSentence(why: string): string {
  const trimmed = why.trim();
  return capitalised(trimmed.endsWith(".") ? trimmed : `${trimmed}.`);
}

function NotRecorded({ why }: { readonly why: string }) {
  return (
    <>
      <KpiStrip label={FIGURES_LABEL} count={1}>
        <StatCard label={COST_LABEL} unrecordedWhy={why} />
      </KpiStrip>
      <EmptyState title={NO_COST_YET} description={asSentence(why)} />
    </>
  );
}

export function SpendPage() {
  const [period, setPeriod] = useState<ReportPeriod>(DEFAULT_PERIOD);
  const [dimension, setDimension] = useState(SPEND_DIMENSIONS[0]?.value ?? "department");
  // The day is read once per page, so a report asked for over midnight names one window.
  const [today] = useState(() => new Date());
  const answer = useResource<unknown>(spendReportPath(dimension, period, today));
  const report = answer.data === null ? null : readSpendReport(answer.data);

  let content;
  if (answer.failure !== null) {
    content = <FailureState failure={answer.failure} />;
  } else if (answer.busy) {
    content = <LoadingState label={LOADING_SPEND} />;
  } else if (report === null) {
    content = <EmptyState title={NO_COST_YET} description={NOT_BUILT} />;
  } else {
    const why = costNotRecorded(report);
    content =
      why !== null ? <NotRecorded why={why} /> : !report.built ? <NotRecorded why={NOT_BUILT} /> : <Recorded report={report} />;
  }

  return (
    <div data-slot="report-page" className="flex min-w-0 flex-col gap-4">
      <ReportHeader
        crumbs={SPEND_CRUMBS}
        title={SPEND_HEADING}
        lede={`${SPEND_LEDE} ${periodWords(period)}.`}
        period={period}
        onPeriod={setPeriod}
        sheets={report === null || answer.busy || answer.failure !== null ? [] : spendSheets(report, period)}
      />
      <div>
        <Switch label={DIMENSION_LABEL} value={dimension} options={SPEND_DIMENSIONS} onChange={setDimension} />
      </div>
      {content}
    </div>
  );
}
