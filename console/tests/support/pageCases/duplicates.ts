/**
 * The page cases for `/duplicates`: the address each is mounted at and what the stand-in API
 * answers it with. `support/pageCases.ts` collects this file by its name and says what a case is
 * for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Possible duplicates. One pair with a long label on each side and a long line of evidence, and a
  // waiting fit whose lines and crossings are long too, so a phone's width is held against both
  // cards. The decision and the promote are held in `tests/resolution-review-page.test.tsx`.
  "/duplicates": {
    address: "/duplicates",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/resolution/review": {
        cards: [
          {
            item_id: "rev_0123456789abcdef0123456789abcdef",
            left: { source: "hubspot", entity: "hubspot_company", label: UNBROKEN },
            right: { source: "xero", entity: "contact", label: UNBROKEN },
            lines: [UNBROKEN],
            why: UNBROKEN,
            origin: "held",
            state: "open",
            raised_at: "2019-03-04T09:00:00Z",
            weight_version: "declared-1",
            calibrated: false,
          },
        ],
        by_strongest: { decisive: 1, strong: 0, supporting: 0, weak: 0, against: 0 },
      },
      "/api/v1/resolution/weights": {
        in_force: "declared",
        calibrated: false,
        candidate: UNBROKEN,
        lines: [UNBROKEN, "phone stayed weak"],
        crossings: [UNBROKEN],
      },
    },
  },
};
