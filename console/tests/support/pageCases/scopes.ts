/**
 * The page cases for `/scopes`: the address each is mounted at and what the stand-in API answers it
 * with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, SCOPES } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/scopes": {
    address: "/scopes",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/govern/scopes": SCOPES },
  },
};
