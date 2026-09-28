/**
 * The page cases for `/records` and `/records/:entity`: the address each is mounted at and what the
 * stand-in API answers it with. `support/pageCases.ts` collects this file by its name and says what
 * a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/records": { address: "/records", signedIn: true, drawsValues: false, answers: {} },
  "/records/:entity": {
    address: "/records/customer_account",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/records/customer_account": {
        items: [{ id: UNBROKEN, owner: UNBROKEN }],
        next_cursor: null,
        locked: [],
        source: "a-system-of-record",
        fetched_at: "2019-03-04T09:00:00Z",
        truncated: false,
      },
    },
  },
};
