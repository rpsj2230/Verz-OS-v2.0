/**
 * Service levels: what each lane promised, what it measured over the period, and where it fell
 * short.
 *
 * **Every figure is the API's.** Whether a lane met its objective is the API's own `met`, and the
 * shortfalls are the reliability module's own sentences; the page adds no total over the lanes and
 * computes no percentage it was not sent, which is `serviceLevelsQuery.ts`'
 * `A_MEASUREMENT_IS_NEVER_RECOMPUTED_IN_A_BROWSER`. The figures at the top are counts of the lanes
 * drawn.
 *
 * **A reading with no lanes says there is nothing to show and nothing about why**, which is
 * `A_READING_WITH_NO_LANES_IS_NOT_EXPLAINED`: a narrowed reading and an install that promises
 * nothing are one body.
 *
 * **A figure the sample could not support reads "Not measured", never nought.** Nought would say
 * every request failed or answered instantly.
 *
 * What was removed from the old page: lower-case column headings that were field names, and the
 * one fixed window of a day (now the period every Report page offers).
 *
 * Task ids: M27.7.16, M27.16.1
 */

import { useState } from "react";
import { useResource } from "../../api/useResource";
import { EmptyState, EntityTable, FailureState, KpiStrip, LoadingState, SectionCard, StatCard, type EntityColumn } from "../../components/kit";
import { cn } from "../../lib/utils";
import { countWords } from "../agents/agentStats";
import { milliseconds, ratePercent, readServiceLevels, serviceLevelsPathFor, type LaneReadingRow } from "../serviceLevelsQuery";
import { BarList, DEFAULT_PERIOD, REPORTS_CRUMB, ReportHeader, periodWords, sheetOf, type ReportPeriod } from "./reportParts";

export const SERVICE_LEVELS_HEADING = "Service levels";
export const SERVICE_LEVELS_LEDE = "What each lane promised, what it measured, and where it fell short.";
export const SERVICE_LEVELS_CRUMBS = [REPORTS_CRUMB, { label: SERVICE_LEVELS_HEADING }];

export const LOADING_LANES = "Loading service levels.";
export const NO_LANES = "No lane to show";
export const NO_LANES_MORE = "Each lane's reading appears here when there is one to show.";

export const FIGURES_LABEL = "Service level figures";
export const LANES_LABEL = "Lanes";
export const MET_LABEL = "Meeting their objective";
export const MISSED_LABEL = "Missing their objective";

export const ANSWER_TIME = "Answer time against objective";
export const ANSWER_TIME_LEDE = "The 95th percentile; the line is what the lane promises.";
export const LANES_HEADING = "Every lane";

export const MET = "Met";
export const MISSED = "Missed";

/** What is said where a figure was not measured. Never nought. */
export const NOT_MEASURED = "Not measured";

function measured(text: string): string {
  return text === "-" ? NOT_MEASURED : text;
}

function OutcomePill({ met }: { readonly met: boolean }) {
  return (
    <span
      data-slot="outcome-pill"
      className={cn(
        "inline-block rounded-[2px] px-1.5 py-0.5 font-mono text-[10.5px] font-medium tracking-[0.03em]",
        met ? "bg-ok-wash text-ok" : "bg-crit-wash text-crit",
      )}
    >
      {met ? MET : MISSED}
    </span>
  );
}

export const COLUMNS: readonly EntityColumn<LaneReadingRow>[] = [
  { id: "lane", header: "Lane", hideable: false, cell: (row) => row.lane, text: (row) => row.lane },
  { id: "outcome", header: "Outcome", cell: (row) => <OutcomePill met={row.met} />, text: (row) => (row.met ? MET : MISSED) },
  { id: "p95", header: "p95", align: "end", cell: (row) => measured(milliseconds(row.p95_ms)), text: (row) => measured(milliseconds(row.p95_ms)) },
  {
    id: "p95-objective",
    header: "p95 promised",
    align: "end",
    cell: (row) => (row.objective_p95_ms === null ? "" : milliseconds(row.objective_p95_ms)),
    text: (row) => (row.objective_p95_ms === null ? "" : milliseconds(row.objective_p95_ms)),
  },
  { id: "success", header: "Success", align: "end", cell: (row) => measured(ratePercent(row.success_rate)), text: (row) => measured(ratePercent(row.success_rate)) },
  {
    id: "success-objective",
    header: "Success promised",
    align: "end",
    cell: (row) => ratePercent(row.objective_success_rate),
    text: (row) => ratePercent(row.objective_success_rate),
  },
  { id: "requests", header: "Requests", align: "end", cell: (row) => countWords(row.requests), text: (row) => String(row.requests) },
  {
    id: "shortfalls",
    header: "Shortfalls",
    cell: (row) => (
      <ul className="m-0 flex list-none flex-col gap-1 p-0 [overflow-wrap:anywhere]">
        {row.shortfalls.map((one) => (
          <li key={one}>{one}</li>
        ))}
      </ul>
    ),
    text: (row) => row.shortfalls.join("; "),
  },
];

function Reading({ lanes }: { readonly lanes: readonly LaneReadingRow[] }) {
  const met = lanes.filter((one) => one.met).length;
  const timed = lanes.filter((one) => one.p95_ms !== null || one.objective_p95_ms !== null);
  return (
    <>
      <KpiStrip label={FIGURES_LABEL} count={3}>
        <StatCard label={LANES_LABEL} value={countWords(lanes.length)} />
        <StatCard label={MET_LABEL} value={countWords(met)} />
        <StatCard label={MISSED_LABEL} value={countWords(lanes.length - met)} />
      </KpiStrip>
      {timed.length === 0 ? null : (
        <SectionCard title={ANSWER_TIME} lede={ANSWER_TIME_LEDE}>
          <BarList
            caption={ANSWER_TIME}
            keyHeading="Lane"
            valueHeading="p95 against objective"
            bars={timed.map((one) => ({
              key: one.lane,
              label: one.lane,
              value: one.p95_ms ?? 0,
              mark: one.objective_p95_ms ?? undefined,
              figure:
                one.objective_p95_ms === null
                  ? measured(milliseconds(one.p95_ms))
                  : `${measured(milliseconds(one.p95_ms))}, promised ${milliseconds(one.objective_p95_ms)}`,
            }))}
          />
        </SectionCard>
      )}
      <SectionCard title={LANES_HEADING}>
        <EntityTable caption={LANES_HEADING} columns={COLUMNS} rows={lanes} rowId={(row) => row.lane} rowLabel={(row) => row.lane} />
      </SectionCard>
    </>
  );
}

export function ServiceLevelsPage() {
  const [period, setPeriod] = useState<ReportPeriod>(DEFAULT_PERIOD);
  const answer = useResource<unknown>(serviceLevelsPathFor(period));
  const reading = answer.data === null ? null : readServiceLevels(answer.data);

  let content;
  if (answer.failure !== null) {
    content = <FailureState failure={answer.failure} />;
  } else if (answer.busy) {
    content = <LoadingState label={LOADING_LANES} />;
  } else if (reading === null || reading.lanes.length === 0) {
    content = <EmptyState title={NO_LANES} description={NO_LANES_MORE} />;
  } else {
    content = <Reading lanes={reading.lanes} />;
  }

  const drawn = reading !== null && !answer.busy && answer.failure === null && reading.lanes.length > 0;
  return (
    <div data-slot="report-page" className="flex min-w-0 flex-col gap-4">
      <ReportHeader
        crumbs={SERVICE_LEVELS_CRUMBS}
        title={SERVICE_LEVELS_HEADING}
        lede={`${SERVICE_LEVELS_LEDE} ${periodWords(period)}.`}
        period={period}
        onPeriod={setPeriod}
        sheets={
          drawn && reading !== null
            ? [
                sheetOf(
                  LANES_HEADING,
                  `service-levels-${String(period)}-days`,
                  COLUMNS.map((one) => ({ header: one.header, text: one.text ?? (() => "") })),
                  reading.lanes,
                ),
              ]
            : []
        }
      />
      {content}
    </div>
  );
}
