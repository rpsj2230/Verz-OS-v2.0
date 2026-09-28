/**
 * Errors, on the page kit: jobs whose run failed and questions that failed or degraded, in a
 * window the reader chooses, each list answered whole.
 *
 * **A failed question carries the gate's whole routing decision**, put into words by
 * `errorsQuery.ts`: the lane and why, the agent and how it was chosen, the tier and why, and the
 * model. The risk score and the lane asked for are columns a reader turns on; the reference, which
 * is what a person told something went wrong quotes, leads the row.
 *
 * **A list that came back full says so under it**, because a full list in a window is fewer rows
 * than the window holds, and the remedy is a shorter window.
 *
 * **What was removed.** The breadcrumb as a line of text, the "What this screen cannot show" card
 * and its paragraphs (one line each now), and the control identifiers as job names.
 *
 * Task ids: M3.4.2, M3.6.3, M27.16.1
 */

import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { useResource } from "../../api/useResource";
import { type EntityColumn } from "../../components/kit";
import {
  agentWords,
  DEFAULT_HOURS,
  ERRORS_LABEL,
  ERRORS_LEDE,
  errorsApiPath,
  FAILURE_MESSAGES_STAY_ON_THE_SERVER,
  FULL_LIST,
  JOBS_CAPTION,
  JOBS_HEADING,
  laneWords,
  LOG_IS_ON_THE_LOGS_SCREEN,
  LOGS_LINK,
  modelWords,
  NO_JOB_FAILURES,
  NO_JOB_FAILURES_MORE,
  NO_REQUEST_FAILURES,
  NO_REQUEST_FAILURES_MORE,
  NOT_SCREENED,
  PROCESS_LOG_IS_NOT_KEPT,
  READING_ERRORS,
  readErrors,
  REQUESTS_CAPTION,
  REQUESTS_HEADING,
  STATUS_WORDS,
  tierWords,
  WINDOWS,
  type ErrorsBody,
} from "../errorsQuery";
import { jobAddress } from "../jobsQuery";
import { LOGS_PATH } from "../logsQuery";
import { at, jobName, Line, OPERATIONS, OpsPage, WholeList } from "./parts";
import { RequestPill } from "./pills";

type JobFailure = ErrorsBody["jobs"][number];
type RequestFailure = ErrorsBody["requests"][number];

export const WINDOW_LABEL = "Window";

const SELECT =
  "h-11 min-w-0 max-w-full rounded-md border border-input bg-panel px-2.5 text-sm text-ink shadow-xs outline-hidden focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring sm:h-8";

function WindowChoice({ hours, onChange }: { readonly hours: number; readonly onChange: (hours: number) => void }) {
  const id = useId();
  return (
    <form
      aria-label="Choose a window"
      className="flex items-center gap-1.5"
      onSubmit={(event) => {
        event.preventDefault();
      }}
    >
      <label htmlFor={id} className="text-[12.5px] text-dim">
        {WINDOW_LABEL}
      </label>
      <select
        id={id}
        className={SELECT}
        value={hours}
        onChange={(event) => {
          onChange(Number(event.target.value));
        }}
      >
        {WINDOWS.map((one) => (
          <option key={one.hours} value={one.hours}>
            {one.label}
          </option>
        ))}
      </select>
    </form>
  );
}

const JOB_COLUMNS: readonly EntityColumn<JobFailure>[] = [
  {
    id: "job",
    header: "Job",
    hideable: false,
    cell: (row) => (
      <Link to={jobAddress(row.control)} className="font-medium text-ink underline-offset-4 hover:text-acc-text hover:underline">
        {jobName(row.control)}
      </Link>
    ),
    text: (row) => jobName(row.control),
  },
  { id: "started", header: "Started", cell: (row) => at(row.started_at), text: (row) => row.started_at },
  { id: "finished", header: "Finished", hidden: true, cell: (row) => at(row.finished_at), text: (row) => row.finished_at ?? "" },
  { id: "kind", header: "Kind of failure", cell: (row) => row.kind ?? NOT_SCREENED, text: (row) => row.kind ?? "" },
];

const REQUEST_COLUMNS: readonly EntityColumn<RequestFailure>[] = [
  {
    id: "reference",
    header: "Reference",
    hideable: false,
    cell: (row) => <code className="font-mono text-[12px]">{row.reference}</code>,
    text: (row) => row.reference,
  },
  { id: "arrived", header: "Arrived", cell: (row) => at(row.received_at), text: (row) => row.received_at },
  {
    id: "outcome",
    header: "Outcome",
    cell: (row) => <RequestPill status={row.status} words={STATUS_WORDS[row.status] ?? row.status} />,
    text: (row) => STATUS_WORDS[row.status] ?? row.status,
  },
  {
    id: "took",
    header: "Took",
    align: "end",
    cell: (row) => `${String(Math.round(row.duration_ms))} ms`,
    text: (row) => String(Math.round(row.duration_ms)),
  },
  { id: "routed", header: "Routed to", cell: (row) => laneWords(row.routed_lane, row.lane_basis), text: (row) => laneWords(row.routed_lane, row.lane_basis) },
  { id: "agent", header: "Agent", cell: (row) => agentWords(row.selected_agent, row.selection_stage), text: (row) => agentWords(row.selected_agent, row.selection_stage) },
  { id: "tier", header: "Tier", hidden: true, cell: (row) => tierWords(row.routed_tier, row.tier_basis), text: (row) => tierWords(row.routed_tier, row.tier_basis) },
  { id: "model", header: "Model", cell: (row) => modelWords(row.model, row.provider), text: (row) => modelWords(row.model, row.provider) },
  { id: "lane", header: "Lane asked", hidden: true, cell: (row) => row.lane, text: (row) => row.lane },
  {
    id: "risk",
    header: "Risk score",
    hidden: true,
    cell: (row) => (row.risk_score == null ? NOT_SCREENED : String(row.risk_score)),
    text: (row) => (row.risk_score == null ? "" : String(row.risk_score)),
  },
];

function Failures({ hours, onHours }: { readonly hours: number; readonly onHours: (hours: number) => void }) {
  const answer = useResource<unknown>(errorsApiPath(hours));
  const body = answer.data === null ? null : readErrors(answer.data);
  return (
    <OpsPage
      crumbs={[{ label: OPERATIONS }, { label: ERRORS_LABEL }]}
      title={ERRORS_LABEL}
      lede={ERRORS_LEDE}
      loading={READING_ERRORS}
      busy={answer.busy}
      failure={answer.failure}
      body={body}
      actions={<WindowChoice hours={hours} onChange={onHours} />}
    >
      {(page) => (
        <>
          <WholeList
            title={JOBS_HEADING}
            caption={JOBS_CAPTION}
            columns={JOB_COLUMNS}
            rows={page.jobs}
            rowId={(row) => `${row.control}:${row.started_at}`}
            rowLabel={(row) => jobName(row.control)}
            exportName="failed-jobs"
            empty={NO_JOB_FAILURES}
            emptyDescription={NO_JOB_FAILURES_MORE}
            footer={
              page.jobs_truncated || (page.jobs.length > 0 && page.failure_messages_stay_on_the_server !== false) ? (
                <>
                  {page.jobs_truncated ? <Line>{FULL_LIST}</Line> : null}
                  {page.jobs.length > 0 && page.failure_messages_stay_on_the_server !== false ? (
                    <Line>{FAILURE_MESSAGES_STAY_ON_THE_SERVER}</Line>
                  ) : null}
                </>
              ) : undefined
            }
          />
          <WholeList
            title={REQUESTS_HEADING}
            caption={REQUESTS_CAPTION}
            columns={REQUEST_COLUMNS}
            rows={page.requests}
            rowId={(row) => `${row.reference}:${row.received_at}`}
            rowLabel={(row) => row.reference}
            exportName="failed-questions"
            empty={NO_REQUEST_FAILURES}
            emptyDescription={NO_REQUEST_FAILURES_MORE}
            footer={page.requests_truncated ? <Line>{FULL_LIST}</Line> : undefined}
          />
          <Line>
            {page.process_log_is_not_kept === false ? (
              <>
                {LOG_IS_ON_THE_LOGS_SCREEN}{" "}
                <Link to={LOGS_PATH} className="text-acc-text underline underline-offset-4">
                  {LOGS_LINK}
                </Link>
              </>
            ) : (
              PROCESS_LOG_IS_NOT_KEPT
            )}
          </Line>
        </>
      )}
    </OpsPage>
  );
}

export function ErrorsPage() {
  const [hours, setHours] = useState(DEFAULT_HOURS);
  // Keyed by the window, so a new window starts from its own loading state rather than drawing
  // the last window's failures under the new window's name.
  return <Failures key={hours} hours={hours} onHours={setHours} />;
}
