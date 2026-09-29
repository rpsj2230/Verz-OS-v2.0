/**
 * The page cases for `/skills`, `/skills/:name` and `/skills/:name/:view`: the address each is
 * mounted at and what the stand-in API answers it with. `support/pageCases.ts` collects this file
 * by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

/** One version in the library, with every control the Profile can draw switched on. */
const SKILL_VERSION = {
  digest: "d".repeat(64),
  name: UNBROKEN,
  version: "1.0.0",
  description: UNBROKEN,
  source: "github",
  source_location: UNBROKEN,
  source_commit: "c".repeat(40),
  source_path: UNBROKEN,
  submitted_by: UNBROKEN,
  submitted_by_name: UNBROKEN,
  submitted_at: "2019-03-04T09:00:00Z",
  review: "approved",
  reviewer: UNBROKEN,
  reviewer_name: UNBROKEN,
  reviewed_at: "2019-03-04T10:00:00Z",
  tools: [{ name: UNBROKEN, capability: UNBROKEN }],
  capabilities: [UNBROKEN],
  unregistered_tools: [],
  body: UNBROKEN,
  reviewable: false,
  assignable: true,
  edited_from: null,
  self_decided: false,
  categories: [UNBROKEN],
  diff: null,
  markdown: UNBROKEN,
  editable: true,
  retired: false,
  retired_at: null,
  retired_by: null,
  retirable: true,
  scripts: [{ path: "scripts/check.py", sha256: "e".repeat(64), text: UNBROKEN, is_text: true }],
  examples: [{ task: UNBROKEN, expected: UNBROKEN }],
  rehearsal: {
    behaved: [true],
    passed: true,
    rehearsed_at: "2019-03-04T09:30:00Z",
    rehearsed_by: UNBROKEN,
    rehearsed_by_name: UNBROKEN,
  },
  awaits_rehearsal: false,
  approval_needs: null,
  rehearsable: true,
  exportable: true,
};

const SKILLS = {
  items: [
    {
      name: UNBROKEN,
      pinned_by: [
        {
          agent_id: UNBROKEN,
          digest: "d".repeat(64),
          display_name: UNBROKEN,
          assigned_at: "2019-03-04T11:00:00Z",
          assigned_by: UNBROKEN,
        },
      ],
      versions_differ: true,
      categories: [UNBROKEN],
    },
  ],
  next_cursor: null,
  total: null,
  truncated: false,
  queue: { entries: [], waiting: 0, edits: 0, stale: 0 },
  library: [SKILL_VERSION],
  library_truncated: false,
  agents: [{ agent_id: UNBROKEN, display_name: UNBROKEN }],
  may_add: true,
  registry_is_absent: false,
  categories: [UNBROKEN],
};

/** The searchable library, one row per version (`brain.skill_routes.SkillLibraryPage`). */
const SKILL_LIBRARY = {
  items: [
    {
      digest: "d".repeat(64),
      name: UNBROKEN,
      version: "1.0.0",
      description: UNBROKEN,
      review: "pending",
      retired: true,
      categories: [UNBROKEN],
      agents_running: 2,
      source: "upload",
      submitted_at: "2019-03-04T09:00:00Z",
    },
  ],
  next_cursor: null,
  total: null,
  queue: { entries: [], waiting: 3, edits: 1, stale: 0 },
  library_truncated: false,
  truncated: false,
  may_add: true,
  categories: [UNBROKEN],
};

/** One skill's figures as `brain.console_stats_routes.SkillStatsView` sends them. */
const SKILL_STATS = {
  skill_name: UNBROKEN,
  agents_pinned: 2,
  pinned_versions: 1,
  versions: 3,
  run_basis: "everyone",
  last_used: "2019-03-04T09:00:00Z",
  at_least: false,
  periods: ["7d", "30d"].map((range) => ({
    range,
    since: "2019-02-02T00:00:00Z",
    until: "2019-03-04T12:00:00Z",
    versions_added: 1,
    runs: 6,
  })),
  unrecorded: [],
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Skills: the searchable library, one skill's Dashboard at its bare address with the figures
  // from the shared stats route, and its Profile, the view with every control on it.
  "/skills": {
    address: "/skills",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/skills/library": SKILL_LIBRARY },
  },
  "/skills/:name": {
    address: `/skills/${encodeURIComponent(UNBROKEN)}`,
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/skills": SKILLS,
      [`/api/v1/console/skills/${UNBROKEN}/stats`]: SKILL_STATS,
    },
  },
  "/skills/:name/:view": {
    address: `/skills/${encodeURIComponent(UNBROKEN)}/profile`,
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/skills": SKILLS },
  },
};
