/**
 * The page cases for `/tools` and `/tools/:name`: the address each is mounted at and what the
 * stand-in API answers it with. `support/pageCases.ts` collects this file by its name and says what
 * a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/tools": {
    address: "/tools",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/tools": {
        tools: [
          {
            name: "notes.read_note",
            source: "notes",
            description: UNBROKEN,
            entity: "note",
            capability: UNBROKEN,
            effect: "irreversible",
            side_effect: "write",
            sensitive_effect: "deletion",
            result_contract: "typed",
            identity_mode: "delegated",
            leash_at_most: "assisted",
            registered: true,
            off_for_install: {
              department: null,
              switched_off_by: UNBROKEN,
              switched_off_at: "2019-03-04T09:00:00Z",
              reason: UNBROKEN,
            },
            stopped_for: [
              { department: "web", switched_off_by: UNBROKEN, switched_off_at: "2019-03-04T09:00:00Z", reason: null },
            ],
          },
        ],
        may_switch_install: true,
        departments: ["web"],
        reason_to_switch_on: 12,
        a_switch_only_narrows: true,
        the_asker_is_never_told: true,
        every_change_is_in_the_audit_trail: true,
      },
    },
  },
  // One tool, answered from the same list: the name is the heading, the note and the capability wrap.
  "/tools/:name": {
    address: "/tools/notes.read_note",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/tools": {
        tools: [
          {
            name: "notes.read_note",
            source: "notes",
            description: UNBROKEN,
            entity: "note",
            capability: UNBROKEN,
            effect: "irreversible",
            side_effect: "write",
            sensitive_effect: "deletion",
            result_contract: "typed",
            identity_mode: "delegated",
            leash_at_most: "assisted",
            registered: true,
            off_for_install: {
              department: null,
              switched_off_by: UNBROKEN,
              switched_off_at: "2019-03-04T09:00:00Z",
              reason: UNBROKEN,
            },
            stopped_for: [
              { department: "web", switched_off_by: UNBROKEN, switched_off_at: "2019-03-04T09:00:00Z", reason: null },
            ],
          },
        ],
        may_switch_install: true,
        departments: ["web"],
        reason_to_switch_on: 12,
        a_switch_only_narrows: true,
        the_asker_is_never_told: true,
        every_change_is_in_the_audit_trail: true,
      },
    },
  },
};
