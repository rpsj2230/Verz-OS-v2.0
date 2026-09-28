/**
 * The Dashboard view of one skill, which opens first: how widely it is used and how it is changing.
 *
 * **The figures are the stats route's, and only what it sent** (`skillStats.ts`): the agents pinned
 * to it among those the reader may see, how many versions those agents run between them, how many
 * versions the library holds, the versions added and the runs that used it in the period chosen, and
 * when it was last used, labelled with whose runs they are. A figure the route did not send, or
 * lists as unrecorded, is drawn as "Not recorded yet" with the reason, never as nought, and no run
 * in the month reads as that. While the figures are on their way the strip says so; if the route
 * fails the strip draws the API's sentence.
 *
 * **What is waiting is a link to where it is decided**, the Profile, rather than a second copy of
 * the review controls.
 *
 * Task ids: M27.16.1
 */

import { ArrowUpRight } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import { Note, SectionCard, StatCard, StatsStrip } from "../../components/kit";
import { cn } from "../../lib/utils";
import { basisWords, countWords, rangeWords, whenWords } from "../agents/agentStats";
import { reviewPill } from "./skillActions";
import { type SkillDetail } from "./skillDetailQuery";
import {
  LAST_USED_FIGURE,
  readSkillStats,
  RUNS_FIGURE,
  skillPeriod,
  skillStatsApiPath,
  skillUnrecordedWhy,
} from "./skillStats";

export const FIGURES_LABEL = "This skill's figures";
export const PERIOD_LABEL = "Period the figures cover";
export const AGENTS_LABEL = "Agents using it";
export const PINNED_VERSIONS_LABEL = "Versions in use";
export const VERSIONS_LABEL = "Versions in the library";
export const ADDED_LABEL = "Versions added";
export const RUNS_LABEL = "Runs that used it";
export const LAST_USED_LABEL = "Last used";
export const NOT_USED = "None in 30 days";
export const WAITING_HEADING = "Waiting for a decision";
export const NOTHING_WAITING = "No version of this skill is waiting for review.";

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

export function SkillDashboard({ detail, profileAddress }: { readonly detail: SkillDetail; readonly profileAddress: string }) {
  const [period, setPeriod] = useState<string>("30d");
  const stats = useResource<unknown>(skillStatsApiPath(detail.name));
  const read = stats.data === null ? null : readSkillStats(stats.data);
  const figures = skillPeriod(read, period);
  const whose = basisWords(read?.runBasis);
  const atLeast = read?.atLeast === true ? "at least, " : "";
  const runsSub = whose === undefined ? undefined : `${atLeast}${whose}`;
  const lastUsed = read?.lastUsedAt === null ? NOT_USED : whenWords(read?.lastUsedAt);
  const waiting = detail.versions.filter((one) => one.review === "pending" || one.review === "changed");

  return (
    <div data-slot="skill-dashboard" className="flex min-w-0 flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="m-0 text-sm font-semibold text-ink">{FIGURES_LABEL}</h2>
        <PeriodSwitch period={period} onChange={setPeriod} />
      </div>
      <StatsStrip label={FIGURES_LABEL} busy={stats.busy} failure={stats.failure} count={6}>
        <StatCard label={AGENTS_LABEL} value={countWords(read?.agentsPinned)} sub="pinned, among the agents you can see" />
        <StatCard label={PINNED_VERSIONS_LABEL} value={countWords(read?.pinnedVersions)} sub="run by those agents" />
        <StatCard label={VERSIONS_LABEL} value={countWords(read?.versions)} />
        <StatCard label={ADDED_LABEL} value={countWords(figures?.versionsAdded)} sub={rangeWords(figures?.range)} />
        <StatCard
          label={RUNS_LABEL}
          value={countWords(figures?.runs)}
          sub={runsSub}
          unrecordedWhy={skillUnrecordedWhy(read, RUNS_FIGURE)}
        />
        <StatCard
          label={LAST_USED_LABEL}
          value={lastUsed}
          sub={whose}
          unrecordedWhy={skillUnrecordedWhy(read, LAST_USED_FIGURE)}
        />
      </StatsStrip>

      <SectionCard
        title={WAITING_HEADING}
        lede="Versions a reviewer has not decided yet."
        action={
          waiting.length === 0 ? undefined : (
            <Link to={profileAddress} className="inline-flex items-center gap-1 text-[12px] text-acc-text underline-offset-4 hover:underline">
              Review on the Profile <ArrowUpRight aria-hidden className="size-3" />
            </Link>
          )
        }
      >
        {waiting.length === 0 ? (
          <p className="m-0 text-[13px] text-dim">{NOTHING_WAITING}</p>
        ) : (
          <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-[13px] text-ink">
            {waiting.map((one) => (
              <li key={one.digest}>
                Version {one.version}: {reviewPill(one.review).toLowerCase()}
                {one.edited_from ? ", an edit" : ""}
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
      {detail.pinned?.versions_differ === true ? (
        <Note>The agents running it do not all run the same version; the Profile says which runs which.</Note>
      ) : null}
    </div>
  );
}
