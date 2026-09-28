/**
 * The page cases for `/spend`: the address each is mounted at and what the stand-in API answers it
 * with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/spend": {
    address: "/spend",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/report/spend": {
        dimension: "department",
        built: true,
        lines: [{ key: UNBROKEN, cost_minor: 700 }],
        machine_included: false,
        total_minor: 700,
        as_of: "2019-03-04T09:00:00Z",
        freshness: "live",
      },
    },
  },
};
