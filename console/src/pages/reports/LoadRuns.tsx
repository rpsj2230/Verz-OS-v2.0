/**
 * The peak load runs this install has kept, under the service levels they are held to (M36.2.4.3).
 *
 * **Every figure and verdict is the API's.** A run's `held` is the product's own judgement of its
 * lanes against `reliability.LANE_OBJECTIVES`, and each lane arrives with the objective that lane
 * promises, so the page sets a measured figure beside a promised one and decides neither. A run
 * smaller than the stated peak says so, because a bounded run that held is evidence the machinery
 * works and not that the peak is carried. A run names no person and no question.
 *
 * **A reader the service levels are withheld from is sent an empty list**, the same body an install
 * that has never been run sends, so this draws the same empty list for both and says nothing of why.
 *
 * Task ids: M36.2.4.3
 */

import { useResource } from "../../api/useResource";
import { EmptyList, FailureState, LoadingState, SectionCard } from "../../components/kit";
import { milliseconds, ratePercent } from "../serviceLevelsQuery";
import { Quiet } from "./reportParts";
import type { components } from "../../api/schema";

export type LoadRunsBody = components["schemas"]["LoadRunsView"];

export const LOAD_RUNS_PATH = "/report/service-levels/load-runs";
export const LOAD_RUNS_HEADING = "Peak load runs";
export const LOAD_RUNS_LEDE = "Each run of the peak load test on this install, with each lane's figures beside what it promises.";
export const LOADING_LOAD_RUNS = "Loading the peak load runs.";
export const NO_LOAD_RUNS = "No peak run has been kept";
export const HELD = "Held every objective";
export const DID_NOT_HOLD = "Did not hold every objective";
export const AT_THE_PEAK = "At the stated peak";
export const SMALLER_THAN_THE_PEAK = "Smaller than the stated peak";

/** A figure the run could not support reads "Not measured", as the lanes table does, never nought. */
const NOT_MEASURED = "Not measured";

function measured(text: string): string {
  return text === "-" ? NOT_MEASURED : text;
}

export function LoadRuns() {
  const answer = useResource<LoadRunsBody>(LOAD_RUNS_PATH);
  if (answer.failure !== null) {
    return <FailureState failure={answer.failure} />;
  }
  if (answer.data === null) {
    // Said while it is asked, so a page is not finished until this card is, and two renders of one
    // page cannot differ by whether it had arrived when they were read.
    return <LoadingState label={LOADING_LOAD_RUNS} />;
  }
  return (
    <SectionCard title={LOAD_RUNS_HEADING} lede={LOAD_RUNS_LEDE}>
      {answer.data.runs.length === 0 ? (
        <EmptyList
          compact
          title={NO_LOAD_RUNS}
          adds="A run is kept when an operator runs the peak load test on the install's server."
          by={["super_admin"]}
        />
      ) : (
        <ul data-slot="load-runs" aria-label={LOAD_RUNS_HEADING} className="m-0 flex list-none flex-col gap-4 p-0">
          {answer.data.runs.map((run) => (
            <li key={run.run_id} className="flex min-w-0 flex-col gap-1">
              <div className="flex min-w-0 flex-wrap gap-x-3 text-sm">
                <span className="font-medium">{run.held ? HELD : DID_NOT_HOLD}</span>
                <span>{run.at_stated_peak ? AT_THE_PEAK : SMALLER_THAN_THE_PEAK}</span>
                <span className="tabular-nums text-dim">
                  {run.started_at.slice(0, 10)}, sent {String(run.sent)} of {String(run.planned)}, most in flight {String(run.most_in_flight)}
                </span>
              </div>
              <ul className="m-0 flex list-none flex-col gap-0.5 p-0 text-[13px]">
                {run.lanes.map((lane) => (
                  <li key={lane.lane} className="tabular-nums">
                    {lane.lane}: p95 {measured(milliseconds(lane.p95_ms))}
                    {lane.objective_p95_ms === null ? "" : `, promised ${milliseconds(lane.objective_p95_ms)}`}; success {measured(ratePercent(lane.success_rate))}
                    {lane.objective_success_rate === null ? "" : `, promised ${ratePercent(lane.objective_success_rate)}`}
                  </li>
                ))}
              </ul>
              {run.findings.map((one) => (
                <Quiet key={one}>{one}</Quiet>
              ))}
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}
