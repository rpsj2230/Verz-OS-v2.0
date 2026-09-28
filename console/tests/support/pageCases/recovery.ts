/**
 * The page cases for `/recovery`: the address each is mounted at and what the stand-in API answers
 * it with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/recovery": {
    address: "/recovery",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/install/recovery": {
        rehearsal: {
          every_days: 7,
          copies_kept_days: 35,
          promised_recovery_seconds: 7200,
          manifest_ends: ".manifest.json",
          record_ends: ".drill.json",
          no_control_here: UNBROKEN,
        },
        panel: {
          profile: "standard",
          copies: [
            {
              coverage: "database",
              facts: [
                {
                  name: "database: newest copy reaches",
                  source: "measured",
                  value: UNBROKEN,
                  because: UNBROKEN,
                },
              ],
              within_objective: false,
              objective_seconds: 3600,
            },
          ],
          last_verified: {
            name: "last verified restore",
            source: "unknown",
            value: "",
            because: UNBROKEN,
          },
          measured_rto_seconds: null,
          assurance: "never verified",
          says: UNBROKEN,
          what_to_do: UNBROKEN,
          drill_is_due: true,
          // Empty, and not because the unreadable case does not matter. `ui/Notice.tsx` carries
          // `role="status"`, which is what `mount` above waits for the absence of before it
          // measures, so a page whose steady state holds a notice never settles here. The two
          // notice states on these screens are held by `tests/install-pages.test.tsx` instead.
          unreadable: [],
        },
        unread: "",
      },
    },
  },
};
