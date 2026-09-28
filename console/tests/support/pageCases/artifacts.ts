/**
 * The page cases for `/artifacts`: the address each is mounted at and what the stand-in API answers
 * it with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Artifacts. The identifiers are in the table, which scrolls; the kept rule and the hint are
  // sentences outside it and must wrap. The unread state is a sentence too and is held in
  // `tests/artifacts-page.test.tsx`.
  "/artifacts": {
    address: "/artifacts",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/govern/artifacts": {
        artifacts: [
          {
            artifact_id: UNBROKEN,
            kind: "report",
            agent_id: UNBROKEN,
            produced_for: UNBROKEN,
            produced_at: "2019-03-04T09:00:00Z",
            state: "current",
            superseded_by: "",
            run_id: UNBROKEN,
            agent_version: "3",
            kept_as: "payload",
            kept_until: "2019-04-03T09:00:00Z",
            kept_because: UNBROKEN,
          },
        ],
        unread: "",
        kept_rule: UNBROKEN,
      },
    },
  },
};
