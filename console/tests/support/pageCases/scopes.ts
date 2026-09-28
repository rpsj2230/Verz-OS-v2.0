/**
 * The page cases for `/scopes`: the address each is mounted at and what the stand-in API answers it
 * with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { DEPARTMENTS, type PageCase, UNBROKEN } from "../pageFixtures";

/** One scope, whose slug and whose clause value are both unbreakable tokens. */
const SCOPES = {
  items: [
    {
      slug: UNBROKEN,
      label: UNBROKEN,
      is_department: true,
      scope: { clauses: [{ field: "department", op: "eq", value: UNBROKEN }] },
    },
  ],
  next_cursor: null,
  total: null,
  truncated: false,
  departments: [UNBROKEN],
  staleness: null,
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/scopes": {
    address: "/scopes",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/govern/scopes": SCOPES, "/api/v1/govern/departments": DEPARTMENTS },
  },
};
