/**
 * The page cases for `/requirement-checks`: the address each is mounted at and what the stand-in
 * API answers it with. `support/pageCases.ts` collects this file by its name and says what a case
 * is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

const REQUIREMENT_CHECKS = {
  areas: [
    { area: "Permissions", proves: "M1.8.8", requirements: 2, passed: 1, failed: 0, unchecked: 1 },
    { area: "Models", proves: "M5.6.5", requirements: 1, passed: 0, failed: 0, unchecked: 1 },
  ],
  area: "Permissions",
  requirements: [
    {
      id: "ARC-A-001",
      requirement: UNBROKEN,
      source: UNBROKEN,
      latest: {
        requirement_id: "ARC-A-001",
        outcome: "passed",
        checked_by: "u_admin",
        checked_at: "2019-03-04T09:00:00Z",
        release_commit: "a".repeat(40),
        note: UNBROKEN,
      },
    },
    { id: "DEC-30", requirement: UNBROKEN, source: UNBROKEN, latest: null },
  ],
  release_commit: "a".repeat(40),
  told: UNBROKEN,
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Requirement checks. The requirements table scrolls; the areas, the served sentence and the form
  // sit outside it.
  "/requirement-checks": {
    address: "/requirement-checks",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/requirements/checks": REQUIREMENT_CHECKS },
  },
};
