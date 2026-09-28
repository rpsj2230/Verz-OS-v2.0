/**
 * The page cases for `/updates`: the address each is mounted at and what the stand-in API answers
 * it with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/updates": {
    address: "/updates",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/install/updates": {
        running: {
          tag: "",
          facts: [{ name: "built commit", source: "measured", value: UNBROKEN, because: UNBROKEN }],
          cannot_say: UNBROKEN,
        },
        told: null,
        unanswered: {
          why: "no release list is configured",
          detail: UNBROKEN,
          at: "2019-03-04T09:00:00Z",
        },
        standing: "unknown running",
        says: UNBROKEN,
        what_to_do: UNBROKEN,
        told_days_ago: null,
        goes_off_after_days: 30,
      },
    },
  },
};
