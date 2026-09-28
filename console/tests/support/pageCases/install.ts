/**
 * The page cases for `/install`: the address each is mounted at and what the stand-in API answers
 * it with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // The five install screens. Each draws a value the API sent, so the unbroken identifier is on
  // every one of them: a fact's value, a release statement, a copy's timestamp, a ceiling's name
  // and a database's name are all identifiers with nowhere to break, which is the shape that
  // took three other pages past a phone's width before anybody measured.
  "/install": {
    address: "/install",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/install": {
        facts: [
          { name: "profile", source: "declared", value: "standard", because: "" },
          { name: "release", source: "measured", value: UNBROKEN, because: UNBROKEN },
        ],
      },
    },
  },
};
