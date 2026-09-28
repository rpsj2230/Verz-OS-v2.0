/**
 * The page cases for `/connections`: the address each is mounted at and what the stand-in API
 * answers it with. `support/pageCases.ts` collects this file by its name and says what a case is
 * for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/connections": {
    address: "/connections",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/install/capacity": {
        memory: {
          profile: "standard",
          host_total_mib: 16000,
          declared_mib: 4000,
          deployed_mib: null,
          // Empty for the reason the recovery case above gives: a budget finding draws a notice,
          // and a notice never stops looking like a page that is still asking to `mount`.
          breaches: [],
          unbudgeted: [],
        },
        connections: [{ database: UNBROKEN, admissible: 100, demand: 60, headroom: 40 }],
      },
    },
  },
};
