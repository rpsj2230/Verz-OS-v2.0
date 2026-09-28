/**
 * The page cases for `/limits`: the address each is mounted at and what the stand-in API answers it
 * with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/limits": {
    address: "/limits",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/install/limits": {
        ceilings: [{ name: UNBROKEN, per_day: 5000, raisable: true, derived: false }],
        throttled: [
          { scope: "principal", subject: UNBROKEN, limit: 60, retry_after_seconds: 12 },
        ],
        unread: "",
      },
    },
  },
};
