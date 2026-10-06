/**
 * The page cases for `/roles`: the address each is mounted at and what the stand-in API answers it
 * with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { DIRECTORY, type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/roles": {
    address: "/roles",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/govern/roles": {
        roles: [
          {
            role: UNBROKEN,
            exists_to: UNBROKEN,
            typical_count: UNBROKEN,
            scope_required: true,
          },
        ],
        holders_are_not_recorded_yet: true,
      },
      // The Approver flag and the synced roles carry an id only, so the page asks the directory for names.
      "/api/v1/govern/directory": DIRECTORY,
      "/api/v1/govern/roles/holders": {
        items: [{ id: "g-1", principal_id: UNBROKEN, display_name: UNBROKEN, role: "auditor", scope: null, deputy_of: null, not_after: null }],
        editable: true,
      },
      // A nomination waiting for this reader, each value a token with nowhere to break.
      "/api/v1/govern/roles/nominations": {
        deciding: [
          {
            id: "n-1",
            principal_id: UNBROKEN,
            display_name: UNBROKEN,
            role: "auditor",
            scope_slug: null,
            nominated_by: UNBROKEN,
            reason: UNBROKEN,
            created_at: "2019-03-04T09:00:00Z",
            outcome: null,
            decided_by: null,
            decided_at: null,
          },
        ],
        mine: [],
      },
      "/api/v1/govern/roles/misconfigurations": {
        items: [{ principal_id: "u_2", kind: "role_without_capability", sentence: UNBROKEN }],
      },
      "/api/v1/govern/roles/group-rules": {
        rules: [
          {
            id: "r-1",
            idp_group: UNBROKEN,
            role: "auditor",
            scope: null,
            created_by: UNBROKEN,
            created_at: "2019-03-04T09:00:00Z",
          },
        ],
        synced: [
          {
            principal_id: UNBROKEN,
            role: "auditor",
            source_group: UNBROKEN,
            first_seen_at: "2019-03-04T09:00:00Z",
            last_seen_at: "2019-03-04T09:00:00Z",
          },
        ],
        editable: true,
      },
    },
  },
};
