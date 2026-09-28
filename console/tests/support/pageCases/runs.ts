/**
 * The page cases for `/runs`: the address each is mounted at and what the stand-in API answers it
 * with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

/**
 * What the live runs screen is answered: one control running and one owed, each with a name and a
 * sentence that are unbreakable tokens. No refusal, because a `Notice` carries `role="status"` and
 * `mount` reads that as a page still asking.
 */
const LIVE_RUNS = {
  as_of: "2019-03-04T09:00:00Z",
  running: [
    {
      control: UNBROKEN,
      keeps_true: UNBROKEN,
      started_at: "2019-03-04T07:00:00Z",
      report_only: true,
      stalled: true,
    },
  ],
  waiting: [
    {
      control: UNBROKEN,
      keeps_true: UNBROKEN,
      due_since: "2019-03-04T06:00:00Z",
      late_by_seconds: 10800,
      first_run: false,
    },
  ],
  stalled_after_seconds: 600,
  requests_in_flight_are_not_recorded: true,
  queue_is_not_readable: true,
  no_run_can_be_stopped: true,
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/runs": {
    address: "/runs",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/operate/runs": LIVE_RUNS },
  },
};
