/**
 * Runs and queue, on the page kit: the scheduled jobs running now and the ones owed a run, each
 * named in words and linked to its job's page.
 *
 * **Two lists answered whole, and what neither can list said in one line each.** Questions and
 * agent runs are recorded when they finish, the queue's own tables are closed to the application,
 * and nothing can stop a run that has started; each line is gated on the field the API sends, so it
 * leaves the page the day it stops being true. See `liveRunsQuery.ts`.
 *
 * **Nothing here decides who may see a run.** A reader holding neither screen's grant is answered two
 * empty lists, which is what an install running nothing is answered, and the empty sentences say
 * nothing about grants.
 *
 * **What was removed.** The control identifiers as the rows' names, the "What this screen cannot
 * show" card and its three paragraphs, and the "What it keeps true" column (on each job's page).
 *
 * Task ids: M27.2.2, M27.2.6, M27.16.1
 */

import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import { Note, type EntityColumn } from "../../components/kit";
import { jobAddress } from "../jobsQuery";
import {
  ACTING,
  durationWords,
  FIRST_RUN,
  LIVE_RUNS_API_PATH,
  LIVE_RUNS_LABEL,
  LIVE_RUNS_LEDE,
  LOADING_RUNS,
  NO_RUN_CAN_BE_STOPPED,
  NOTHING_RUNNING,
  NOTHING_RUNNING_MORE,
  NOTHING_WAITING,
  NOTHING_WAITING_MORE,
  QUEUE_IS_NOT_READABLE,
  readLiveRuns,
  REPORT_ONLY,
  REQUESTS_IN_FLIGHT_ARE_NOT_RECORDED,
  RUNNING_CAPTION,
  RUNNING_HEADING,
  runningFor,
  stalledNote,
  WAITING_CAPTION,
  WAITING_HEADING,
  type OwedControl,
  type RunningControl,
} from "../liveRunsQuery";
import { at, jobName, OPERATIONS, OpsPage, WholeList } from "./parts";
import { ModePill } from "./pills";

function JobLink({ control }: { readonly control: string }) {
  return (
    <Link to={jobAddress(control)} className="font-medium text-ink underline-offset-4 hover:text-acc-text hover:underline">
      {jobName(control)}
    </Link>
  );
}

export function LiveRunsPage() {
  const answer = useResource<unknown>(LIVE_RUNS_API_PATH);
  const body = answer.data === null ? null : readLiveRuns(answer.data);

  return (
    <OpsPage
      crumbs={[{ label: OPERATIONS }, { label: LIVE_RUNS_LABEL }]}
      title={LIVE_RUNS_LABEL}
      lede={LIVE_RUNS_LEDE}
      loading={LOADING_RUNS}
      busy={answer.busy}
      failure={answer.failure}
      body={body}
    >
      {(page) => {
        const running: readonly EntityColumn<RunningControl>[] = [
          { id: "job", header: "Job", hideable: false, cell: (row) => <JobLink control={row.control} />, text: (row) => jobName(row.control) },
          { id: "started", header: "Started", cell: (row) => at(row.started_at), text: (row) => row.started_at },
          {
            id: "for",
            header: "Running for",
            cell: (row) => (
              <span className="flex flex-col gap-0.5">
                <span>{runningFor(row.started_at, page.as_of)}</span>
                {row.stalled ? <span className="text-[12px] text-warn">{stalledNote(page.stalled_after_seconds)}</span> : null}
              </span>
            ),
            text: (row) => runningFor(row.started_at, page.as_of),
          },
          {
            id: "mode",
            header: "Mode",
            cell: (row) => <ModePill reportOnly={row.report_only} acting={ACTING} reporting={REPORT_ONLY} />,
            text: (row) => (row.report_only ? REPORT_ONLY : ACTING),
          },
        ];
        const waiting: readonly EntityColumn<OwedControl>[] = [
          { id: "job", header: "Job", hideable: false, cell: (row) => <JobLink control={row.control} />, text: (row) => jobName(row.control) },
          { id: "since", header: "Owed since", cell: (row) => at(row.due_since), text: (row) => row.due_since },
          {
            id: "late",
            header: "Late by",
            cell: (row) => (row.first_run ? FIRST_RUN : durationWords(row.late_by_seconds)),
            text: (row) => (row.first_run ? FIRST_RUN : durationWords(row.late_by_seconds)),
          },
        ];
        return (
          <>
            <WholeList
              title={RUNNING_HEADING}
              caption={RUNNING_CAPTION}
              columns={running}
              rows={page.running}
              rowId={(row) => row.control}
              rowLabel={(row) => jobName(row.control)}
              exportName="running-now"
              empty={NOTHING_RUNNING}
              emptyDescription={NOTHING_RUNNING_MORE}
            />
            <WholeList
              title={WAITING_HEADING}
              caption={WAITING_CAPTION}
              columns={waiting}
              rows={page.waiting}
              rowId={(row) => row.control}
              rowLabel={(row) => jobName(row.control)}
              exportName="waiting"
              empty={NOTHING_WAITING}
              emptyDescription={NOTHING_WAITING_MORE}
            />
            <div className="flex flex-col gap-1.5">
              {page.requests_in_flight_are_not_recorded === false ? null : <Note>{REQUESTS_IN_FLIGHT_ARE_NOT_RECORDED}</Note>}
              {page.queue_is_not_readable === false ? null : <Note>{QUEUE_IS_NOT_READABLE}</Note>}
              {page.no_run_can_be_stopped === false ? null : <Note>{NO_RUN_CAN_BE_STOPPED}</Note>}
            </div>
          </>
        );
      }}
    </OpsPage>
  );
}
