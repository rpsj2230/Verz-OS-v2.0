/**
 * The page cases for `/subscribers`: the address each is mounted at and what the stand-in API
 * answers it with. `support/pageCases.ts` collects this file by its name and says what a case is
 * for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

const SUBSCRIBERS = {
  items: [
    {
      subscriber_id: UNBROKEN,
      endpoint: UNBROKEN,
      kinds: [UNBROKEN],
      active: false,
      created_by: UNBROKEN,
      last_delivered_at: null,
    },
  ],
  findings: [UNBROKEN],
  kinds: [UNBROKEN],
  staleness: null,
  stopping: UNBROKEN,
  scope: UNBROKEN,
  told: UNBROKEN,
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/subscribers": {
    address: "/subscribers",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/govern/subscribers": SUBSCRIBERS },
  },
};
