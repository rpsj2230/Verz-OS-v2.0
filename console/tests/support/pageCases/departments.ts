/**
 * The page cases for `/departments`: the address each is mounted at and what the stand-in API
 * answers it with. `support/pageCases.ts` collects this file by its name and says what a case is
 * for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

const DEPARTMENTS = {
  items: [
    {
      slug: UNBROKEN,
      name: UNBROKEN,
      teams: [
        {
          slug: UNBROKEN,
          name: UNBROKEN,
          members: [{ principal_id: `${UNBROKEN}1`, display_name: UNBROKEN, disabled: false }],
        },
      ],
      members: [
        { principal_id: UNBROKEN, display_name: UNBROKEN, disabled: true },
        { principal_id: `${UNBROKEN}2`, display_name: UNBROKEN, disabled: false },
      ],
      lead: { principal_id: `${UNBROKEN}1`, display_name: UNBROKEN, disabled: false },
      shapeable: true,
    },
  ],
  next_cursor: null,
  unplaced: [{ principal_id: `${UNBROKEN}0`, display_name: UNBROKEN, disabled: false, department: UNBROKEN }],
  truncated: true,
  may_organise: true,
  may_found: true,
  may_draw_scopes: true,
  staleness: null,
  teams: UNBROKEN,
  leads: UNBROKEN,
  counted: UNBROKEN,
  organising: UNBROKEN,
  shaping: UNBROKEN,
  retiring_department: UNBROKEN,
  retiring_team: UNBROKEN,
  retiring_scope: UNBROKEN,
};

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
    answers: { "/api/v1/govern/departments": DEPARTMENTS, "/api/v1/govern/scopes": DEPARTMENT_SCOPES },
  },
};
