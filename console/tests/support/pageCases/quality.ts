/**
 * The page cases for `/quality`: the address each is mounted at and what the stand-in API answers
 * it with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Quality and canaries. A run state the console has no words for is drawn as the API sent it,
  // so an unbroken one reaches the Last run figure outside any table, and the runs table inside
  // one.
  "/quality": {
    address: "/quality",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/report/quality": {
        last_canary_run: {
          started_at: "2019-03-05T06:00:00Z",
          finished_at: "2019-03-05T06:02:00Z",
          state: UNBROKEN,
        },
        canaries_owed: false,
        canaries_started: false,
        canary_interval_seconds: 43200,
        findings_are_recorded: false,
        evaluation_runs_are_recorded: false,
        runs: [
          {
            started_at: "2019-03-05T06:00:00Z",
            finished_at: "2019-03-05T06:02:00Z",
            state: UNBROKEN,
          },
        ],
        runs_truncated: false,
      },
    },
  },
};
