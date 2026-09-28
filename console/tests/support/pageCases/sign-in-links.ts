/**
 * The page cases for `/sign-in-links`: the address each is mounted at and what the stand-in API
 * answers it with. `support/pageCases.ts` collects this file by its name and says what a case is
 * for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

/**
 * One link marked as the last administrator's, so the served sentence about it is drawn, and the
 * sentence about where the account is kept, both outside the table.
 */
const SIGN_IN_LINKS = {
  items: [
    {
      principal_id: UNBROKEN,
      display_name: UNBROKEN,
      department: UNBROKEN,
      linked_at: "2019-03-04T09:00:00Z",
      last_administrator: true,
      yours: false,
    },
  ],
  next_cursor: null,
  truncated: false,
  account: UNBROKEN,
  unlinking: UNBROKEN,
  last_administrator: UNBROKEN,
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/sign-in-links": {
    address: "/sign-in-links",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/govern/sign-ins": SIGN_IN_LINKS },
  },
};
