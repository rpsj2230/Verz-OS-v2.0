/**
 * Quality and canaries: whether the permission canaries passed over the period, when they last
 * ran, and whether they run at all.
 *
 * **A pass is drawn only for a run the API calls passed**, which is `qualityQuery.ts`'
 * `A_PASS_IS_DRAWN_ONLY_FOR_A_RUN_THE_API_CALLS_PASSED`. What a failed run found is never sent: it
 * goes to the on-call alert, and the page says so in one line.
 *
 * **A reader who may not see a run is answered as an install with none**: no last run, no runs in
 * the period and nothing cut off (`brain.console.quality_view`'s
 * `A_RUN_HISTORY_IS_WITHHELD_WHOLE_AS_THE_LAST_RUN_IS`), so the page draws the two alike. The
 * counts at the top are counts of the runs listed, shown only when a run is listed; with none, the
 * card says "Not recorded yet" rather than nought.
 *
 * What was removed from the old page: the design's rows restated as paragraphs (who a run asks as,
 * what it checks, what happens on a red one), and the golden questions and regression cards, which
 * said at length that an install holds neither.
 *
 * Task ids: M27.7.19, M27.16.1
 */

import { useState } from "react";
import { useResource } from "../../api/useResource";
import { EmptyState, EntityTable, FailureState, KpiStrip, LoadingState, Note, SectionCard, StatCard, type EntityColumn } from "../../components/kit";
import { cn } from "../../lib/utils";
import { whenWords } from "../agents/agentStats";
import { cadence, qualityApiPathFor, readQuality, resultWords, runCounts, type CanaryRunBody, type QualityBody } from "../qualityQuery";
import { capitalised } from "../overview/overviewQuery";
import { DEFAULT_PERIOD, Quiet, REPORTS_CRUMB, ReportHeader, periodWords, sheetOf, type ReportPeriod } from "./reportParts";

export const QUALITY_HEADING = "Quality and canaries";
export const QUALITY_LEDE = "The permission canaries ask questions whose right answer is a refusal; a pass means every one was refused.";
export const QUALITY_CRUMBS = [REPORTS_CRUMB, { label: QUALITY_HEADING }];

export const LOADING_QUALITY = "Loading the canary runs.";
export const NO_QUALITY = "No canary figures to show";
export const NO_QUALITY_MORE = "The canaries' runs appear here once they have run.";

export const FIGURES_LABEL = "Canary figures";
export const LAST_RUN_LABEL = "Last run";
export const PASSED_LABEL = "Passed";
export const FAILED_LABEL = "Failed";
export const RUNS_LABEL = "Runs in this period";
export const SCHEDULE_LABEL = "Schedule";
export const NOT_SCHEDULED = "Not scheduled";
export const OWED = "a run is owed now";

export const RUNS_HEADING = "Runs";
export const NO_RUN_IN_PERIOD = "No canary run in this period.";
export const CUT_OFF = "The period holds more runs than are listed here; the newest are shown.";
export const FINDINGS_GO_TO_THE_ALERT = "What a failed run found goes to the on-call alert and is not stored here.";

/** A figure with "+" when the list it was counted over was cut off. */
function atLeast(count: number, cut: boolean): string {
  const figure = count.toLocaleString("en-GB");
  return cut ? `${figure}+` : figure;
}

const RESULT_TONE: Readonly<Record<string, string>> = {
  passed: "bg-ok-wash text-ok",
  failed: "bg-crit-wash text-crit",
};

function ResultPill({ state }: { readonly state: string }) {
  return (
    <span
      data-slot="result-pill"
      className={cn(
        "inline-block rounded-[2px] px-1.5 py-0.5 font-mono text-[10.5px] font-medium tracking-[0.03em]",
        RESULT_TONE[state] ?? "bg-sunk text-dim",
      )}
    >
      {resultWords(state)}
    </span>
  );
}

export const COLUMNS: readonly EntityColumn<CanaryRunBody>[] = [
  { id: "started", header: "Started", hideable: false, cell: (row) => whenWords(row.started_at), text: (row) => row.started_at },
  { id: "result", header: "Result", cell: (row) => <ResultPill state={row.state} />, text: (row) => resultWords(row.state) },
  {
    id: "finished",
    header: "Finished",
    cell: (row) => (row.finished_at === null ? "" : whenWords(row.finished_at)),
    text: (row) => row.finished_at ?? "",
  },
];

function Figures({ body }: { readonly body: QualityBody }) {
  const last = body.last_canary_run;
  const counts = runCounts(body.runs);
  const cards = [
    <StatCard
      key="last"
      label={LAST_RUN_LABEL}
      value={last === null ? undefined : resultWords(last.state)}
      sub={last === null ? undefined : whenWords(last.started_at)}
    />,
  ];
  if (body.runs.length > 0) {
    cards.push(<StatCard key="passed" label={PASSED_LABEL} value={atLeast(counts.passed, body.runs_truncated)} />);
    cards.push(<StatCard key="failed" label={FAILED_LABEL} value={atLeast(counts.failed, body.runs_truncated)} />);
  } else {
    cards.push(<StatCard key="runs" label={RUNS_LABEL} />);
  }
  cards.push(
    <StatCard
      key="schedule"
      label={SCHEDULE_LABEL}
      value={body.canaries_started ? capitalised(cadence(body.canary_interval_seconds)) : NOT_SCHEDULED}
      sub={body.canaries_owed && body.canaries_started ? OWED : undefined}
    />,
  );
  return (
    <KpiStrip label={FIGURES_LABEL} count={cards.length}>
      {cards}
    </KpiStrip>
  );
}

/** The runs as a row of marks, oldest first, for the eye; the table below says the same in words. */
function RunStrip({ runs }: { readonly runs: readonly CanaryRunBody[] }) {
  return (
    <div aria-hidden className="flex flex-wrap gap-[3px]">
      {[...runs].reverse().map((run) => (
        <span
          key={run.started_at}
          className={cn("block size-3 rounded-[2px]", run.state === "passed" ? "bg-ok" : run.state === "failed" ? "bg-crit" : "bg-line")}
        />
      ))}
    </div>
  );
}

function Runs({ body }: { readonly body: QualityBody }) {
  return (
    <SectionCard title={RUNS_HEADING} footer={<Note>{FINDINGS_GO_TO_THE_ALERT}</Note>}>
      {body.runs.length === 0 ? (
        <Quiet>{NO_RUN_IN_PERIOD}</Quiet>
      ) : (
        <div className="flex min-w-0 flex-col gap-3">
          <RunStrip runs={body.runs} />
          <EntityTable caption={RUNS_HEADING} columns={COLUMNS} rows={body.runs} rowId={(row) => row.started_at} rowLabel={(row) => row.started_at} />
          {body.runs_truncated ? <Quiet>{CUT_OFF}</Quiet> : null}
        </div>
      )}
    </SectionCard>
  );
}

export function QualityPage() {
  const [period, setPeriod] = useState<ReportPeriod>(DEFAULT_PERIOD);
  const answer = useResource<unknown>(qualityApiPathFor(period));
  const body = answer.data === null ? null : readQuality(answer.data);

  let content;
  if (answer.failure !== null) {
    content = <FailureState failure={answer.failure} />;
  } else if (answer.busy) {
    content = <LoadingState label={LOADING_QUALITY} />;
  } else if (body === null) {
    content = <EmptyState title={NO_QUALITY} description={NO_QUALITY_MORE} />;
  } else {
    content = (
      <>
        <Figures body={body} />
        <Runs body={body} />
      </>
    );
  }

  const drawn = body !== null && !answer.busy && answer.failure === null && body.runs.length > 0;
  return (
    <div data-slot="report-page" className="flex min-w-0 flex-col gap-4">
      <ReportHeader
        crumbs={QUALITY_CRUMBS}
        title={QUALITY_HEADING}
        lede={`${QUALITY_LEDE} ${periodWords(period)}.`}
        period={period}
        onPeriod={setPeriod}
        sheets={
          drawn && body !== null
            ? [
                sheetOf(
                  "Canary runs",
                  `canary-runs-${String(period)}-days`,
                  COLUMNS.map((one) => ({ header: one.header, text: one.text ?? (() => "") })),
                  body.runs,
                ),
              ]
            : []
        }
      />
      {content}
    </div>
  );
}
