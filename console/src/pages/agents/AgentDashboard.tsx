/**
 * The Dashboard view of one agent, which opens first: what it has been doing, and what is waiting.
 *
 * **The figures are the stats route's, and only what it sent.** Runs, answered, nothing returned,
 * the median time, cost and when it was last active, for the period chosen (7 or 30 days), from
 * `agentStats.ts`. While they are on their way the strip says so; if the route fails the strip draws
 * the API's sentence under "The figures could not be loaded"; a figure the route did not send, or
 * listed as unrecorded, reads "Not recorded yet" with the route's reason, never nought. Whose the
 * figures are is said under each, because a reader shown their own runs would otherwise read them as
 * the agent's.
 *
 * **Two blocks say what the page is not sent yet, rather than drawing examples.** No route lists one
 * agent's runs, and approvals carry no agent to filter by, so "Recent runs" and "Waiting on a person"
 * are notes with a link to where the company-wide list is. The design of record draws both with
 * example rows; an install shows no example.
 *
 * **Automations are live.** A reader of the Automations tab sees this agent's automations with the
 * start and stop the API offers, which is `components/AgentAutomations.tsx` unchanged, and a link to
 * the gallery.
 *
 * Task ids: M27.10.2, M39.6.1.3
 */

import { ArrowUpRight } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useResource, type Resource } from "../../api/useResource";
import { AgentAutomations } from "../../components/AgentAutomations";
import { Note, SectionCard, StatCard, StatsStrip } from "../../components/kit";
import { cn } from "../../lib/utils";
import { WORKS_AT } from "./agentActions";
import {
  agentStatsApiPath,
  basisWords,
  COST_FIGURE,
  costWords,
  countWords,
  FIRST_PERIOD,
  latencyWords,
  periodOf,
  rangeWords,
  readAgentStats,
  unrecordedWhy,
  whenWords,
} from "./agentStats";

export const FIGURES_LABEL = "This agent's figures";
export const PERIOD_LABEL = "Period the figures cover";
export const RUNS_LABEL = "Runs";
export const ANSWERED_LABEL = "Answered";
export const NOTHING_RETURNED_LABEL = "Nothing returned";
export const LATENCY_LABEL = "Median time";
export const COST_LABEL = "Cost";
export const LAST_ACTIVE_LABEL = "Last active";

/** Under the nothing-returned figure: what it counts, and that it is one figure on purpose. */
export const NOTHING_RETURNED_SUB = "refused or no answer, as one figure";

export const RECENT_RUNS = "Recent runs";
export const RECENT_RUNS_NOT_YET = "a list of this agent's own runs. Its figures above are counted from them.";
export const WAITING = "Waiting on a person";
export const WAITING_NOT_YET = "approvals for one agent. Every approval you may decide is on the Approvals page.";
export const AUTOMATIONS_HEADING = "Automations";
export const OPEN_GALLERY = "Browse automations to install";

/** The periods the switch offers. The route's own two. */
const PERIODS = ["7d", "30d"] as const;

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

export function AgentDashboard({
  agentId,
  automationsAddress,
  automations,
  onAutomationsChanged,
}: {
  readonly agentId: string;
  /** The Automations section's address, or absent for a reader without that tab. */
  readonly automationsAddress?: string | undefined;
  /** This agent's installed automations, asked for by the page for a reader of that tab. */
  readonly automations?: Resource<unknown> | undefined;
  readonly onAutomationsChanged: () => void;
}) {
  const [period, setPeriod] = useState<string>(FIRST_PERIOD);
  const stats = useResource<unknown>(agentStatsApiPath(agentId));
  const read = stats.data === null ? null : readAgentStats(stats.data);
  const figures = periodOf(read, period);
  const whose = basisWords(read?.basis);
  const atLeast = read?.truncated === true ? "at least, " : "";
  const sub = whose === undefined ? undefined : `${atLeast}${whose}`;

  return (
    <div data-slot="agent-dashboard" className="flex min-w-0 flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="m-0 text-sm font-semibold text-ink">{FIGURES_LABEL}</h2>
        <PeriodSwitch period={period} onChange={setPeriod} />
      </div>
      <StatsStrip label={FIGURES_LABEL} busy={stats.busy} failure={stats.failure} count={6}>
        <StatCard label={RUNS_LABEL} value={countWords(figures?.runs)} sub={sub} />
        <StatCard label={ANSWERED_LABEL} value={countWords(figures?.answered)} sub={sub} />
        <StatCard label={NOTHING_RETURNED_LABEL} value={countWords(figures?.nothingReturned)} sub={NOTHING_RETURNED_SUB} />
        <StatCard label={LATENCY_LABEL} value={latencyWords(figures?.p50LatencyMs)} sub={sub} />
        <StatCard
          label={COST_LABEL}
          value={costWords(figures?.costMinor, read?.currency)}
          sub={basisWords(read?.costBasis)}
          unrecordedWhy={unrecordedWhy(read, COST_FIGURE)}
        />
        <StatCard label={LAST_ACTIVE_LABEL} value={whenWords(read?.lastActiveAt)} sub={whose} />
      </StatsStrip>

      <div className="mt-1 [display:grid] min-w-0 gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <SectionCard title={RECENT_RUNS} lede="Who asked, what happened and what it cost, newest first.">
          <Note kind="not-yet">{RECENT_RUNS_NOT_YET}</Note>
        </SectionCard>

        <div className="flex min-w-0 flex-col gap-4">
          <SectionCard
            title={WAITING}
            lede="Actions this agent stopped before they happened, for a person who may decide them."
            action={
              <Link to={WORKS_AT.approvals} className="inline-flex items-center gap-1 text-[12px] text-acc-text underline-offset-4 hover:underline">
                Approvals <ArrowUpRight aria-hidden className="size-3" />
              </Link>
            }
          >
            <Note kind="not-yet">{WAITING_NOT_YET}</Note>
          </SectionCard>

          {automations === undefined || automationsAddress === undefined ? null : (
            <SectionCard
              title={AUTOMATIONS_HEADING}
              lede="What this agent runs on a schedule, as the person it runs as."
              action={
                <Link to={automationsAddress} className="inline-flex items-center gap-1 text-[12px] text-acc-text underline-offset-4 hover:underline">
                  {OPEN_GALLERY} <ArrowUpRight aria-hidden className="size-3" />
                </Link>
              }
              footer={<Note kind="works">starting and stopping a schedule takes effect.</Note>}
            >
              <AgentAutomations agentId={agentId} automations={automations} onChanged={onAutomationsChanged} />
            </SectionCard>
          )}
        </div>
      </div>
    </div>
  );
}
