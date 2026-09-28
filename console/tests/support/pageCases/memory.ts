/**
 * The page cases for `/memory` and `/memory/:subject`: the address each is mounted at and what the
 * stand-in API answers it with. `support/pageCases.ts` collects this file by its name and says what
 * a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Memory with nobody named asks the API nothing, so it draws no value.
  "/memory": { address: "/memory", signedIn: true, drawsValues: false, answers: {} },
  // One person's memory. The address carries an ordinary reference, because `UNBROKEN` is longer
  // than a principal id may be and the page refuses it before asking, which is correct. The API's
  // own values are unbroken: the reference it echoes is drawn in the card's heading outside any
  // table, a statement may be one unbroken word, and the history table holds a memory id and a
  // diff line inside `.grid__scroll`.
  "/memory/:subject": {
    address: "/memory/u_subject",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/govern/memory": {
        subject_id: UNBROKEN,
        curated: [
          {
            memory_id: UNBROKEN,
            statement: UNBROKEN,
            confidence: 0.9,
            formed_at: "2019-03-05T09:00:00Z",
          },
        ],
        extracted: [],
        history: [
          {
            memory_id: UNBROKEN,
            replaced_id: `${UNBROKEN}0`,
            at: "2019-03-05T09:00:00Z",
            diff: [`+${UNBROKEN}`],
            trigger: null,
            correction: null,
          },
        ],
        considered_per_kind: 200,
        staleness: null,
        edit_is_not_writable: true,
      },
    },
  },
};
