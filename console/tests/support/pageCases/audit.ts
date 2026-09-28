/**
 * The page cases for `/audit`: the address each is mounted at and what the stand-in API answers it
 * with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { AUDIT, type PageCase } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Audit. The actor is drawn twice, in the table and as an option in the Who filter, and the
  // option is the one outside anything that scrolls. The history card is not opened here; it is
  // the same table shape and is held in `tests/audit-page.test.tsx`.
  "/audit": {
    address: "/audit",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/audit": AUDIT },
  },
};
