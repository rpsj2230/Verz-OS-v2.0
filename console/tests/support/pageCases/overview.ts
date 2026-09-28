/**
 * The page cases for `/`: the address each is mounted at and what the stand-in API answers it with.
 * `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { AUDIT, type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // The Overview, SCREEN 1: the health strip and Needs you from the overview route, the figure row
  // from the figures route, the roster and the Connectors list, and the audit log's newest page.
  // Every drawn value the API sent is the unbroken token: a part's name, a queue's name, and the
  // signed-in person's name and identifiers in Advanced.
  "/": {
    address: "/",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/me": {
        principal_id: UNBROKEN,
        display_name: UNBROKEN,
        primary_department: UNBROKEN,
        employment: "employee",
        assurance: "aal2",
        channel: "web",
        ent_hash: "f".repeat(64),
      },
      "/api/v1/console/overview": {
        as_of: "2019-03-04T12:00:00Z",
        health: {
          status: "ok",
          parts: [
            { name: "database", state: "ready", gates: true },
            { name: "cache", state: "not_configured", gates: false },
            { name: UNBROKEN, state: "ready", gates: false },
          ],
          halts: [{ scope: "department", target: UNBROKEN, since: "2019-03-04T11:30:00Z" }],
          halts_known: true,
          worker_last_seen: "2019-03-04T11:58:00Z",
          unrecorded: [{ figure: "budget_stops", why: UNBROKEN }],
        },
        needs_you: [
          { queue: "approvals", waiting: 3, at_least: false, opens: "/approvals" },
          { queue: UNBROKEN, waiting: 1, at_least: true, opens: "/access_review" },
        ],
        uncounted: [{ figure: "publish_approvals", why: UNBROKEN }],
      },
      "/api/v1/console/overview/figures": {
        range: "7d",
        since: "2019-02-25T12:00:00Z",
        until: "2019-03-04T12:00:00Z",
        basis: "everyone",
        answered: 1847,
        nothing_returned: 312,
        not_recorded: [{ figure: "cost", why: UNBROKEN }],
      },
      "/api/v1/agents": {
        items: [{ agent_id: "quote-helper", display_name: UNBROKEN, owner_id: UNBROKEN, state: "enabled" }],
        next_cursor: null,
        truncated: false,
      },
      "/api/v1/connectors": { connectors: [{ name: UNBROKEN }], unread: "" },
      "/api/v1/audit": AUDIT,
    },
  },
};
