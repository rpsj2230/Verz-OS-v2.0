/**
 * The page cases for `/access_review`: the address each is mounted at and what the stand-in API
 * answers it with. `support/pageCases.ts` collects this file by its name and says what a case is
 * for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

const ACCESS_REVIEW = {
  items: [
    {
      kind: "pack",
      row_id: UNBROKEN,
      principal_id: UNBROKEN,
      display_name: UNBROKEN,
      department: UNBROKEN,
      capabilities: [UNBROKEN],
      pack: UNBROKEN,
      scope: { clauses: [{ field: "department", op: "eq", value: UNBROKEN }] },
      granted_by: UNBROKEN,
      reason: UNBROKEN,
      granted_at: "2019-03-04T09:00:00Z",
      lapses_at: null,
      last_decision: "keep",
      last_decided_by: UNBROKEN,
      last_decided_at: "2019-04-01T09:00:00Z",
    },
  ],
  next_cursor: null,
  truncated: true,
  shows: UNBROKEN,
  keeping: UNBROKEN,
  removing: UNBROKEN,
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/access_review": {
    address: "/access_review",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/govern/access-review": ACCESS_REVIEW },
  },
};
