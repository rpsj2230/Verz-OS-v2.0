/**
 * The page cases for `/jobs`, `/jobs/:name` and `/jobs/:name/:view`: the address each is mounted at
 * and what the stand-in API answers it with. `support/pageCases.ts` collects this file by its name
 * and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

/** One background job as `brain.jobs_routes.JobView` sends it, every drawn value unbroken. */
const JOB_ROW = {
  control: UNBROKEN,
  keeps_true: UNBROKEN,
  every_seconds: 3600,
  destructive: false,
  report_only: true,
  runnable: false,
  needs: UNBROKEN,
  last_started_at: "2019-03-06T08:00:00Z",
  last_finished_at: "2019-03-06T08:00:02Z",
  last_outcome: "failed",
  last_report: null,
  last_failure_kind: UNBROKEN,
  last_succeeded_at: "2019-03-05T08:00:02Z",
  owed: true,
  late_by_seconds: 7200,
  paused: true,
  pause_changed_by: "u_admin",
  pause_changed_at: "2019-03-06T08:30:00Z",
  run_requested_at: "2019-03-06T08:40:00Z",
  run_requested_by: "u_admin",
  run_pending: true,
};

/** One job's page as `brain.jobs_routes.JobDetail` sends it. */
const JOB_DETAIL = {
  as_of: "2019-03-06T09:00:00Z",
  job: JOB_ROW,
  lost_silently: UNBROKEN,
  controls_switched_on: false,
  may_control: true,
  periods: ["7d", "30d"].map((range) => ({
    range,
    since: "2019-02-04T09:00:00Z",
    started: 12,
    succeeded: 9,
    failed: 2,
    reported_only: 1,
  })),
  no_run_can_be_stopped: true,
  every_change_is_in_the_audit_trail: true,
  people: { u_admin: UNBROKEN },
};

/** One page of that job's runs, as `JobRunsPage` sends it. */
const JOB_RUNS = {
  items: [
    {
      run_id: "00000000-0000-4000-8000-000000000001",
      started_at: "2019-03-06T08:00:00Z",
      finished_at: "2019-03-06T08:00:02Z",
      outcome: "failed",
      report_only: false,
      report: null,
      failure_kind: UNBROKEN,
    },
    {
      run_id: "00000000-0000-4000-8000-000000000002",
      started_at: "2019-03-05T08:00:00Z",
      finished_at: "2019-03-05T08:00:02Z",
      outcome: "ok",
      report_only: false,
      report: UNBROKEN,
      failure_kind: null,
    },
  ],
  next_cursor: null,
  truncated: false,
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Scheduled jobs. The control name, the sentence, the report and the person who paused are
  // drawn inside the scrolling table; the switched-off sentence is outside it.
  "/jobs": {
    address: "/jobs",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/jobs": {
        as_of: "2019-03-06T09:00:00Z",
        jobs: [
          {
            control: UNBROKEN,
            keeps_true: UNBROKEN,
            every_seconds: 3600,
            destructive: false,
            report_only: true,
            runnable: true,
            needs: null,
            last_started_at: "2019-03-06T08:00:00Z",
            last_finished_at: "2019-03-06T08:00:02Z",
            last_outcome: "ok",
            last_report: UNBROKEN,
            last_failure_kind: null,
            last_succeeded_at: "2019-03-06T08:00:02Z",
            owed: true,
            late_by_seconds: 7200,
            paused: true,
            pause_changed_by: UNBROKEN,
            pause_changed_at: "2019-03-06T08:30:00Z",
            run_requested_at: "2019-03-06T08:40:00Z",
            run_requested_by: UNBROKEN,
            run_pending: true,
          },
        ],
        controls_switched_on: false,
        may_control: true,
        no_run_can_be_stopped: true,
        every_change_is_in_the_audit_trail: true,
      },
    },
  },
  // One job's Dashboard: the header's figures, the week's, and the run history on the list contract.
  "/jobs/:name": {
    address: `/jobs/${UNBROKEN}`,
    signedIn: true,
    drawsValues: true,
    answers: {
      [`/api/v1/jobs/${UNBROKEN}`]: JOB_DETAIL,
      [`/api/v1/jobs/${UNBROKEN}/runs`]: JOB_RUNS,
    },
  },
  // One job's Profile: the schedule's facts, and the people named by their display names.
  "/jobs/:name/:view": {
    address: `/jobs/${UNBROKEN}/profile`,
    signedIn: true,
    drawsValues: true,
    answers: { [`/api/v1/jobs/${UNBROKEN}`]: JOB_DETAIL },
  },
};
