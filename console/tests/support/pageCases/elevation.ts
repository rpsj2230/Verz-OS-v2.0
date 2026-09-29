/**
 * The page cases for `/elevation`: the address each is mounted at and what the stand-in API answers
 * it with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

const ELEVATION = {
  prompt: UNBROKEN,
  holds_nothing_standing: false,
  may_authorise: true,
  reasons: [UNBROKEN],
  longest_hours: 4,
  items: [
    {
      request_id: UNBROKEN,
      principal_id: UNBROKEN,
      display_name: UNBROKEN,
      department: UNBROKEN,
      capability: UNBROKEN,
      scope_slug: UNBROKEN,
      reason: UNBROKEN,
      explanation: UNBROKEN,
      hours: 2,
      requested_at: "2019-03-04T09:00:00Z",
      state: "pending",
      decided_by: null,
      decided_at: null,
      lapses_at: null,
      decidable: true,
    },
  ],
  next_cursor: null,
  truncated: true,
  what: UNBROKEN,
  recorded: UNBROKEN,
  notified: UNBROKEN,
  authorising: UNBROKEN,
  people: { [UNBROKEN]: UNBROKEN },
};

/** The break-glass notices addressed to the reader, with the names of the people on them. */
const NOTICES = {
  items: [
    {
      session_id: "s-1",
      principal_id: UNBROKEN,
      authorised_by: UNBROKEN,
      reason: "lockout",
      lapses_at: "2019-03-04T13:00:00Z",
      told_at: "2019-03-04T09:00:00Z",
    },
  ],
  people: { [UNBROKEN]: UNBROKEN },
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/elevation": {
    address: "/elevation",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/govern/elevation": ELEVATION,
      "/api/v1/govern/elevation/notices": NOTICES,
    },
  },
  // One request's page asks the same list for it by id.
  "/elevation/:requestId": {
    address: "/elevation/11111111-2222-3333-4444-555555555555",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/govern/elevation": ELEVATION },
  },
};
