/**
 * One background job's page, in SCREEN 14's shape: one header shared by three views, Dashboard,
 * Profile and About, each at its own address.
 *
 * **The addresses.** `/jobs/{name}` is the Dashboard; `/jobs/{name}/profile` and `/jobs/{name}/about`
 * are the other two. An address naming anything else opens the Dashboard, so an address typed to
 * probe for a view learns nothing.
 *
 * **The figures are counts of this job's own runs** (`GET /jobs/{name}`), which the reader may see
 * because they may see the job; a count of nought is a count the database made. The Dashboard lists
 * the runs themselves (`GET /jobs/{name}/runs`, M27.15.47) on the list contract: newest first,
 * searchable by report and kind of failure, filtered by outcome, and paged with no count.
 *
 * **Every act whose route exists works.** Pause, resume and run now are confirmed through
 * `JobActs.tsx`; stopping a run already going has no route and is `kit/UnavailableAction` with the
 * sentence `operationsActions.ts` gives, drawn only while a run is going (`runIsGoing`): a job with
 * no run in progress has nothing to stop, and offering to stop one read as a live button beside a
 * sentence saying it was not available. The identifier is in Advanced.
 *
 * **Nothing here decides who may see a job.** A job this reader may not see and a name nothing
 * registers are the same 404, drawn in the API's words.
 *
 * Task ids: M27.8.13, M27.15.47, M27.16.1
 */

import { Ban, IdCard, Info, LayoutDashboard } from "lucide-react";
import { useCallback, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import { FETCHING_MORE, NOTHING_MATCHES, SHOW_MORE } from "../../components/ListControls";
import {
  Advanced,
  DetailHeader,
  DetailPage,
  EmptyState,
  EntityTable,
  Fact,
  FactList,
  FailureState,
  KpiStrip,
  ListToolbar,
  LoadingState,
  Note,
  SectionCard,
  StatCard,
  UnavailableAction,
  ViewSwitch,
  type DetailView,
  type EntityColumn,
} from "../../components/kit";
import { narrows, type FilterChoice, type SortChoice } from "../../components/listing";
import { useListing } from "../../components/useListing";
import { Button } from "../../components/ui/button";
import {
  ACTION_LABELS,
  actionsFor,
  CONTROLS_SWITCHED_OFF,
  EVERY_CHANGE_IS_IN_THE_AUDIT_TRAIL,
  everyWords,
  jobAddress,
  jobApiPath,
  jobRunsApiPath,
  JOBS_LABEL,
  JOBS_PATH,
  lastRunWords,
  runIsGoing,
  MESSAGE_KEPT_ON_THE_SERVER,
  NEVER_SUCCEEDED,
  NO_RUN_CAN_BE_STOPPED,
  outcomeWords,
  periodOf,
  personWords,
  readJobDetail,
  type JobDetailBody,
  type JobRun,
} from "../jobsQuery";
import { useJobActs } from "./JobActs";
import { UNAVAILABLE } from "./operationsActions";
import { at, jobName, Line, OPERATIONS, UNREADABLE } from "./parts";
import { JobStatePills, OutcomePill } from "./pills";

/** The three views, in the owner's order. The first is where the bare address lands. */
export const VIEWS = ["dashboard", "profile", "about"] as const;
export type JobView = (typeof VIEWS)[number];

export const VIEW_LABELS: Readonly<Record<JobView, string>> = Object.freeze({
  dashboard: "Dashboard",
  profile: "Profile",
  about: "About",
});

export const VIEWS_LABEL = "Job views";
export const LOADING_JOB = "Loading this job.";
export const FIGURES_LABEL = "This job's last 30 days";
export const RUNS_LABEL = "Runs, 30 days";
export const SUCCEEDED_LABEL = "Finished";
export const FAILED_LABEL = "Failed";
export const LAST_SUCCESS_LABEL = "Last success";
export const WEEK_HEADING = "The last 7 days";

export const HISTORY_HEADING = "Run history";
export const HISTORY_LEDE = "Every run of this job, newest first.";
export const HISTORY_CAPTION = "Past runs of this job";
export const HISTORY_FILTERS = "Narrow the runs";
export const HISTORY_SEARCH = "Search reports and failures";
export const LOADING_RUNS = "Loading the runs.";
export const NO_RUNS = "No runs yet";
export const NO_RUNS_MORE = "A run appears here once the worker has started this job.";
export const HISTORY_CUT_OFF = "Only the newest runs are listed; older runs are kept on the server.";

export const STARTED_COLUMN = "Started";
export const FINISHED_COLUMN = "Finished";
export const OUTCOME_COLUMN = "Outcome";
export const SAID_COLUMN = "Report or failure";

/** Which view an address opens. Anything unknown opens the Dashboard, silently. */
export function viewFor(tab: string | undefined): JobView {
  return tab === "profile" || tab === "about" ? tab : "dashboard";
}

export function viewAddress(control: string, view: JobView): string {
  return view === VIEWS[0] ? jobAddress(control) : jobAddress(control, view);
}

const VIEW_ICONS: Readonly<Record<JobView, ReactNode>> = {
  dashboard: <LayoutDashboard aria-hidden />,
  profile: <IdCard aria-hidden />,
  about: <Info aria-hidden />,
};

export const RUN_FILTERS: readonly FilterChoice<JobRun>[] = [
  { column: "outcome", label: OUTCOME_COLUMN, everything: "Any outcome", read: (row) => row.outcome, describe: outcomeWords },
];

export const RUN_SORTS: readonly SortChoice[] = [
  { value: "", label: "Newest first" },
  { value: "started_at", label: "Oldest first" },
  { value: "outcome", label: "Outcome" },
];

function said(row: JobRun): string {
  if (row.outcome === "failed") {
    return row.failure_kind ?? "";
  }
  return row.report ?? "";
}

function RunHistory({ control }: { readonly control: string }) {
  const listing = useListing<JobRun>(jobRunsApiPath(control), { choices: RUN_FILTERS });
  const rows = listing.rows;
  const truncated =
    typeof listing.body === "object" && listing.body !== null && (listing.body as { truncated?: unknown }).truncated === true;

  const columns: readonly EntityColumn<JobRun>[] = [
    {
      id: "started",
      header: STARTED_COLUMN,
      hideable: false,
      cell: (row) => at(row.started_at),
      text: (row) => row.started_at,
    },
    {
      id: "outcome",
      header: OUTCOME_COLUMN,
      cell: (row) => <OutcomePill outcome={row.outcome} />,
      text: (row) => outcomeWords(row.outcome),
    },
    {
      id: "said",
      header: SAID_COLUMN,
      cell: (row) => said(row),
      text: (row) => said(row),
    },
    {
      id: "finished",
      header: FINISHED_COLUMN,
      hidden: true,
      cell: (row) => at(row.finished_at),
      text: (row) => row.finished_at ?? "",
    },
  ];

  let body: ReactNode;
  if (listing.failure !== null) {
    body = <FailureState failure={listing.failure} />;
  } else if (listing.busy) {
    body = <LoadingState label={LOADING_RUNS} rows={3} />;
  } else if (rows.length === 0) {
    body = narrows(listing.question) ? (
      <EmptyState title={NOTHING_MATCHES} description="Change the search or clear a filter." />
    ) : (
      <EmptyState title={NO_RUNS} description={NO_RUNS_MORE} />
    );
  } else {
    body = (
      <EntityTable
        caption={HISTORY_CAPTION}
        columns={columns}
        rows={rows}
        rowId={(row) => row.run_id}
        rowLabel={(row) => at(row.started_at)}
        exportName={`${control}-runs`}
      />
    );
  }

  return (
    <SectionCard
      title={HISTORY_HEADING}
      lede={HISTORY_LEDE}
      footer={rows.some((row) => row.outcome === "failed") || truncated ? (
        <>
          {rows.some((row) => row.outcome === "failed") ? <Line>{MESSAGE_KEPT_ON_THE_SERVER}</Line> : null}
          {truncated ? <Line>{HISTORY_CUT_OFF}</Line> : null}
        </>
      ) : undefined}
    >
      <div className="flex min-w-0 flex-col gap-3">
        <ListToolbar label={HISTORY_FILTERS} listing={listing} choices={RUN_FILTERS} sorts={RUN_SORTS} searchHint={HISTORY_SEARCH} />
        {body}
        {listing.moreFailure === null ? null : <FailureState failure={listing.moreFailure} />}
        {listing.fetchingMore ? (
          <p role="status" className="m-0 text-[12.5px] text-dim">
            {FETCHING_MORE}
          </p>
        ) : null}
        {listing.more ? (
          <div>
            <Button
              variant="outline"
              className="min-h-11 sm:min-h-9"
              disabled={listing.fetchingMore}
              onClick={() => {
                listing.showMore();
              }}
            >
              {SHOW_MORE}
            </Button>
          </div>
        ) : null}
      </div>
    </SectionCard>
  );
}

function Dashboard({ detail }: { readonly detail: JobDetailBody }) {
  const week = periodOf(detail, "7d");
  return (
    <div className="flex min-w-0 flex-col gap-4">
      {week === undefined ? null : (
        <SectionCard title={WEEK_HEADING}>
          <KpiStrip label={WEEK_HEADING} count={4}>
            <StatCard label="Runs" value={week.started.toLocaleString("en-GB")} />
            <StatCard label={SUCCEEDED_LABEL} value={week.succeeded.toLocaleString("en-GB")} />
            <StatCard label={FAILED_LABEL} value={week.failed.toLocaleString("en-GB")} />
            <StatCard label="Report only" value={week.reported_only.toLocaleString("en-GB")} />
          </KpiStrip>
        </SectionCard>
      )}
      <RunHistory control={detail.job.control} />
    </div>
  );
}

function Profile({ detail }: { readonly detail: JobDetailBody }) {
  const { job, people } = detail;
  return (
    <SectionCard title="Schedule">
      <FactList>
        <Fact label="Runs">{everyWords(job.every_seconds)}</Fact>
        <Fact label="Mode">{job.report_only ? "Report only: it says what it would do and does not do it" : "Acts"}</Fact>
        <Fact label="State">
          <JobStatePills row={job} />
        </Fact>
        <Fact label="Last run">
          {lastRunWords(job)}
          {job.last_started_at ? ` (${at(job.last_started_at)})` : ""}
        </Fact>
        <Fact label="Last report">{job.last_report ?? "None"}</Fact>
        <Fact label="Last success">{job.last_succeeded_at ? at(job.last_succeeded_at) : NEVER_SUCCEEDED}</Fact>
        {job.pause_changed_at ? (
          <Fact label={job.paused ? "Paused" : "Resumed"}>
            {`${at(job.pause_changed_at)} by ${personWords(job.pause_changed_by, people)}`}
          </Fact>
        ) : null}
        {job.run_requested_at ? (
          <Fact label="Run asked for">
            {`${at(job.run_requested_at)} by ${personWords(job.run_requested_by, people)}`}
            {job.run_pending ? ", not started yet" : ""}
          </Fact>
        ) : null}
        {job.runnable ? null : <Fact label="Cannot start yet">{job.needs ?? ""}</Fact>}
      </FactList>
    </SectionCard>
  );
}

function About({ detail }: { readonly detail: JobDetailBody }) {
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <SectionCard title="What it keeps true">
        <p className="m-0 text-sm text-ink">{detail.job.keeps_true}</p>
      </SectionCard>
      <SectionCard title="If it stops running">
        <p className="m-0 text-sm text-ink">{detail.lost_silently}</p>
      </SectionCard>
      <div className="flex flex-col gap-1.5">
        {detail.no_run_can_be_stopped === false ? null : <Note>{NO_RUN_CAN_BE_STOPPED}</Note>}
        {detail.every_change_is_in_the_audit_trail === false ? null : <Note>{EVERY_CHANGE_IS_IN_THE_AUDIT_TRAIL}</Note>}
      </div>
      <Advanced>
        <FactList>
          <Fact label="Job identifier">
            <code className="font-mono text-[12px]">{detail.job.control}</code>
          </Fact>
        </FactList>
      </Advanced>
    </div>
  );
}

export function JobDetailPage({ control, tab }: { readonly control: string; readonly tab: string | undefined }) {
  const [version, setVersion] = useState(0);
  const onChanged = useCallback(() => {
    setVersion((count) => count + 1);
  }, []);
  const acts = useJobActs(onChanged);
  const answer = useResource<unknown>(jobApiPath(control), version);
  const detail = useMemo(() => (answer.data === null ? null : readJobDetail(answer.data)), [answer.data]);
  const view = viewFor(tab);
  const name = jobName(control);
  const crumbs = [{ label: OPERATIONS }, { label: JOBS_LABEL, to: JOBS_PATH }, { label: name }];

  if (answer.failure !== null) {
    return (
      <DetailPage crumbs={crumbs} header={null}>
        <FailureState failure={answer.failure} />
      </DetailPage>
    );
  }
  if (detail === null) {
    return (
      <DetailPage crumbs={crumbs} header={null}>
        {answer.busy ? <LoadingState label={LOADING_JOB} /> : <p className="m-0 text-sm text-dim">{UNREADABLE}</p>}
      </DetailPage>
    );
  }

  const { job } = detail;
  const month = periodOf(detail, "30d");
  const views: readonly DetailView[] = VIEWS.map((one) => ({
    key: one,
    label: VIEW_LABELS[one],
    to: viewAddress(control, one),
    icon: VIEW_ICONS[one],
  }));
  const offered = actionsFor(job, detail.controls_switched_on, detail.may_control);

  return (
    <DetailPage
      crumbs={crumbs}
      header={
        <DetailHeader
          name={name}
          headingId="job-heading"
          pills={<JobStatePills row={job} />}
          subline={`${everyWords(job.every_seconds)} · last run: ${lastRunWords(job)}`}
          actions={
            <>
              {offered.map((action) => (
                <Button
                  key={action}
                  size="sm"
                  variant={action === "run" ? "default" : "outline"}
                  className="min-h-11 sm:min-h-8"
                  disabled={acts.busy}
                  onClick={() => {
                    acts.choose(action, job);
                  }}
                >
                  {ACTION_LABELS[action]}
                </Button>
              ))}
              {runIsGoing(job) ? (
                <UnavailableAction
                  label={UNAVAILABLE.stopRun.label}
                  text={UNAVAILABLE.stopRun.label}
                  icon={<Ban aria-hidden />}
                  reason={UNAVAILABLE.stopRun.reason}
                />
              ) : null}
            </>
          }
          figures={
            // A window the API sent no counts for is "Not recorded yet", never nought.
            <KpiStrip label={FIGURES_LABEL} count={4}>
              <StatCard label={RUNS_LABEL} value={month?.started.toLocaleString("en-GB")} />
              <StatCard label={SUCCEEDED_LABEL} value={month?.succeeded.toLocaleString("en-GB")} />
              <StatCard label={FAILED_LABEL} value={month?.failed.toLocaleString("en-GB")} />
              <StatCard label={LAST_SUCCESS_LABEL} value={job.last_succeeded_at ? at(job.last_succeeded_at) : NEVER_SUCCEEDED} />
            </KpiStrip>
          }
          footnote={
            detail.may_control && !detail.controls_switched_on ? <Note kind="not-yet">{CONTROLS_SWITCHED_OFF}</Note> : undefined
          }
        />
      }
      switcher={<ViewSwitch label={VIEWS_LABEL} views={views} current={view} />}
      beside={
        <Button asChild variant="ghost" size="sm" className="min-h-11 text-ink no-underline sm:min-h-8">
          <Link to={JOBS_PATH}>All jobs</Link>
        </Button>
      }
    >
      <div className="flex min-w-0 flex-col gap-4">
        {acts.notice}
        {acts.dialog}
        {view === "dashboard" ? <Dashboard detail={detail} /> : view === "profile" ? <Profile detail={detail} /> : <About detail={detail} />}
      </div>
    </DetailPage>
  );
}
