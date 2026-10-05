/**
 * The page cases for `/people`, `/people/:personId` and `/people/:personId/:view`: the address each
 * is mounted at and what the stand-in API answers it with. `support/pageCases.ts` collects this
 * file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { DIRECTORY, type PageCase, PERSON, UNBROKEN } from "../pageFixtures";

/** One person's page: a direct grant and a pack, a team and a lead, and every sentence served. */
const PERSON_DETAIL = {
  person: PERSON,
  placements: {
    department: { slug: UNBROKEN, name: UNBROKEN },
    teams: [{ department: UNBROKEN, slug: UNBROKEN, name: UNBROKEN }],
    leads: [{ slug: UNBROKEN, name: UNBROKEN }],
  },
  held: [
    {
      kind: "grant",
      row_id: "11111111-1111-4111-8111-000000000001",
      capabilities: [UNBROKEN],
      pack: null,
      pack_label: null,
      pack_version: null,
      scope: { clauses: [{ field: "department", op: "eq", value: UNBROKEN }] },
      scope_slug: UNBROKEN,
      scope_label: UNBROKEN,
      granted_by: "p_2",
      granted_by_name: UNBROKEN,
      reason: UNBROKEN,
      granted_at: "2019-03-04T09:00:00Z",
      not_after: "2999-03-04T09:00:00Z",
    },
    {
      kind: "pack",
      row_id: "11111111-1111-4111-8111-000000000002",
      capabilities: [UNBROKEN],
      pack: UNBROKEN,
      pack_label: UNBROKEN,
      pack_version: 2,
      scope: { clauses: [{ field: "department", op: "eq", value: UNBROKEN }] },
      scope_slug: null,
      scope_label: null,
      granted_by: "p_2",
      granted_by_name: null,
      reason: UNBROKEN,
      granted_at: "2019-03-04T09:00:00Z",
      not_after: null,
    },
  ],
  editable: true,
  may_disable: true,
  may_organise: true,
  disabling: UNBROKEN,
  from_a_pack: UNBROKEN,
  staleness: null,
};

/**
 * The People screen's Data steward card with nobody appointed, so its form is drawn. Sentences
 * rather than tokens, because the card draws the API's sentences and never an identifier.
 */
const NO_STEWARD = {
  appointed: false,
  principal_id: null,
  display_name: null,
  told: "No data steward is appointed.",
  appointing_another: "They are granted the reads of every connected source.",
  appointing_yourself: "Your account then holds both.",
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  // People: the directory of every person, and one person's page at its Overview and at the Access
  // view, which asks the most routes. Every value is a token with nowhere to break.
  "/people": {
    address: "/people",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/govern/directory": DIRECTORY, "/api/v1/govern/data-steward": NO_STEWARD },
  },
  "/people/:personId": {
    address: "/people/p_1",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/govern/directory/p_1": PERSON_DETAIL,
      "/api/v1/agents": {
        items: [{ agent_id: "quote-helper", display_name: UNBROKEN, owner_id: "p_1", state: "enabled" }],
        next_cursor: null,
        truncated: false,
      },
      "/api/v1/govern/staff_sources/transfers": { transfers: [] },
    },
  },
  "/people/:personId/:view": {
    address: "/people/p_1/access",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/govern/directory/p_1": PERSON_DETAIL,
      "/api/v1/govern/roles/holders": {
        items: [
          {
            id: "g-1",
            principal_id: "p_1",
            display_name: UNBROKEN,
            role: "department_admin",
            scope: { clauses: [{ field: "department", op: "eq", value: UNBROKEN }] },
            deputy_of: null,
            granted_by: "p_2",
            granted_at: "2019-03-04T09:00:00Z",
            not_after: null,
          },
        ],
        editable: true,
      },
      // The agents a run can be previewed through, the reader's own roster, with a name that has
      // nowhere to break.
      "/api/v1/agents": { items: [{ agent_id: "quote-helper", display_name: UNBROKEN, owner_id: UNBROKEN }], truncated: false },
    },
  },
};
