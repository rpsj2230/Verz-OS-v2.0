/**
 * The Profile view of one automation: what it is for, when it runs, whom it runs as, and the reach
 * each run was resolved at.
 *
 * **The reach is resolved at every run and kept nowhere.** A run runs at what the person it runs as
 * may read through this agent at the moment it starts, so a grant removed on Monday is absent from
 * Tuesday's run. What the page can show is whether each run's reach was the same as the run before
 * it, from the digest the run recorded; what the reach held is that person's, and is not shown here.
 *
 * **Identifiers are in Advanced and nowhere else.**
 *
 * Task ids: M27.12.3, M39.6.1.4, M27.16.1
 */

import { Advanced, Fact, FactList, Note, SectionCard } from "../../components/kit";
import { REACH_WORDS, dateWords, outcomeWords, type AutomationDetail } from "./automationsQuery";

export const DEFINITION_HEADING = "What it does";
export const SCHEDULE_HEADING = "Schedule";
export const REACH_HEADING = "Reach at each run";
export const REACH_LEDE =
  "Each run reads what the person it runs as may read through this agent when it starts. Nothing is kept between runs.";
export const NO_REACH = "No run has been resolved yet.";
export const NOT_SCHEDULED = "Not scheduled";

export function AutomationProfile({ detail }: { readonly detail: AutomationDetail }) {
  const { row } = detail;
  return (
    <div data-slot="automation-profile" className="flex min-w-0 flex-col gap-4">
      <SectionCard title={DEFINITION_HEADING}>
        <FactList>
          <Fact label="Outcome">{row.name}</Fact>
          <Fact label="If it stops">{detail.guards}</Fact>
          <Fact label="Agent">{row.agentName}</Fact>
          <Fact label="Runs as">{row.ownerName}</Fact>
          {detail.cannotRun === undefined ? null : <Fact label="Can it run here">{detail.cannotRun}</Fact>}
        </FactList>
      </SectionCard>

      <SectionCard title={SCHEDULE_HEADING}>
        <FactList>
          <Fact label="When">{row.schedule ?? NOT_SCHEDULED}</Fact>
          <Fact label="Next run">{row.nextRunAt === undefined ? NOT_SCHEDULED : dateWords(row.nextRunAt)}</Fact>
          {detail.stoppedBecause === undefined ? null : <Fact label="Why not">{detail.stoppedBecause}</Fact>}
        </FactList>
      </SectionCard>

      <SectionCard title={REACH_HEADING} lede={REACH_LEDE}>
        {detail.runs.length === 0 ? (
          <Note>{NO_REACH}</Note>
        ) : (
          <FactList>
            {detail.runs.slice(0, 10).map((run) => (
              <Fact key={run.finishedAt} label={dateWords(run.finishedAt) ?? ""}>
                {REACH_WORDS[run.reach] ?? run.reach}
                <span className="text-dim">
                  {" "}
                  ({outcomeWords(run.outcome)}
                  {run.ranAsName === "" ? "" : `, as ${run.ranAsName}`})
                </span>
              </Fact>
            ))}
          </FactList>
        )}
      </SectionCard>

      <Advanced>
        <FactList>
          <Fact label="Automation id">
            <code className="font-mono text-[12px]">{row.id}</code>
          </Fact>
          <Fact label="Task">
            <code className="font-mono text-[12px]">{detail.task}</code>
          </Fact>
          <Fact label="Template">
            <code className="font-mono text-[12px]">{detail.templateId}</code>
          </Fact>
          <Fact label="Runs as (id)">
            <code className="font-mono text-[12px]">{detail.ownerId}</code>
          </Fact>
          <Fact label="Agent id">
            <code className="font-mono text-[12px]">{row.agentId}</code>
          </Fact>
        </FactList>
      </Advanced>
    </div>
  );
}
