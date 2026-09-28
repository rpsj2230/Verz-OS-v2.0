/**
 * The page cases for `/questions`: the address each is mounted at and what the stand-in API answers
 * it with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Questions and gaps. Nothing connected, so the one-row table is drawn, and one gap line, so the
  // second is. The sentence every asker receives arrives unbroken twice: inside the table, whose
  // parent scrolls, and in the note that quotes the not-found sentence outside it, which has to be
  // able to break. The gap line's department and source are unbroken inside their own table.
  "/questions": {
    address: "/questions",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/report/questions": {
        start: "2019-02-26T09:00:00Z",
        end: "2019-03-05T09:00:00Z",
        gaps: [{ department: UNBROKEN, source: UNBROKEN, asked: 3 }],
        nothing_connected: true,
        answered_when_nothing_connected: UNBROKEN,
        answered_when_nothing_found: UNBROKEN,
        unanswered_are_recorded: false,
      },
    },
  },
};
