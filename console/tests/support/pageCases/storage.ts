/**
 * The page cases for `/storage`: the address each is mounted at and what the stand-in API answers
 * it with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

const STORAGE = {
  buckets: [
    {
      name: UNBROKEN,
      holds: UNBROKEN,
      retention_days: 30,
      retention_reason: UNBROKEN,
      versioned: false,
      public_read: false,
      kinds: [UNBROKEN],
    },
  ],
  findings: [UNBROKEN],
  endpoint: { address: `http://${UNBROKEN}:8333`, prefix: UNBROKEN, from_default: false, told: UNBROKEN },
  connection: UNBROKEN,
  usage: UNBROKEN,
  names: UNBROKEN,
  retention: UNBROKEN,
  read_at: "2019-03-04T09:00:00Z",
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Storage. The bucket table scrolls; the address, the prefix and the sentences wrap.
  "/storage": {
    address: "/storage",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/storage": STORAGE },
  },
};
