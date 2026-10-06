/**
 * The page cases for `/me`: the address each is mounted at and what the stand-in API answers it
 * with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // My workspace. An agent id and an item id sit in tables that scroll; a memory statement, the
  // disclosure line and every served sentence sit outside them and must wrap.
  "/me": {
    address: "/me",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/me/workspace": {
        principal_id: UNBROKEN,
        display_name: UNBROKEN,
        asked: { since: "2019-03-01T00:00:00Z", questions: 3, corrections: UNBROKEN },
        agents: [{ agent_id: UNBROKEN, provision: "provided", channels: [UNBROKEN], uses: 2 }],
        agents_used_since: "2019-02-05T00:00:00Z",
        budget: [
          {
            period: "month",
            ceiling_minor: 4000,
            spent_minor: 1000,
            headroom_minor: 3000,
            alerts_crossed: [],
          },
        ],
        budget_unread: "",
        knowledge: [{ item_id: UNBROKEN, level: "department", department: UNBROKEN }],
        knowledge_truncated: false,
        knowledge_not_shown: UNBROKEN,
        learned: [
          {
            memory_id: "m_1",
            statement: UNBROKEN,
            stated: true,
            confidence: 1,
            formed_at: "2019-02-28T00:00:00Z",
          },
        ],
        learned_undo: UNBROKEN,
        can_ask_about: UNBROKEN,
        accounts: UNBROKEN,
        staleness: null,
      },
      "/api/v1/me/channels": {
        channels: [
          { channel: "lark", bound: true, bound_at: "2019-03-01T09:00:00Z", may_bind: true },
          { channel: "webhook", bound: false, bound_at: null, may_bind: true },
        ],
        told: UNBROKEN,
      },
      "/api/v1/me/accounts": {
        accounts: [{ connector: "xero", label: UNBROKEN, connected: false, told: "" }],
        told: UNBROKEN,
      },
    },
  },
  // The undo a weekly learning digest links. It asks nothing until Undo is confirmed, and draws the
  // memory id from its own address, which must wrap.
  "/me/undo/:memoryId": {
    address: `/me/undo/${UNBROKEN}`,
    signedIn: true,
    drawsValues: true,
    answers: {},
  },
};
