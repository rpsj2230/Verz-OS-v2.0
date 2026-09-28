/**
 * The page cases for `/webhooks`: the address each is mounted at and what the stand-in API answers
 * it with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

/** Every registered route pattern, and what to mount for it. */
const WEBHOOKS = {
  manageable: true,
  vault: "unreachable",
  vault_told: UNBROKEN,
  subscribers: [
    {
      subscriber_id: UNBROKEN,
      endpoint: `https://${UNBROKEN}.example.test/`,
      kinds: ["approval.requested"],
      active: true,
      created_by: UNBROKEN,
      created_at: "2019-03-04T09:00:00Z",
      deactivated_at: null,
      last_delivered_at: null,
      secret_held: null,
      secret_written_at: null,
      deliveries: [
        {
          kind: "approval.requested",
          state: "pending",
          attempts: 0,
          occurred_at: "2019-03-04T09:00:00Z",
          last_attempt_at: null,
          reason: UNBROKEN,
          next_attempt_at: "2019-03-04T09:05:00Z",
        },
      ],
      changes: [
        {
          change: "registered",
          changed_by: UNBROKEN,
          changed_at: "2019-03-04T09:00:00Z",
          secret_written_at: null,
        },
      ],
    },
  ],
  findings: [UNBROKEN],
  kinds: ["automation.run_finished", "operation.settled", "connector.health_changed", "approval.requested"],
  delivery: UNBROKEN,
  dispatcher: {
    runs_here: true,
    paused: false,
    last_started_at: "2019-03-04T09:00:00Z",
    last_finished_at: "2019-03-04T09:00:01Z",
    last_outcome: "ok",
    last_report: UNBROKEN,
    told: UNBROKEN,
  },
  inbound: {
    channels: [
      { channel: "slack", verification: "written", check: `brain.channels.${UNBROKEN}:verify`, how: UNBROKEN },
      { channel: "lark", verification: "not_written", check: "", how: UNBROKEN },
    ],
    channels_told: UNBROKEN,
    automation_path: `/api/v1/${UNBROKEN}`,
    automation_told: UNBROKEN,
  },
  registering: UNBROKEN,
  replacing: UNBROKEN,
  switching_off: UNBROKEN,
  secret_minimum: 32,
  people: { [UNBROKEN]: UNBROKEN },
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Webhooks, the kit list: identifiers are in the table, which scrolls; the served sentences, the
  // vault's state and the findings are outside it, where they must wrap. The drawers and dialogs
  // are held in `tests/webhooks-page.test.tsx`.
  "/webhooks": {
    address: "/webhooks",
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/webhooks": WEBHOOKS },
  },
  // One subscriber's Dashboard: its figures and recent deliveries, from the list's own answer.
  "/webhooks/:id": {
    address: `/webhooks/${UNBROKEN}`,
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/webhooks": WEBHOOKS },
  },
  // One subscriber's Profile: its address, kinds, signing secret and switch.
  "/webhooks/:id/:view": {
    address: `/webhooks/${UNBROKEN}/profile`,
    signedIn: true,
    drawsValues: true,
    answers: { "/api/v1/webhooks": WEBHOOKS },
  },
};
