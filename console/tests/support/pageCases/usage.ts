/**
 * The page cases for `/usage`: the address each is mounted at and what the stand-in API answers it
 * with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Usage. A department and a person's name are both values with no break in them, one in each
  // card of bars, and a model name is one too, in the tokens card.
  "/usage": {
    address: "/usage",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/report/usage": {
        start: "2019-02-26T09:00:00Z",
        end: "2019-03-05T09:00:00Z",
        departments: [{ department: UNBROKEN, questions: 3, people: 1 }],
        people: [{ person: UNBROKEN, questions: 3, name: UNBROKEN }],
        questions: 3,
        machine_included: false,
        not_measured: [],
        tokens: [
          {
            axis: "model",
            lines: [{ key: UNBROKEN, runs: 3, tokens_in: 1200, tokens_out: 300 }],
            total_runs: 3,
            total_tokens_in: 1200,
            total_tokens_out: 300,
          },
        ],
      },
    },
  },
};
