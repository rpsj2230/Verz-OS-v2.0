/**
 * The Dashboard view of one automation, which opens first: how its runs went, and its recent runs.
 *
 * **The figures are the stats route's, and only what it sent.** Runs, and how many succeeded,
 * failed or were refused, over seven or thirty days, over the runs this reader may be shown. A run's
 * cost is not recorded by anything on an install yet, so its figure reads "Not recorded yet" with the
 * API's reason, never nought.
 *
 * **What a run found is shown only to whom it ran as.** Everybody else who may see the automation
 * sees that it ran, when and how it ended.
 *
 * Task ids: M27.12.3, M39.6.1.4, M27.16.1
 */

import { useState } from "react";
import { useResource } from "../../api/useResource";
import { EmptyState, SectionCard, StatCard, StatsStrip } from "../../components/kit";
import { cn } from "../../lib/utils";
import { basisWords, rangeWords } from "../agents/agentStats";
import {
  COST_FIGURE,
  automationStatsApiPath,
  dateWords,
  outcomeWords,
  readAutomationStats,
  type AutomationDetail,
} from "./automationsQuery";

export const FIGURES_LABEL = "This automation's runs";
export const PERIOD_LABEL = "Period the figures cover";
export const RUNS_LABEL = "Runs";
export const SUCCEEDED_LABEL = "Succeeded";
export const FAILED_LABEL = "Failed";
export const REFUSED_LABEL = "Refused";
export const NEXT_RUN_LABEL = "Next run";
export const COST_LABEL = "Cost";
export const RECENT_HEADING = "Recent runs";
export const NO_RUNS = "No runs yet";
export const NO_RUNS_DESCRIPTION = "A run appears here once the automation is resumed and its time comes.";
export const NOT_SCHEDULED = "Not scheduled";
export const ONLY_TO_WHOM = "What a run found is shown only to the person it ran as.";

const PERIODS = ["7d", "30d"] as const;

function count(value: number | undefined): string | undefined {
  return value === undefined ? undefined : value.toLocaleString("en-GB");
}

function PeriodSwitch({ period, onChange }: { readonly period: string; readonly onChange: (period: string) => void }) {
  return (
    <div role="group" aria-label={PERIOD_LABEL} className="inline-flex rounded-md border border-line bg-sunk p-0.5">
      {PERIODS.map((one) => (
        <button
          key={one}
          type="button"
          aria-pressed={one === period}
          onClick={() => {
            onChange(one);
          }}
          className={cn(
            "min-h-11 rounded-[5px] px-3 text-[12.5px] outline-hidden focus-visible:ring-2 focus-visible:ring-ring sm:min-h-7",
            one === period ? "bg-panel font-medium text-ink shadow-xs" : "text-dim hover:text-ink",
          )}
        >
          {rangeWords(one)}
        </button>
      ))}
    </div>
  );
}

function Figures({ detail }: { readonly detail: AutomationDetail }) {
  const [period, setPeriod] = useState<string>("30d");
  const stats = useResource<unknown>(automationStatsApiPath(detail.row.id));
  const read = stats.data === null ? null : readAutomationStats(stats.data);
  const figures = read?.periods.find((one) => one.range === period);
  const whose = basisWords(read?.basis);
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="m-0 text-sm font-semibold text-ink">{FIGURES_LABEL}</h2>
        <PeriodSwitch period={period} onChange={setPeriod} />
      </div>
      <StatsStrip label={FIGURES_LABEL} busy={stats.busy} failure={stats.failure} count={6}>
        <StatCard label={RUNS_LABEL} value={count(figures?.runs)} sub={whose} />
        <StatCard label={SUCCEEDED_LABEL} value={count(figures?.succeeded)} />
        <StatCard label={FAILED_LABEL} value={count(figures?.failed)} />
        <StatCard label={REFUSED_LABEL} value={count(figures?.refused)} />
        <StatCard
          label={NEXT_RUN_LABEL}
          value={detail.row.nextRunAt === undefined ? NOT_SCHEDULED : dateWords(detail.row.nextRunAt)}
        />
        <StatCard label={COST_LABEL} unrecordedWhy={read?.unrecorded[COST_FIGURE]} />
      </StatsStrip>
    </div>
  );
}

export function AutomationDashboard({ detail }: { readonly detail: AutomationDetail }) {
  return (
    <div data-slot="automation-dashboard" className="flex min-w-0 flex-col gap-4">
      <Figures detail={detail} />
      <SectionCard title={RECENT_HEADING} lede={ONLY_TO_WHOM}>
        {detail.runs.length === 0 ? (
          <EmptyState title={NO_RUNS} description={NO_RUNS_DESCRIPTION} />
        ) : (
          <ol className="m-0 flex list-none flex-col gap-3 p-0">
            {detail.runs.slice(0, 10).map((run) => (
              <li
                key={run.finishedAt}
                className="flex flex-col gap-1 border-b border-line pb-3 text-[13px] last:border-b-0 last:pb-0"
              >
                <span className="flex flex-wrap items-baseline gap-2">
                  <span className="font-medium text-ink">{outcomeWords(run.outcome)}</span>
                  <span className="font-mono text-[12px] text-dim tabular-nums">{dateWords(run.finishedAt)}</span>
                  {run.ranAsName === "" ? null : <span className="text-dim">as {run.ranAsName}</span>}
                </span>
                {run.reason === undefined ? null : <span className="text-dim">{run.reason}</span>}
                {run.result.length === 0 ? null : (
                  <ul className="m-0 flex list-disc flex-col gap-0.5 pl-5 text-body">
                    {run.result.map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ol>
        )}
      </SectionCard>
    </div>
  );
}
