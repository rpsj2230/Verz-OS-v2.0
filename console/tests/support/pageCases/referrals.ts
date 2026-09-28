/**
 * The page cases for `/referrals`: the address each is mounted at and what the stand-in API answers
 * it with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, RUNG_ID, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Referred to me. The asker's reference sits in the table, which scrolls; the state sentence
  // beside it wraps. The confirmation is held in `tests/referrals-page.test.tsx`.
  "/referrals": {
    address: "/referrals",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/me/referrals": {
        referrals: [
          {
            referral_id: RUNG_ID,
            topic: "grievance",
            label: "Grievances",
            asked_by: UNBROKEN,
            asked_at: "2019-03-04T09:00:00Z",
            handled_at: null,
            handled_by: null,
          },
        ],
      },
    },
  },
};
