/**
 * Background jobs, on the page kit: every job the worker's schedule starts, how it last went, its
 * state, and pause, resume and run now from each row, each confirmed.
 *
 * **Each job has a page of its own** (`JobDetailPage.tsx`) with its run figures and its past runs;
 * the list names a job in words and links to it.
 *
 * **The list is answered whole, so it has no search or pager.** `brain.jobs_routes` sends every job
 * this reader may see in the registry's order and takes no question; see `parts.tsx`.
 *
 * **What was removed from the old screen.** The control identifier as the row's name (it is in the
 * job's Advanced section), the "What this screen cannot do" card and its two paragraphs (one line
 * each now), the "Paused by u_admin" principal ids (a name, or "somebody"), and the per-row
 * explanation of what each job keeps true (on the job's About view).
 *
 * Task ids: M27.8.13, M27.15.47, M27.16.1
 */

import { MoreHorizontal } from "lucide-react";
import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import { Note, type EntityColumn } from "../../components/kit";
import { Button } from "../../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../../components/ui/dropdown-menu";
import {
  ACTION_LABELS,
  actionsFor,
  CONTROLS_SWITCHED_OFF,
  everyWords,
  jobAddress,
  JOBS_API_PATH,
  JOBS_CAPTION,
  JOBS_LABEL,
  JOBS_LEDE,
  lastRunWords,
  MESSAGE_KEPT_ON_THE_SERVER,
  NEVER_SUCCEEDED,
  NO_JOBS,
  NO_JOBS_MORE,
  NO_RUN_CAN_BE_STOPPED,
  READING_JOBS,
  readJobs,
  stateWords,
  type JobAction,
  type JobRow,
} from "../jobsQuery";
import { useJobActs } from "./JobActs";
import { at, jobName, Line, OPERATIONS, OpsPage, WholeList } from "./parts";
import { JobStatePills } from "./pills";

export const JOB_COLUMN = "Job";
export const LAST_RUN_COLUMN = "Last run";
export const LAST_SUCCESS_COLUMN = "Last success";
export const STATE_COLUMN = "State";
export const EVERY_COLUMN = "Runs";

function RowMenu({
  row,
  acts,
  busy,
  onChoose,
}: {
  readonly row: JobRow;
  readonly acts: readonly JobAction[];
  readonly busy: boolean;
  readonly onChoose: (action: JobAction, row: JobRow) => void;
}) {
  const name = jobName(row.control);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" className="size-11 sm:size-8" aria-label={`Actions for ${name}`}>
          <MoreHorizontal aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuItem asChild>
          <Link to={jobAddress(row.control)}>Open</Link>
        </DropdownMenuItem>
        {acts.length === 0 ? null : <DropdownMenuSeparator />}
        {acts.map((action) => (
          <DropdownMenuItem
            key={action}
            disabled={busy}
            onSelect={() => {
              onChoose(action, row);
            }}
          >
            {ACTION_LABELS[action]}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function JobsPage() {
  const [version, setVersion] = useState(0);
  const onChanged = useCallback(() => {
    setVersion((count) => count + 1);
  }, []);
  const acts = useJobActs(onChanged);
  const answer = useResource<unknown>(JOBS_API_PATH, version);
  const body = answer.data === null ? null : readJobs(answer.data);

  return (
    <OpsPage
      crumbs={[{ label: OPERATIONS }, { label: JOBS_LABEL }]}
      title={JOBS_LABEL}
      lede={JOBS_LEDE}
      notice={
        <>
          {acts.notice}
          {acts.dialog}
        </>
      }
      loading={READING_JOBS}
      busy={answer.busy && answer.data === null}
      failure={answer.failure}
      body={body}
    >
      {(page) => {
        const columns: readonly EntityColumn<JobRow>[] = [
          {
            id: "job",
            header: JOB_COLUMN,
            hideable: false,
            cell: (row) => (
              <Link
                to={jobAddress(row.control)}
                className="font-medium text-ink underline-offset-4 hover:text-acc-text hover:underline"
              >
                {jobName(row.control)}
              </Link>
            ),
            text: (row) => jobName(row.control),
          },
          {
            id: "state",
            header: STATE_COLUMN,
            cell: (row) => <JobStatePills row={row} />,
            text: (row) => stateWords(row)
              .map((one) => one.word)
              .join("; "),
          },
          {
            id: "last_run",
            header: LAST_RUN_COLUMN,
            cell: (row) => (
              <span className="flex flex-col">
                <span>{lastRunWords(row)}</span>
                {row.last_started_at ? <span className="text-[12px] text-dim">{at(row.last_started_at)}</span> : null}
              </span>
            ),
            text: (row) => lastRunWords(row),
          },
          {
            id: "last_success",
            header: LAST_SUCCESS_COLUMN,
            cell: (row) => (row.last_succeeded_at ? at(row.last_succeeded_at) : NEVER_SUCCEEDED),
            text: (row) => (row.last_succeeded_at ? at(row.last_succeeded_at) : NEVER_SUCCEEDED),
          },
          {
            id: "every",
            header: EVERY_COLUMN,
            hidden: true,
            cell: (row) => everyWords(row.every_seconds),
            text: (row) => everyWords(row.every_seconds),
          },
        ];
        const anyFailed = page.jobs.some((row) => row.last_outcome === "failed");
        return (
          <>
            {page.may_control && !page.controls_switched_on ? <Note kind="not-yet">{CONTROLS_SWITCHED_OFF}</Note> : null}
            <WholeList
              title={JOBS_LABEL}
              caption={JOBS_CAPTION}
              columns={columns}
              rows={page.jobs}
              rowId={(row) => row.control}
              rowLabel={(row) => jobName(row.control)}
              rowActions={(row) => (
                <RowMenu
                  row={row}
                  acts={actionsFor(row, page.controls_switched_on, page.may_control)}
                  busy={acts.busy}
                  onChoose={acts.choose}
                />
              )}
              exportName="background-jobs"
              empty={NO_JOBS}
              emptyDescription={NO_JOBS_MORE}
              footer={
                <>
                  {page.no_run_can_be_stopped === false ? null : <Line>{NO_RUN_CAN_BE_STOPPED}</Line>}
                  {anyFailed ? <Line>{MESSAGE_KEPT_ON_THE_SERVER}</Line> : null}
                </>
              }
            />
          </>
        );
      }}
    </OpsPage>
  );
}
