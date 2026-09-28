/**
 * The page cases for `/agent-templates`: the address each is mounted at and what the stand-in API
 * answers it with. `support/pageCases.ts` collects this file by its name and says what a case is
 * for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // The catalogue. Its widest values are a template slug and the publisher's principal id,
  // which are both identifiers, and the summary is a sentence the API wrote.
  "/agent-templates": {
    address: "/agent-templates",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/agent-templates": {
        items: [
          {
            template_id: UNBROKEN,
            version: 2,
            display_name: UNBROKEN,
            summary: UNBROKEN,
            published_by: UNBROKEN,
            origin: "built_in",
          },
        ],
        next_cursor: null,
        total: null,
        truncated: false,
      },
    },
  },
};
