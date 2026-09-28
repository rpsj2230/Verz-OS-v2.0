/**
 * The page cases for `/departments`, `/departments/:slug` and `/departments/:slug/:view`: the
 * address each is mounted at and what the stand-in API answers it with. `support/pageCases.ts`
 * collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { DEPARTMENTS, type PageCase, UNBROKEN } from "../pageFixtures";

/** The scopes the Departments page's Scopes card lists: one it offers to retire. */
const DEPARTMENT_SCOPES = {
  items: [
    {
      slug: UNBROKEN,
      label: UNBROKEN,
      is_department: false,
      scope: { clauses: [{ field: "department", op: "eq", value: UNBROKEN }] },
    },
  ],
  next_cursor: null,
  truncated: false,
  departments: [UNBROKEN],
  staleness: null,
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Departments and teams, Access review, Elevation and Subscribers. The review and the
  // subscribers are tables, which scroll; the organisation, the landing, the filter options and
  // every served sentence are outside a table, where they must wrap. No control is pressed here:
  // the confirmation panel is held to the same rules in `tests/govern-people-pages.test.tsx`.
  "/departments": {
    address: "/departments",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/govern/departments": DEPARTMENTS },
  },
  // One department's page at its Overview, and at Scopes, which asks the scopes that name it.
  "/departments/:slug": {
    address: `/departments/${UNBROKEN}`,
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/govern/departments": DEPARTMENTS },
  },
  "/departments/:slug/:view": {
    address: `/departments/${UNBROKEN}/scopes`,
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/govern/departments": DEPARTMENTS, "/api/v1/govern/scopes": DEPARTMENT_SCOPES },
  },
};
