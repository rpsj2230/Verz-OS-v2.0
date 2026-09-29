/**
 * The page cases for `/adoption`: the address each is mounted at and what the stand-in API answers
 * it with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/adoption": {
    address: "/adoption",
    signedIn: true,
    drawsValues: true,
    answers: {
      // The figures and the quiet departments are the usage report's, over the same period: one
      // department asked and one did not, so the quiet card draws an unbroken name outside a table.
      "/api/v1/report/usage": {
        start: "2019-02-26T09:00:00Z",
        end: "2019-03-05T09:00:00Z",
        departments: [
          { department: UNBROKEN, questions: 12, people: 3 },
          { department: `${UNBROKEN}q`, questions: 0, people: 0 },
        ],
        people: [{ person: UNBROKEN, questions: 12, name: UNBROKEN }],
        questions: 12,
        machine_included: false,
        not_measured: [],
        tokens: [],
      },
      "/api/v1/report/adoption": {
        items: [{ department: UNBROKEN, questions: 12, people: 3 }],
        next_cursor: null,
        total: null,
        truncated: false,
      },
    },
  },
};
