/**
 * The page cases for `/packs`: the address each is mounted at and what the stand-in API answers it
 * with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Packs, with one pack whose capabilities and names are tokens, and the controls a writer is offered.
  "/packs": {
    address: "/packs",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/govern/packs": {
        packs: [{ slug: UNBROKEN, label: UNBROKEN, capabilities: [UNBROKEN], version: 3 }],
        may_write: true,
        versioning: UNBROKEN,
        retiring: UNBROKEN,
      },
    },
  },
};
