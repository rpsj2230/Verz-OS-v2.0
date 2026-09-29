/**
 * The page cases for `/memory`, `/memory/:subject` and `/memory/:subject/:view`: the address each
 * is mounted at and what the stand-in API answers it with. `support/pageCases.ts` collects this file
 * by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, PERSON, UNBROKEN } from "../pageFixtures";

/** The person's own page in the directory, which names them. */
const THE_PERSON = {
  person: PERSON,
  placements: { department: null, teams: [], leads: [] },
  held: [],
  editable: false,
  may_disable: false,
  may_organise: false,
  staleness: null,
};

/** One person's memory: a statement and a diff line, each unbroken. */
const MEMORY = {
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
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Memory with nobody named asks the API nothing, so it draws no value.
  "/memory": { address: "/memory", signedIn: true, drawsValues: false, answers: {} },
  // One person's memory at Remembered. The address carries an ordinary reference, because
  // `UNBROKEN` is longer than a principal id may be and the page refuses it before asking, which is
  // correct. The person is named by their own page, and a statement is one unbroken word.
  "/memory/:subject": {
    address: "/memory/u_subject",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/govern/memory": MEMORY, "/api/v1/govern/directory/u_subject": THE_PERSON },
  },
  // Its History, whose diff line is unbroken.
  "/memory/:subject/:view": {
    address: "/memory/u_subject/history",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/govern/memory": MEMORY, "/api/v1/govern/directory/u_subject": THE_PERSON },
  },
};
