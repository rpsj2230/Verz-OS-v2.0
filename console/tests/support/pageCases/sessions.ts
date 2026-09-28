/**
 * The page cases for `/sessions`: the address each is mounted at and what the stand-in API answers
 * it with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

/**
 * One session whose person, principal id and department are unbreakable, and the two sentences
 * the API serves beside the list, which sit outside the table and must wrap.
 */
const SESSIONS = {
  items: [
    {
      session_id: "kc-1",
      principal_id: UNBROKEN,
      display_name: UNBROKEN,
      department: UNBROKEN,
      second_factor: true,
      signed_in_at: "2019-03-04T09:00:00Z",
      lapses_at: "2019-03-04T19:00:00Z",
      yours: false,
      endable: true,
    },
  ],
  next_cursor: null,
  truncated: false,
  ending: UNBROKEN,
  appears: UNBROKEN,
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Sessions and sign-in links. Every identifier is in the table, which scrolls, and the served
  // sentences are outside it, where they must wrap. No control is pressed here: the confirmation
  // panel is held to the same rules in `tests/sessions-page.test.tsx` and
  // `tests/sign-in-links-page.test.tsx`.
  "/sessions": {
    address: "/sessions",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/govern/sessions": SESSIONS },
  },
};
