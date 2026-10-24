/**
 * The requests split between agents, on the Features page: for each run kept, who asked, how the
 * specialists were run and why not together, what each did and what it cost (M18.6.2).
 *
 * **A run is kept as how it went and never what it was about.** The row holds the coordinating
 * agent, the asker, the mode, the reasons it was not run together, and for each specialist its
 * reach's hash, a status word, its cost and its seconds. The request's words and the answers are not
 * in it, so a reader of this list learns no more than the administrator who may weigh a plan already
 * may. Costs are the product's estimates, in the install's currency.
 *
 * **Nothing here decides who may.** The route answers anybody without the authority as for a screen
 * that is not there, and a refusal is drawn as the API wrote it. Asking a coordinating agent to
 * split a request is on that agent's Profile.
 *
 * Task ids: M18.6.2
 */

import { useResource } from "../../api/useResource";
import { Chip, EmptyList, Explanation, FailureState, LoadingState, Note, SectionCard } from "../../components/kit";
import { whenWords } from "../access/formParts";
import { moneyWords } from "../spendQuery";
import {
  childWords,
  COORDINATED_RUNS_API_PATH,
  modeWords,
  readKeptCoordinatedRuns,
  whyWords,
  type KeptCoordinatedRuns,
} from "../agents/agentSpecialistsQuery";

export const COORDINATED_RUNS_TITLE = "Requests split between agents";
export const READING_COORDINATED_RUNS = "Reading the requests split so far.";
export const UNREADABLE_COORDINATED_RUNS =
  "The API answered in a shape this console does not read, so no run is listed. The console and the API are probably from different releases.";
export const NO_COORDINATED_RUNS = "No request has been split between agents";
export const NO_COORDINATED_RUNS_ADDS =
  "Allow specialists for a coordinating agent on its Profile and give it a request there, and the run is kept here.";
export const WHAT_IS_KEPT = "A run is kept as how it went, never what it was about. The costs are estimates.";

function Runs({ kept }: { readonly kept: KeptCoordinatedRuns }) {
  return (
    <>
      {kept.switched_on ? null : <Explanation form="note" act="coordination.run_switched_off" />}
      {kept.runs.length === 0 ? (
        <EmptyList title={NO_COORDINATED_RUNS} adds={NO_COORDINATED_RUNS_ADDS} by={["super_admin", "department_admin"]} />
      ) : (
        kept.runs.map((run) => (
          <SectionCard key={run.run_id} title={modeWords(run.mode)} headingLevel="h3" action={<Chip>{run.complete ? "complete" : "incomplete"}</Chip>}>
            <p className="m-0 text-[13px] text-body [overflow-wrap:anywhere]">
              {`${run.coordinator_id}, asked by ${run.asked_by}, ${whenWords(run.started_at)}. Estimated cost ${moneyWords(run.total_minor, run.currency)}.`}
            </p>
            {run.why.length === 0 ? null : (
              <p className="m-0 mt-1 text-[12.5px] text-dim">{`Not run together because ${run.why.map(whyWords).join(", and ")}.`}</p>
            )}
            <ol aria-label={`Subtasks of ${run.run_id}`} className="m-0 mt-1 flex list-none flex-col gap-0.5 p-0 text-[12.5px] text-dim">
              {run.children.map((child) => (
                <li key={child.subtask_id} className="[overflow-wrap:anywhere]">
                  {`${child.subtask_id}: ${child.callee_id}, ${childWords(child.status)}, ${child.seconds.toFixed(1)} seconds, ${moneyWords(child.cost_minor, run.currency)}`}
                </li>
              ))}
            </ol>
          </SectionCard>
        ))
      )}
      <Note>{WHAT_IS_KEPT}</Note>
    </>
  );
}

export function CoordinatedRunsPanel() {
  const answer = useResource<unknown>(COORDINATED_RUNS_API_PATH);

  let content;
  if (answer.busy) {
    content = <LoadingState label={READING_COORDINATED_RUNS} />;
  } else if (answer.failure !== null) {
    content = <FailureState failure={answer.failure} />;
  } else {
    const kept = readKeptCoordinatedRuns(answer.data);
    content = kept === null ? <Note>{UNREADABLE_COORDINATED_RUNS}</Note> : <Runs kept={kept} />;
  }
  return (
    <section data-slot="coordinated-runs-panel" aria-label={COORDINATED_RUNS_TITLE} className="flex min-w-0 flex-col gap-3">
      <h2 className="m-0 text-[15px] font-semibold">{COORDINATED_RUNS_TITLE}</h2>
      {content}
    </section>
  );
}
