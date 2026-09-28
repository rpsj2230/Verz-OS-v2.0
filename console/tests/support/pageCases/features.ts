/**
 * The page cases for `/features`: the address each is mounted at and what the stand-in API answers
 * it with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/features": {
    address: "/features",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/install/features": {
        features: [
          {
            name: "schedule_control",
            title: UNBROKEN,
            what: UNBROKEN,
            while_off: UNBROKEN,
            on: true,
            read_by: [UNBROKEN],
            changed_by: UNBROKEN,
            changed_at: "2019-03-04T09:00:00Z",
          },
        ],
        components_are_chosen_by_the_profile: true,
        plugins_have_no_loader: true,
        every_change_is_in_the_audit_trail: true,
      },
    },
  },
};
