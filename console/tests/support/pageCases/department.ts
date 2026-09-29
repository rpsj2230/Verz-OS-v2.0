/**
 * The page cases for `/department` and `/department/:view`: the address each is mounted at and what
 * the stand-in API answers it with. `support/pageCases.ts` collects this file by its name and says
 * what a case is for.
 *
 * Task ids: none
 */

import { departmentConsole, NAVIGATION_ADDRESS } from "../navigation";
import { DEPARTMENTS, DIRECTORY, PERSON, type PageCase, UNBROKEN } from "../pageFixtures";

/** The directory filtered to the department: one person, whose department's name is unbroken. */
const DEPARTMENT_PEOPLE = { ...DIRECTORY, items: [{ ...PERSON, department: UNBROKEN }] };

/** The scopes that name the department, for its Profile. */
const DEPARTMENT_SCOPES = {
  items: [
    {
      slug: UNBROKEN,
      label: UNBROKEN,
      is_department: true,
      scope: { clauses: [{ field: "department", op: "eq", value: UNBROKEN }] },
    },
  ],
  next_cursor: null,
  truncated: false,
  departments: [UNBROKEN],
  staleness: null,
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Department, SCREEN 2's overview, mounted as a department admin would open it: the stand-in API
  // gives a department's console, so the menu drawn above it is that console's and not the
  // company's. The Dashboard draws a value from every block: a person, an agent, a document, the
  // sentence every asker is told, and the department's name in the header.
  "/department": {
    address: "/department",
    signedIn: true,
    drawsValues: true,
    answers: {
      [NAVIGATION_ADDRESS]: departmentConsole(UNBROKEN),
      "/api/v1/govern/departments": DEPARTMENTS,
      "/api/v1/govern/directory": DEPARTMENT_PEOPLE,
      "/api/v1/report/usage": {
        start: "2019-02-26T09:00:00Z",
        end: "2019-03-05T09:00:00Z",
        departments: [{ department: UNBROKEN, questions: 3, people: 1 }],
        people: [{ person: UNBROKEN, questions: 3 }],
        questions: 3,
        machine_included: false,
        not_measured: [],
        tokens: [],
      },
      "/api/v1/agents": {
        items: [{ agent_id: "quote-helper", display_name: UNBROKEN, owner_id: UNBROKEN }],
        next_cursor: null,
        truncated: false,
      },
      "/api/v1/knowledge/documents": {
        items: [{ item_id: UNBROKEN, title: UNBROKEN, level: "department", department: UNBROKEN, state: "published", verification: "verified", due: false, you_steward: false }],
        next_cursor: null,
        total: null,
        truncated: false,
      },
      "/api/v1/report/questions": {
        start: "2019-02-26T09:00:00Z",
        end: "2019-03-05T09:00:00Z",
        gaps: [],
        nothing_connected: true,
        answered_when_nothing_connected: UNBROKEN,
        answered_when_nothing_found: UNBROKEN,
        unanswered_are_recorded: false,
      },
    },
  },
  // The Profile: the department's name, lead and teams from the Departments row, and the scopes
  // that name it.
  "/department/:view": {
    address: "/department/profile",
    signedIn: true,
    drawsValues: true,
    answers: {
      [NAVIGATION_ADDRESS]: departmentConsole(UNBROKEN),
      "/api/v1/govern/departments": DEPARTMENTS,
      "/api/v1/govern/directory": DEPARTMENT_PEOPLE,
      "/api/v1/govern/scopes": DEPARTMENT_SCOPES,
    },
  },
};
