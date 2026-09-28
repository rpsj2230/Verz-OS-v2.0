/**
 * The page cases for `/access-requests`: the address each is mounted at and what the stand-in API
 * answers it with. `support/pageCases.ts` collects this file by its name and says what a case is
 * for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/access-requests": {
    address: "/access-requests",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/access-requests": {
        items: [
          {
            request_id: UNBROKEN,
            asker_id: UNBROKEN,
            subject: UNBROKEN,
            question: UNBROKEN,
            requested_capability: UNBROKEN,
            requested_at: "2019-03-04T09:00:00Z",
          },
        ],
        next_cursor: null,
        total: null,
        truncated: true,
      },
    },
  },
};
