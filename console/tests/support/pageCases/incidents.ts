/**
 * The page cases for `/incidents`: the address each is mounted at and what the stand-in API answers
 * it with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

const INCIDENTS = {
  items: [
    {
      subject: UNBROKEN,
      state: "down",
      since: "2019-03-04T09:00:00Z",
      blocks: [UNBROKEN],
      blocks_unknown: "",
    },
  ],
  unread: "",
  told: UNBROKEN,
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Incidents. The list of degraded sources scrolls; what each blocks and the sentence wrap.
  "/incidents": {
    address: "/incidents",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/console/incidents": INCIDENTS },
  },
};
