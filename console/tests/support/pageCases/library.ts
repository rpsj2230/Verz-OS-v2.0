/**
 * The page cases for `/library`: the Knowledge list and one document's page, the address each is
 * mounted at and what the stand-in API answers it with. `support/pageCases.ts` collects this file
 * by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

/** One document as `GET /knowledge/documents` and the detail route send it, every field filled. */
const KNOWLEDGE_DOCUMENT = {
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
  steward_name: UNBROKEN,
  verified_by_name: UNBROKEN,
};

/** One document's page as `GET /knowledge/items/{id}` sends it, with every act offered. */
const KNOWLEDGE_DETAIL = {
  document: KNOWLEDGE_DOCUMENT,
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
};

/** The reader's own knowledge task, one that reports, about the document above. */
const KNOWLEDGE_TASKS = {
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
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Knowledge, on the kit: one document with every column filled, each value an unbroken token,
  // which is what a title, a department or a steward's name is on a phone; the reader's options to
  // add, and a task that reports.
  "/library": {
    address: "/library",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/knowledge/documents": {
        items: [KNOWLEDGE_DOCUMENT],
        next_cursor: null,
        total: null,
        truncated: true,
      },
      "/api/v1/knowledge/uploads/options": {
        kinds: [{ value: "sop", label: "SOP" }],
        departments: [UNBROKEN],
        personal: true,
        types: [{ media_type: "text/markdown", extensions: [".md"], max_bytes: 5242880 }],
        found_by: "text search",
        checked_by: "structural check (not an antivirus)",
      },
      "/api/v1/knowledge/tasks": KNOWLEDGE_TASKS,
    },
  },
  // One document's Dashboard: the record with every act offered, the reader's task on it, and
  // whether the website widget answers from it, with who made it public.
  "/library/:itemId": {
    address: `/library/${UNBROKEN}`,
    signedIn: true,
    drawsValues: true,
    answers: {
      [`/api/v1/knowledge/items/${UNBROKEN}`]: KNOWLEDGE_DETAIL,
      "/api/v1/knowledge/tasks": KNOWLEDGE_TASKS,
      [`/api/v1/knowledge/items/${UNBROKEN}/public`]: {
        item_id: UNBROKEN,
        public: true,
        marked_by: UNBROKEN,
        marked_by_name: UNBROKEN,
        marked_at: "2019-03-04T09:00:00Z",
        may_change: true,
        says: null,
      },
    },
  },
  // One document's Profile: its record, the text behind a press, and Advanced. The About view reads
  // the history as well, which tests/knowledge-page.test.tsx draws.
  "/library/:itemId/:view": {
    address: `/library/${UNBROKEN}/profile`,
    signedIn: true,
    drawsValues: true,
    answers: {
      [`/api/v1/knowledge/items/${UNBROKEN}`]: KNOWLEDGE_DETAIL,
      "/api/v1/knowledge/tasks": KNOWLEDGE_TASKS,
    },
  },
};
