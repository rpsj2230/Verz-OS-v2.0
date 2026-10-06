/**
 * The page cases for `/stop`: the address each is mounted at and what the stand-in API answers it
 * with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * One department is stopped, so the page draws a resume form before the stop form, and the agent
 * axis is named as one nothing asks yet.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/stop": {
    address: "/stop",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/halts": {
        known: true,
        halts: [
          {
            scope: "department",
            target: UNBROKEN,
            declared_by: "u_admin",
            at: "2019-03-06T09:00:00Z",
            reason: "Stopped from the console Stop control",
          },
        ],
        gaps: [],
        not_asked_yet: ["agent"],
        may_stop_everything: true,
      },
    },
  },
};
