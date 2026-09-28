/**
 * The page cases for `/solutions`, a tab of Knowledge: the address it is mounted at and what the
 * stand-in API answers it with. `support/pageCases.ts` collects this file by its name and says what
 * a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Solutions: one waiting for this reader's decision beside one they captured, each value an
  // unbroken token, and a department they may capture in.
  "/solutions": {
    address: "/solutions",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/knowledge/solutions": {
        waiting: [
          {
            solution_id: UNBROKEN,
            department: UNBROKEN,
            problem: UNBROKEN,
            answer: UNBROKEN,
            conversation_ref: UNBROKEN,
            captured_by: UNBROKEN,
            captured_at: "2019-03-02T09:00:00Z",
            state: "pending",
            decided_by: null,
            decided_at: null,
            item_id: null,
            captured_by_name: UNBROKEN,
            decided_by_name: null,
          },
        ],
        yours: [
          {
            solution_id: `${UNBROKEN}2`,
            department: UNBROKEN,
            problem: UNBROKEN,
            answer: UNBROKEN,
            conversation_ref: null,
            captured_by: UNBROKEN,
            captured_at: "2019-03-02T09:00:00Z",
            state: "approved",
            decided_by: UNBROKEN,
            decided_at: "2019-03-03T09:00:00Z",
            item_id: `${UNBROKEN}2`,
            captured_by_name: UNBROKEN,
            decided_by_name: UNBROKEN,
          },
        ],
        departments: [UNBROKEN],
      },
    },
  },
};
