/**
 * The page cases for `/company`: the address each is mounted at and what the stand-in API answers it
 * with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { AUDIT, type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Everything: a row's label is unbroken, and so are the department and the person offered in the
  // filters, which sit outside the table.
  "/company/estate": {
    address: "/company/estate",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/company/estate": {
        items: [{ kind: "agent", item_id: UNBROKEN, label: UNBROKEN }],
        kinds: ["agent", "skill", "knowledge", "connector"],
        departments: [UNBROKEN],
        people: [UNBROKEN],
        names: { [UNBROKEN]: UNBROKEN },
      },
    },
  },
  // Activity: the ledger's row, its actor named in the table and offered in the Person filter.
  "/company/activity": {
    address: "/company/activity",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/company/activity": {
        items: AUDIT.items,
        next_cursor: null,
        departments: [UNBROKEN],
        actors: AUDIT.actors,
        people: { [UNBROKEN]: UNBROKEN },
      },
    },
  },
  // Consumption: one department's line, whose name is unbroken, beside the company's figure.
  "/company/consumption": {
    address: "/company/consumption",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/company/consumption": {
        currency: "XXX",
        since: "2019-02-02T09:00:00Z",
        until: "2019-03-04T09:00:00Z",
        withheld: false,
        spend_minor: 700,
        by_department: [{ department: UNBROKEN, spend_minor: 700 }],
        incomplete: false,
        ceiling_set: false,
      },
    },
  },
};
