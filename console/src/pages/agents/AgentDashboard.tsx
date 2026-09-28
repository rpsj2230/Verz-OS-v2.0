/**
 * The Dashboard view of one agent, which opens first: what it has been doing, and what is waiting.
 *
 * **The figures are the stats route's, and only what it sent.** Runs, answered, refused, cost and
 * when it was last active, over the window the route states, from `agentStats.ts`. While they are
 * on their way the strip says so; if the route fails or does not exist yet the strip draws the API's
 * sentence under "The figures could not be loaded"; a figure the body did not carry reads "Not
 * recorded yet". A number is never drawn that the route did not send.
 *
 * **Two blocks say what the page is not sent yet, rather than drawing examples.** No route lists
 * one agent's runs, and approvals carry no agent to filter by, so "Recent runs" and "Waiting on a
 * person" are notes with a link to where the company-wide list is. The design of record draws both
 * with example rows; an install shows no example.
 *
 * **Automations are live.** A reader of the Automations tab sees this agent's automations with the
 * start and stop the API offers, which is `components/AgentAutomations.tsx` unchanged, and a link
 * to the gallery.
 *
 * Task ids: M27.10.2, M39.6.1.3
 */

import { ArrowUpRight } from "lucide-react";
import { Link } from "react-router-dom";
import { useResource, type Resource } from "../../api/useResource";
import { AgentAutomations } from "../../components/AgentAutomations";
import { Note, SectionCard, StatCard, StatsStrip } from "../../components/kit";
import { WORKS_AT } from "./agentActions";
import { agentStatsApiPath, costWords, countWords, rangeWords, readAgentStats, whenWords } from "./agentStats";

export const FIGURES_LABEL = "This agent's figures";
export const RUNS_LABEL = "Runs";
export const ANSWERED_LABEL = "Answered";
export const REFUSED_LABEL = "Refused";
export const COST_LABEL = "Cost";
export const LAST_ACTIVE_LABEL = "Last active";

export const RECENT_RUNS = "Recent runs";
export const RECENT_RUNS_NOT_YET = "a list of this agent's own runs. Its figures above are counted from them.";
export const WAITING = "Waiting on a person";
export const WAITING_NOT_YET =
  "approvals for one agent. Every approval you may decide is on the Approvals page.";
export const AUTOMATIONS_HEADING = "Automations";
export const OPEN_GALLERY = "Browse automations to install";

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
  const stats = useResource<unknown>(agentStatsApiPath(agentId));
  const read = stats.data === null ? null : readAgentStats(stats.data);
  const range = rangeWords(read?.range);

  return (
    <div data-slot="agent-dashboard" className="flex min-w-0 flex-col gap-4">
      <StatsStrip label={FIGURES_LABEL} busy={stats.busy} failure={stats.failure} count={5}>
        <StatCard label={RUNS_LABEL} value={countWords(read?.runs)} sub={range} />
        <StatCard label={ANSWERED_LABEL} value={countWords(read?.answered)} sub={range} />
        <StatCard label={REFUSED_LABEL} value={countWords(read?.refused)} sub={range} />
        <StatCard label={COST_LABEL} value={costWords(read?.costMinor, read?.currency)} sub={range} />
        <StatCard label={LAST_ACTIVE_LABEL} value={whenWords(read?.lastActiveAt)} />
      </StatsStrip>

      <div className="[display:grid] min-w-0 gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
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
