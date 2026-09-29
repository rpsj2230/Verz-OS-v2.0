/**
 * The page cases for `/channels`: the address each is mounted at and what the stand-in API answers
 * it with. `support/pageCases.ts` collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

/** One channel on the module list as `brain.binding_routes.ChannelRowView` sends it. */
const CHANNEL_ROW = {
  channel: "webhook",
  label: UNBROKEN,
  receives: true,
  status: "on",
  secret: "held",
  health: "working",
  last_delivered_at: "2019-03-04T09:00:00Z",
  events_path: `/api/v1/channels/webhook/${UNBROKEN}`,
  events_address: "",
  steps: [],
  tenant_fields: ["reply_url"],
  tenant: { reply_url: UNBROKEN },
  changed_at: "2019-03-04T09:00:00Z",
  changed_by: UNBROKEN,
  changed_by_name: UNBROKEN,
};

/** A channel this release does not receive on, never set up. */
const CHANNEL_ROW_SLACK = {
  channel: "slack",
  label: "Slack",
  receives: false,
  status: "not_set_up",
  secret: "none",
  health: "not_set_up",
  last_delivered_at: null,
  events_path: "",
  events_address: "",
  steps: [],
  tenant_fields: [],
  tenant: {},
  changed_at: null,
  changed_by: null,
  changed_by_name: null,
};

/** One channel's figures as `brain.console_stats_routes.ChannelStatsView` sends them. */
const CHANNEL_STATS = {
  channel: "webhook",
  bound_people: 3,
  bound_basis: "everyone",
  last_event: "2019-03-04T09:00:00Z",
  at_least: false,
  periods: ["7d", "30d"].map((range) => ({
    range,
    since: "2019-02-02T00:00:00Z",
    until: "2019-03-04T12:00:00Z",
    received: 12,
    sent: 11,
    failed: 1,
    unknown: 0,
    refused_inbound: 2,
  })),
  unrecorded: [{ figure: "answers", why: UNBROKEN }],
};

/** What a channel declares and how it is doing, as `ChannelHealthView` sends it. */
const CHANNEL_HEALTH = {
  channel: "webhook",
  receives: true,
  features: ["cards", "ephemeral"],
  max_classification: "confidential",
  can_carry_label: true,
  verbs: ["invoke", "read"],
  rooms: "as_nothing",
  rooms_told: UNBROKEN,
  health: "working",
  told: UNBROKEN,
  last_received_at: "2019-03-04T09:00:00Z",
  last_sent_at: "2019-03-04T09:00:00Z",
  last_fault: null,
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Channels, the kit list: one channel this release receives on, set up and switched on, and one
  // it does not, with the bound people figure from the stats route for the one it receives on.
  "/channels": {
    address: "/channels",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/console/channels": { items: [CHANNEL_ROW, CHANNEL_ROW_SLACK], next_cursor: null },
      "/api/v1/console/channels/webhook/stats": CHANNEL_STATS,
    },
  },
  // One channel's Dashboard: the header's figures, the stats strip, the health sentence and the
  // bound people on the list contract, each named and never shown by id.
  "/channels/:name": {
    address: "/channels/webhook",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/console/channels/webhook": CHANNEL_ROW,
      "/api/v1/channels/webhook/health": CHANNEL_HEALTH,
      "/api/v1/console/channels/webhook/stats": CHANNEL_STATS,
      "/api/v1/channels/webhook/bindings": {
        channel: "webhook",
        items: [{ principal_id: UNBROKEN, display_name: UNBROKEN, bound_at: "2019-03-04T09:00:00Z" }],
        next_cursor: null,
        truncated: false,
        told: UNBROKEN,
      },
    },
  },
  // One channel's Profile: where its vendor posts, the set-up form with its identifiers and the
  // write-only secret, and the test message form.
  "/channels/:name/:view": {
    address: "/channels/webhook/profile",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/console/channels/webhook": CHANNEL_ROW,
      "/api/v1/channels/webhook/health": CHANNEL_HEALTH,
    },
  },
};
