/**
 * The page cases for `/library`: the address each is mounted at and what the stand-in API answers
 * it with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Knowledge. The item reference is an identifier with no break in it, which is why the library
  // table sits in `.grid__scroll`; the department name is a chip outside the table and has to be
  // able to wrap. `truncated` is true so the full-page sentence is drawn as well.
  "/library": {
    address: "/library",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/govern/library": {
        items: [{ item_id: UNBROKEN, level: "department", kind: "sop" }],
        next_cursor: null,
        total: null,
        truncated: true,
        departments: [UNBROKEN],
        staleness: null,
        only_existence_and_reach_are_shown: true,
        freshness_and_use_are_not_measured: true,
      },
      // What this reader may add: the Add a document card's form is drawn from it, and the
      // department is the unbroken value a select has to hold on a phone.
      "/api/v1/knowledge/uploads/options": {
        kinds: [{ value: "sop", label: "SOP" }],
        departments: [UNBROKEN],
        personal: true,
        types: [{ media_type: "text/markdown", extensions: [".md"], max_bytes: 5242880 }],
        found_by: "text search",
        checked_by: "structural check (not an antivirus)",
      },
      // The lifecycle cards: a task that reports, a document looked after with every act offered,
      // and a solution waiting beside one captured. Each value is an unbroken token, which is what
      // a title, a principal id or a department is on a phone.
      "/api/v1/knowledge/tasks": {
        items: [
          {
            task_id: UNBROKEN,
            kind: "steward_named",
            item_id: UNBROKEN,
            says: `You are now the steward of ${UNBROKEN}.`,
            opened_at: "2019-03-04T09:00:00Z",
            due_at: null,
            closable: true,
          },
        ],
      },
      "/api/v1/knowledge/items": {
        items: [
          {
            item_id: UNBROKEN,
            title: UNBROKEN,
            kind: "sop",
            kind_label: "SOP",
            level: "department",
            department: UNBROKEN,
            steward_id: UNBROKEN,
            state: "published",
            verification: "verified",
            verified_by: UNBROKEN,
            verified_at: "2019-03-01T09:00:00Z",
            review_by: "2019-09-01T09:00:00Z",
            due: false,
            supersedes: null,
            added_at: "2019-03-01T09:00:00Z",
            you_steward: true,
            solves: null,
            promotion: null,
          },
        ],
        truncated: true,
      },
      [`/api/v1/knowledge/items/${UNBROKEN}`]: {
        document: {
          item_id: UNBROKEN,
          title: UNBROKEN,
          kind: "sop",
          kind_label: "SOP",
          level: "department",
          department: UNBROKEN,
          steward_id: UNBROKEN,
          state: "published",
          verification: "verified",
          verified_by: UNBROKEN,
          verified_at: "2019-03-01T09:00:00Z",
          review_by: "2019-09-01T09:00:00Z",
          due: false,
          supersedes: null,
          added_at: "2019-03-01T09:00:00Z",
          you_steward: true,
          solves: UNBROKEN,
          promotion: { suspension_id: UNBROKEN, status: "waiting", expires_at: "2019-03-05T09:00:00Z" },
        },
        versions: [
          {
            item_id: UNBROKEN,
            title: UNBROKEN,
            state: "published",
            level: "department",
            department: UNBROKEN,
            added_at: "2019-03-01T09:00:00Z",
            readable: true,
          },
        ],
        offered: { verify: true, new_version: true, propose: true, hand_over: true },
        promotion_waits: `Asking puts a card on the Approvals screen for ${UNBROKEN}.`,
      },
      "/api/v1/knowledge/solutions": {
        waiting: [
          {
            solution_id: UNBROKEN,
            department: UNBROKEN,
            problem: UNBROKEN,
            answer: UNBROKEN,
            conversation_ref: UNBROKEN,
            captured_by: UNBROKEN,
            captured_at: "2019-03-02T09:00:00Z",
            state: "pending",
            decided_by: null,
            decided_at: null,
            item_id: null,
          },
        ],
        yours: [
          {
            solution_id: `${UNBROKEN}2`,
            department: UNBROKEN,
            problem: UNBROKEN,
            answer: UNBROKEN,
            conversation_ref: null,
            captured_by: UNBROKEN,
            captured_at: "2019-03-02T09:00:00Z",
            state: "approved",
            decided_by: UNBROKEN,
            decided_at: "2019-03-03T09:00:00Z",
            item_id: `${UNBROKEN}2`,
          },
        ],
        departments: [UNBROKEN],
      },
    },
  },
};
