/**
 * The page cases for `/channels`: the address each is mounted at and what the stand-in API answers
 * it with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Channels. Identifiers, a bound person's id and a delivery sit in lists and definition rows that
  // must wrap. One channel this release receives on, set up and switched on, and one it does not,
  // so every part a card can draw is on the page. The confirmations are held in
  // `tests/channels-page.test.tsx`.
  "/channels": {
    address: "/channels",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/channels": {
        channels: [
          {
            channel: "slack",
            receives: false,
            events_path: "",
            tenant_fields: [],
            configured: false,
            enabled: false,
            tenant: {},
            secret_held: null,
            updated_by: null,
            updated_at: null,
          },
          {
            channel: "webhook",
            receives: true,
            events_path: "/api/v1/channels/webhook/events",
            tenant_fields: ["reply_url"],
            configured: true,
            enabled: true,
            tenant: { reply_url: UNBROKEN },
            secret_held: true,
            updated_by: UNBROKEN,
            updated_at: "2019-03-04T09:00:00Z",
          },
        ],
        told: UNBROKEN,
      },
      "/api/v1/channels/slack/health": {
        channel: "slack",
        receives: false,
        features: ["cards", "ephemeral"],
        max_classification: "confidential",
        can_carry_label: true,
        health: "not_set_up",
        told: UNBROKEN,
        last_received_at: null,
        last_sent_at: null,
        last_fault: null,
      },
      "/api/v1/channels/webhook/health": {
        channel: "webhook",
        receives: true,
        features: [],
        max_classification: "internal",
        can_carry_label: true,
        health: "failing",
        told: UNBROKEN,
        last_received_at: "2019-03-04T09:00:00Z",
        last_sent_at: "2019-03-04T09:01:00Z",
        last_fault: {
          direction: "outbound",
          outcome: "refused",
          reason: "vendor_refused",
          vendor_status: 403,
          recorded_at: "2019-03-04T09:02:00Z",
        },
      },
      "/api/v1/channels/webhook/bindings": {
        channel: "webhook",
        items: [{ principal_id: UNBROKEN, display_name: UNBROKEN, bound_at: "2019-03-01T09:00:00Z" }],
        next_cursor: null,
        truncated: false,
        told: UNBROKEN,
      },
      "/api/v1/channels/webhook/deliveries": {
        channel: "webhook",
        deliveries: [
          {
            direction: "inbound",
            outcome: "accepted",
            reason: null,
            vendor_status: null,
            recorded_at: "2019-03-04T09:00:00Z",
          },
        ],
      },
    },
  },
};
