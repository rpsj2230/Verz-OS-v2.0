/**
 * The page cases for `/rules`: the address each is mounted at and what the stand-in API answers it
 * with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: M6.5.1
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Quick answers. One rule whose question words, table and columns are each one long unbroken
  // value, so a phone's width is held against the card. Adding, trying and retiring are held in
  // `tests/rules-page.test.tsx`.
  "/rules": {
    address: "/rules",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/rules": {
        rules: [
          {
            rule_id: "acceptance_a__rate",
            department: "acceptance_a",
            template: UNBROKEN,
            slot: "name",
            source: "tables",
            entity: UNBROKEN,
            match_field: "name",
            answer_field: UNBROKEN,
            created_by: "u_admin",
            created_at: "2019-03-04T09:00:00Z",
          },
        ],
        own_department: "acceptance_a",
        may_write_install: false,
        told: "The quick answers you may change.",
      },
    },
  },
};
