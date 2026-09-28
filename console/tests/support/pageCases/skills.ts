/**
 * The page cases for `/skills` and `/skills/:name`: the address each is mounted at and what the
 * stand-in API answers it with. `support/pageCases.ts` collects this file by its name and says what
 * a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

const SKILLS = {
  items: [
    {
      name: UNBROKEN,
      pinned_by: [{ agent_id: UNBROKEN, digest: "d".repeat(64) }],
      versions_differ: true,
    },
  ],
  next_cursor: null,
  total: null,
  truncated: false,
  queue: { entries: [], waiting: 0, edits: 0, stale: 0 },
  library: [],
  library_truncated: false,
  agents: [],
  may_add: false,
  registry_is_absent: false,
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Skills, mounted twice for the people screen's reason: once from the menu and once at one
  // skill's own address, because the second draws a second list under the open skill.
  "/skills": {
    address: "/skills",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/skills": SKILLS },
  },
  "/skills/:name": {
    address: `/skills/${encodeURIComponent(UNBROKEN)}`,
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/skills": SKILLS },
  },
};
