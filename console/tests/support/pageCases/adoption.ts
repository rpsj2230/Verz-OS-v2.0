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
      // The coverage statement: a connected department drawn in its widest values, one with nothing
      // connected and nothing to suggest, and an action for the champion.
      "/api/v1/report/coverage": {
        switched_on: true,
        lines: [
          {
            department: UNBROKEN,
            source: UNBROKEN,
            source_label: UNBROKEN,
            state: "connected",
            state_words: "Connected",
            records: 120,
            last_sync: "2019-03-04T09:30:00Z",
          },
          {
            department: `${UNBROKEN}q`,
            source: UNBROKEN,
            source_label: UNBROKEN,
            state: "not_connected",
            state_words: "Not connected",
            records: null,
            last_sync: null,
          },
        ],
        shopping: [
          {
            department: `${UNBROKEN}q`,
            source: UNBROKEN,
            source_label: UNBROKEN,
            need: "authorise_the_source",
            words: "Authorise this source so the department can ask about it",
          },
        ],
        note: "Sources that answer to the whole organisation rather than to one department are listed on the Connectors screen and are not counted in a department's line.",
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
