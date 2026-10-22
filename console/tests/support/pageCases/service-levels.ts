/**
 * The page cases for `/service-levels`: the address each is mounted at and what the stand-in API
 * answers it with. `support/pageCases.ts` collects this file by its name and says what a case is
 * for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Service levels. The lane is unbroken in the answer-time bars, outside any table, and in the
  // lanes table beside an unbroken shortfall.
  "/service-levels": {
    address: "/service-levels",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/report/service-levels": {
        start: "2019-03-04T09:00:00Z",
        end: "2019-03-05T09:00:00Z",
        lanes: [
          {
            lane: UNBROKEN,
            objective_p95_ms: 2000,
            objective_success_rate: 0.99,
            p95_ms: 1200,
            success_rate: 0.995,
            requests: 40,
            met: true,
            shortfalls: [UNBROKEN],
          },
        ],
      },
      // The peak runs kept on the install, one with a lane whose name is unbroken.
      "/api/v1/report/service-levels/load-runs": {
        runs: [
          {
            run_id: "r1",
            started_at: "2019-03-04T09:00:00Z",
            commit: "abc1234",
            profile: "check",
            seconds_run: 1,
            planned: 80,
            sent: 80,
            not_sent: 0,
            most_in_flight: 9,
            at_stated_peak: false,
            held: true,
            interactive_shed: 0,
            lanes: [
              { lane: UNBROKEN, requests: 40, p95_ms: 12, success_rate: 1, shed: 0, objective_p95_ms: 500, objective_success_rate: 0.995 },
            ],
            findings: [UNBROKEN],
          },
        ],
      },
    },
  },
};
