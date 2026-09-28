/**
 * The page cases for `/learning`: the address each is mounted at and what the stand-in API answers
 * it with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Learning. Recorded rather than not, so all three tier tables are drawn and a memory id, a
  // department and a change kind each arrive unbroken; the change kind also sits in the four-tier
  // card outside any table.
  "/learning": {
    address: "/learning",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/govern/learning": {
        basis: "everyone",
        as_of: "2019-03-06T09:00:00Z",
        tier_one: [
          {
            memory_id: UNBROKEN,
            change: "preference",
            control_writes: "demoted",
            learned_at: "2019-03-05T09:00:00Z",
            in_effect: true,
            undo_offered: true,
          },
        ],
        tier_two: [
          {
            memory_id: `${UNBROKEN}2`,
            change: "fast_path_rule",
            evidence: [UNBROKEN],
            promote_ready: false,
            learned_at: "2019-03-05T09:00:00Z",
          },
        ],
        tier_three: [{ memory_id: `${UNBROKEN}3`, department: UNBROKEN, back_to: UNBROKEN }],
        tiers: [{ tier: 1, changes: [UNBROKEN] }],
        considered: 500,
        undo_says: { demoted: UNBROKEN, superseded: UNBROKEN },
        staleness: null,
      },
    },
  },
};
