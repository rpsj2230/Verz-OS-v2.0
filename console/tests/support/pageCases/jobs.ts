/**
 * The page cases for `/jobs`: the address each is mounted at and what the stand-in API answers it
 * with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

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
};
