/**
 * The page cases for `/me`: the address each is mounted at and what the stand-in API answers it
 * with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

/** One artifact as the API names it, every value an unbreakable token. */
const ARTIFACT = {
  artifact_id: UNBROKEN,
  kind: UNBROKEN,
  agent_id: UNBROKEN,
  produced_for: UNBROKEN,
  produced_at: "2019-03-01T09:00:00Z",
  state: "current",
  superseded_by: "",
  run_id: UNBROKEN,
  agent_version: UNBROKEN,
  kept_as: UNBROKEN,
  kept_until: "2999-01-01T00:00:00Z",
  kept_because: UNBROKEN,
};

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
            evidence: ["you asked again in other words"],
            evidence_told: UNBROKEN,
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
      "/api/v1/me/preferences": {
        learning: { opted_out: false, cost: UNBROKEN },
        channels: [
          { channel: "lark", primary: true, chosen: true, notify: ["approval"], may_carry_an_approval: true },
          { channel: "webhook", primary: false, chosen: false, notify: [], may_carry_an_approval: false },
        ],
        primary: "lark",
        approval_route: "lark",
        approval_choices: ["lark", "console"],
        notice_kinds: ["approval", "digest"],
        quiet: { start: "22:00", end: "07:00" },
        quiet_applies_to: ["digest"],
        approvals_are_never_held: UNBROKEN,
        ignored: [],
      },
      "/api/v1/me/devices": {
        devices: [
          {
            session_id: UNBROKEN,
            channel: UNBROKEN,
            second_factor: true,
            started_at: "2019-03-01T09:00:00Z",
            expires_at: "2019-03-02T09:00:00Z",
            is_this_one: false,
          },
        ],
        more: false,
      },
      "/api/v1/me/reads": {
        reads: [{ at: "2019-03-01T09:00:00Z", actor_id: UNBROKEN, agent_id: UNBROKEN, record_kind: UNBROKEN }],
        more: false,
      },
      "/api/v1/me/artifacts": {
        artifacts: [ARTIFACT],
        more: false,
      },
      "/api/v1/me/shared": {
        items: [{ artifact: ARTIFACT, shared_by: UNBROKEN, shared_at: "2019-03-01T09:00:00Z" }],
        more: false,
      },
      "/api/v1/me/projects": {
        projects: [{ project_id: UNBROKEN, name: UNBROKEN, created_at: "2019-03-01T09:00:00Z" }],
        switched_on: true,
      },
      "/api/v1/me/shares": {
        shares: [{ artifact_id: UNBROKEN, shared_with: UNBROKEN, shared_at: "2019-03-01T09:00:00Z" }],
        more: false,
      },
      "/api/v1/me/agents/requestable": {
        agents: [{ agent_id: UNBROKEN, display_name: UNBROKEN, asked: false }],
      },
      "/api/v1/me/deletion-request": {
        may_ask: true,
        asked_at: null,
        state: "none",
        told: UNBROKEN,
        route: {
          order: [{ store: "rows", holds: UNBROKEN }],
          reaches: [{ store: "rows", holds: UNBROKEN }],
          rotates_out: [{ store: "backup", holds: UNBROKEN }],
          retained: [{ store: "ledger", holds: UNBROKEN }],
        },
      },
      "/api/v1/me/stored": {
        stores: [{ store: UNBROKEN, holds: UNBROKEN, deletion: UNBROKEN }],
        told: UNBROKEN,
      },
      "/api/v1/me/accounts": {
        accounts: [
          {
            connector: "xero",
            label: UNBROKEN,
            connected: true,
            told: "",
            provenance: "personal",
            disconnectable: true,
          },
          {
            connector: "drive",
            label: UNBROKEN,
            connected: true,
            told: UNBROKEN,
            provenance: "department",
            disconnectable: false,
          },
        ],
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
