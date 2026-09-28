/**
 * The page cases for `/service-levels`: the address each is mounted at and what the stand-in API
 * answers it with. `support/pageCases.ts` collects this file by its name and says what a case is
 * for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // The three Report screens. Each draws a table of figures beside a key that can be an
  // unbroken identifier, which is the shape that took five views off the side of a phone
  // before `.grid__scroll` existed: the table scrolls and the document does not.
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
