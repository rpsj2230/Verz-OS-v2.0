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
    },
  },
};
