/**
 * The page cases for `/corrections`, a tab of Knowledge: the address it is mounted at and what the
 * stand-in API answers it with. `support/pageCases.ts` collects this file by its name and says what
 * a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Corrections: one waiting for this reader's decision, each value an unbroken token. The list
  // carries no words; they are read when it is opened.
  "/corrections": {
    address: "/corrections",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/knowledge/corrections": {
        items: [
          {
            candidate_id: UNBROKEN,
            item_id: UNBROKEN,
            title: UNBROKEN,
            instances: 2,
            raised_at: "2019-03-02T09:00:00Z",
          },
        ],
      },
    },
  },
};
