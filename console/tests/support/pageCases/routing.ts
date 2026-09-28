/**
 * The page cases for `/routing` and `/routing/:rungId`: the address each is mounted at and what the
 * stand-in API answers it with. `support/pageCases.ts` collects this file by its name and says what
 * a case is for.
 *
 * Task ids: none
 */

import { MATRIX, type PageCase, RUNG_ID, UNBROKEN } from "../pageFixtures";

/**
 * The matrix gate's two answers on the Routing screen: one held change with its failing case, and
 * one golden question, whose question, asker and case id are tokens with nowhere to break.
 */
const ROUTING_CHANGES = {
  items: [
    {
      id: "22222222-2222-4222-8222-222222222222",
      kind: "edit",
      status: "held",
      rung_id: RUNG_ID,
      proposed: {},
      failing: [{ case: UNBROKEN, reason: UNBROKEN }],
      reasons: [UNBROKEN],
      quality_share: 0.5,
      proposed_by: UNBROKEN,
      decided_at: "2019-03-04T09:00:00Z",
      rung: null,
    },
  ],
};

const GOLDEN_QUESTIONS = {
  items: [
    {
      id: "33333333-3333-4333-8333-333333333333",
      question: UNBROKEN,
      asked_as: UNBROKEN,
      asked_as_name: UNBROKEN,
      expect: "refuse",
      created_by: UNBROKEN,
    },
  ],
};

/** The people a golden question may be asked as, whose one name is a token with nowhere to break. */
const GOLDEN_ASKERS = { items: [{ id: "u_asker", name: UNBROKEN }], truncated: false };

export const PAGES: Readonly<Record<string, PageCase>> = {
  "/routing": {
    address: "/routing",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/routing/rungs": MATRIX,
      "/api/v1/routing/changes": ROUTING_CHANGES,
      "/api/v1/routing/golden-questions": GOLDEN_QUESTIONS,
      "/api/v1/routing/golden-questions/askers": GOLDEN_ASKERS,
    },
  },
  "/routing/:rungId": {
    address: `/routing/${RUNG_ID}`,
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/routing/rungs": MATRIX,
      "/api/v1/routing/changes": ROUTING_CHANGES,
      "/api/v1/routing/golden-questions": GOLDEN_QUESTIONS,
    },
  },
};
