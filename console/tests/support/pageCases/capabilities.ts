/**
 * The page cases for `/capabilities`: the address each is mounted at and what the stand-in API
 * answers it with. `support/pageCases.ts` collects this file by its name and says what a case is
 * for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/capabilities": {
    address: "/capabilities",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/govern/capabilities": {
        capabilities: [{ capability: UNBROKEN, description: UNBROKEN }],
        staleness: null,
      },
    },
  },
};
