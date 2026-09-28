/**
 * The page cases for `/*`: the address each is mounted at and what the stand-in API answers it
 * with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import type { PageCase } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/*": { address: "/no/such/page", signedIn: true, drawsValues: false, answers: {} },
};
