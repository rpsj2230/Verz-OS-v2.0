/**
 * The page cases for `/connectors`, `/connectors/:connector` and `/connectors/:connector/:view`:
 * the address each is mounted at and what the stand-in API answers it with. `support/pageCases.ts`
 * collects this file by its name and says what a case is for.
 *
 * Task ids: none
 */

import { type PageCase, UNBROKEN } from "../pageFixtures";

/** One source's figures as `brain.console_stats_routes.ConnectorStatsView` sends them. */
const CONNECTOR_STATS = {
  connector: "xero",
  health: "ok",
  last_attempt: "2019-03-04T09:30:00Z",
  last_read_to_the_end: "2019-03-04T09:30:00Z",
  consecutive_failures: 0,
  index_ids: 1234,
  live_read_basis: "everyone",
  last_live_read: "2019-03-04T09:00:00Z",
  at_least: false,
  periods: ["7d", "30d"].map((range) => ({
    range,
    since: "2019-02-02T00:00:00Z",
    until: "2019-03-04T12:00:00Z",
    attempts: 24,
    read_to_the_end: 22,
    failures: 2,
    quota_waits: 0,
    live_reads: 5,
  })),
  unrecorded: [],
};

/** One source on the Connectors list, every drawn value the unbroken token. */
const CONNECTOR_ROW = {
  name: "xero",
  label: UNBROKEN,
  status: "connected",
  health: "ok",
  department: UNBROKEN,
  last_read_at: "2019-03-04T09:30:00Z",
  connected_at: "2019-03-04T09:00:00Z",
  declaration_changed: true,
  connect_from: "console",
  may_manage: true,
};

/** One source's page, with the widest values the page draws: settings, index fields and history. */
const CONNECTOR_SOURCE = {
  source: CONNECTOR_ROW,
  elsewhere: "",
  reading: UNBROKEN,
  ceiling: UNBROKEN,
  recorded: UNBROKEN,
  department_says: "",
  settings: [{ name: "tenant_id", label: UNBROKEN, value: UNBROKEN }],
  keeps: [{ entity: UNBROKEN, fields: [UNBROKEN] }],
  reads_live: [{ tool: UNBROKEN, entity: UNBROKEN, description: UNBROKEN }],
  history: [
    {
      connected_at: "2019-03-04T09:00:00Z",
      connected_by: UNBROKEN,
      disconnected_at: null,
      disconnected_by: null,
      settings: [{ name: "tenant_id", label: UNBROKEN, value: UNBROKEN }],
    },
  ],
  people: { [UNBROKEN]: UNBROKEN },
  agents: [{ agent_id: "quote-helper", display_name: UNBROKEN }],
  skills: [{ name: UNBROKEN, version: "1.0.0", state: "approved" }],
  confirm_edit: UNBROKEN,
  confirm_key: UNBROKEN,
};

/** A source's newest connection test, as `brain.connector_routes.ConnectorProbeView` sends it. */
const CONNECTOR_PROBE = {
  connector: "xero",
  requested_at: "2019-03-04T10:00:00Z",
  pending: false,
  verdict: "failed",
  tested_at: "2019-03-04T10:00:40Z",
  health: "down",
  said: UNBROKEN,
  confirm: UNBROKEN,
};

/** The Connectors screen's own read, which the list's connect drawer and a source's page use. */
const CONNECTORS_SCREEN = {
  connectors: [
    {
      name: UNBROKEN,
      connected_by: UNBROKEN,
      connected_at: "2019-03-04T09:00:00Z",
      key_held: true,
      key_written_at: "2019-03-04T09:00:05Z",
      pinned: true,
      declaration: UNBROKEN,
      may_disconnect: true,
      last_synced_at: "2019-03-04T09:00:00Z",
      next_sync_at: "2019-03-04T10:00:00Z",
      sync: UNBROKEN,
      trust: {
        name: UNBROKEN,
        wiring: "rest",
        credential: `Held in the vault since it was connected. ${UNBROKEN}`,
        budget: `60 requests a minute. ${UNBROKEN}`,
        projected_fields: 9,
        checked_at: "2019-03-04T09:00:00Z",
        health: "ok",
        lifecycle: "registered",
        serving: false,
        version: "1.0.0",
        reaches: `Reaches view ${UNBROKEN}, and nothing else in the source.`,
        access: UNBROKEN,
        permission_sync: UNBROKEN,
      },
    },
  ],
  unread: "",
  connecting: UNBROKEN,
  confirm_connect: UNBROKEN,
  confirm_disconnect: UNBROKEN,
  copy_policy: [{ what: UNBROKEN, verdict: "projected", why: UNBROKEN }],
  budget_unread: UNBROKEN,
  may_connect: true,
  vault: "ready",
  vault_told: "",
  connectable: [
    {
      name: UNBROKEN,
      label: UNBROKEN,
      settings: [{ name: "tenant_id", label: UNBROKEN, hint: UNBROKEN, max_chars: 200, blank: `Give the ${UNBROKEN}.` }],
      credential_label: UNBROKEN,
      credential_hint: UNBROKEN,
      may_connect: true,
    },
  ],
  not_connectable: [{ name: UNBROKEN, label: UNBROKEN, why: UNBROKEN }],
  evidence: [
    {
      name: UNBROKEN,
      label: UNBROKEN,
      recorded: UNBROKEN,
      credential: UNBROKEN,
      live_read: UNBROKEN,
      last_read_live_at: null,
    },
  ],
  key_max_chars: 1000,
  key_blank: "Paste the key the source issued for this connection.",
};

/** The same screen with its one connection named for the source a page case opens, so the page
 * draws what it draws for a connected source: its figures, its test and what the test found. */
const XERO_CONNECTED = {
  ...CONNECTORS_SCREEN,
  connectors: CONNECTORS_SCREEN.connectors.map((one) => ({ ...one, name: "xero" })),
};

export const PAGES: Readonly<Record<string, PageCase>> = {
  // Connectors, the list of every source on the page kit: the list route, each connected row's
  // figures from the shared stats route, and the Connectors screen's own read, which the connect
  // drawer and the copy policy come from. Every drawn value is the unbroken token.
  "/connectors": {
    address: "/connectors",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/console/connectors": { items: [CONNECTOR_ROW], next_cursor: null, total: null },
      "/api/v1/console/connectors/xero/stats": CONNECTOR_STATS,
      // Connect Lark's guide, every drawn value the unbroken token.
      "/api/v1/connectors/lark-app": {
        uses: [
          {
            name: "staff_list",
            label: UNBROKEN,
            what: UNBROKEN,
            scopes: [],
            switched_on: true,
            key_held: true,
            status: UNBROKEN,
            may_switch_on: true,
          },
        ],
        chosen: ["staff_list"],
        steps: [{ title: UNBROKEN, text: UNBROKEN }],
        scopes: [{ name: UNBROKEN, what: UNBROKEN, read_only: true }],
        platforms: ["larksuite.com"],
        platform: "larksuite.com",
        base: "",
        developer_console: "https://open.larksuite.com/app",
        events_address: "",
        channel_note: UNBROKEN,
        knowledge_note: UNBROKEN,
        test_note: UNBROKEN,
        staff_sources_screen: "/staff_sources",
        vault_told: "",
      },
      "/api/v1/connectors": CONNECTORS_SCREEN,
    },
  },
  // One source's Dashboard: the source, its connection from the Connectors screen's read, and its
  // figures from the shared stats route.
  "/connectors/:connector": {
    address: "/connectors/xero",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/console/connectors/xero": CONNECTOR_SOURCE,
      "/api/v1/connectors": XERO_CONNECTED,
      "/api/v1/console/connectors/xero/stats": CONNECTOR_STATS,
      "/api/v1/console/connectors/xero/probe": CONNECTOR_PROBE,
    },
  },
  // The Profile, the view with the most on it: settings, the index's fields, what it reads live,
  // the agents and skills that use it, and the Advanced section's identifiers.
  "/connectors/:connector/:view": {
    address: "/connectors/xero/profile",
    signedIn: true,
    drawsValues: true,
    answers: {
      "/api/v1/console/connectors/xero": CONNECTOR_SOURCE,
      "/api/v1/connectors": XERO_CONNECTED,
      "/api/v1/console/connectors/xero/probe": CONNECTOR_PROBE,
    },
  },
};
