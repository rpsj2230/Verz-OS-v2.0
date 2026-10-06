/**
 * The Connectors module on the shared page kit: the list of every source, one source's page in its
 * three views, and the acts that change a connection.
 *
 * This is the screen the owner of a fresh install opens to find out what his system has access to,
 * so the failures worth testing are not layout failures. They are: a key reaching the page, a figure
 * drawn where the API sent none, a write sent without a confirmation, an edit that sends a key, a
 * form that says what it accepts only after a refusal, an act called "coming soon" whose route
 * has arrived, and a test of a connection that is sent unconfirmed or whose result never arrives.
 *
 * **Reachable means through the application's own route table.** Every page test mounts `routes`
 * from `src/App.tsx` on a memory router, signed in through the real session modules and answered by
 * a stand-in API, so a test passes only if the address resolves.
 *
 * **The bodies are compared with the Python models and the API document rather than with
 * themselves**: `tests/support/python.ts` reads field names out of `brain.connector_routes`, and
 * `tests/support/openapi.ts` the request bodies and paths the routes declare.
 *
 * Task ids: M27.11.9, M27.15.39, M27.15.58, M11.7.7, M27.16.1, M42.6.5, M27.15.8, M11.3.4, M7.7.2
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { NOT_RECORDED, UNAVAILABLE_MARK } from "../src/components/kit";
import { SECRET_STORED } from "../src/components/ui/secret-field";
import {
  CONNECTORS_LABEL,
  CONNECTORS_PATH,
  offered,
  type Connectable,
  type Connected,
  type Connectors,
} from "../src/pages/connectorsQuery";
import { ACT_LABELS, UNAVAILABLE } from "../src/pages/connectors/connectorActions";
import { LAST_LIVE_READ_LABEL, LIVE_READS_LABEL, NO_LIVE_READ, NOT_CONNECTED_TITLE } from "../src/pages/connectors/ConnectorDashboard";
import { NO_AGENT, STEWARD_LABEL } from "../src/pages/connectors/ConnectorProfile";
import { TESTING_WORDS, VERDICT_WORDS } from "../src/pages/connectors/connectorProbe";
import { CHECK_AGAIN, NOT_NOW } from "../src/pages/connectors/TestConnection";
import { connectorAddress, readSourceRows } from "../src/pages/connectors/connectorSources";
import { CONNECT_A_SOURCE, CONNECTORS_HEADING, NOT_AVAILABLE } from "../src/pages/connectors/ConnectorsPage";
import { GRANT_OFF, GRANT_ON, KEY_SUPPLIED, REVIEW_EDIT, REVIEW_KEY, REVIEW_STEWARD, STEWARD_BLANK, STEWARD_FIELD_LABEL } from "../src/pages/connectors/SourceActs";
import { ACCEPT, BEFORE, DRIFT_HEADING, NOW_DOES } from "../src/pages/connectors/DeclarationDrift";
import { DECLARATION_CHANGED_WORDS } from "../src/pages/connectors/pills";
import { AT_THE_SERVER, FROM_HERE, START } from "../src/pages/connectors/SourceFlow";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { declaredNavigation } from "./support/navigation";
import { apiDocument, declaredPropertyNames, declaredRequestBodySchema } from "./support/openapi";
import { backendModelFields } from "./support/python";
import { readConnectorStats, shareWords } from "../src/pages/connectors/connectorStats";
import { installRadixStubs } from "./support/radix";
import { readConsoleFile } from "./support/repo";

const ROUTES = "src/brain/connector_routes.py";
const STATS_ROUTES = "src/brain/console_stats_routes.py";
const CONSOLE_ORIGIN = "https://console.test";

/** A key nothing else could contain, so finding it anywhere is a leak. */
const KEY = "SOURCE-KEY-SENTINEL-51c0de";

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/Connector");
}, 60_000);

// ------------------------------------------------------------------------------ the answers

function sentinel(name: string): string {
  return `${name.toUpperCase()}-SENTINEL`;
}

/** One step of a connect flow as the API serves it, asking for `asks` on its screen. */
function aStep(key: string, asks: string[] = []): Connectable["steps"][number] {
  return {
    key,
    title: `${key}-TITLE`,
    text: sentinel(`${key}-text`),
    sketch: { place: "Vendor", heading: `${key}-HEADING`, menu: [], menu_mark: "", tabs: [], tab_mark: "", lines: [], button: "" },
    link: key === "create" ? "https://vendor.example.test/apps" : "",
    link_label: key === "create" ? "Open the vendor's apps" : "",
    asks,
  };
}

function aSource(over: Partial<Connectable> = {}): Connectable {
  return {
    name: "xero",
    label: "Xero",
    settings: [
      { name: "tenant_id", label: "Organisation id", hint: sentinel("tenant-hint"), max_chars: 200, blank: sentinel("tenant-blank") },
    ],
    credential_label: "The key Xero issued for this connection",
    credential_hint: sentinel("key-hint"),
    credential_shape: "key",
    credential_max_chars: 1000,
    may_connect: true,
    steps: [aStep("create"), aStep("authorise"), aStep("connect", ["tenant_id", "credential"])],
    ...over,
  };
}

function aConnected(over: Partial<Connected> = {}): Connected {
  return {
    name: "xero",
    connected_by: "u_admin",
    connected_at: "2019-03-04T09:00:00Z",
    key_held: true,
    key_written_at: "2019-03-04T09:00:05Z",
    pinned: true,
    declaration: sentinel("declaration"),
    trust: {
      name: "xero",
      wiring: "rest",
      credential: sentinel("key-sentence"),
      budget: sentinel("ceiling-sentence"),
      projected_fields: 9,
      checked_at: null,
      health: "ok",
      lifecycle: "registered",
      serving: false,
      version: "1.0.0",
      reaches: sentinel("reaches"),
      access: sentinel("access"),
      permission_sync: sentinel("sync"),
    },
    may_disconnect: true,
    last_synced_at: "2019-03-04T09:30:00Z",
    next_sync_at: "2019-03-04T10:30:00Z",
    sync: sentinel("reading"),
    ...over,
  };
}

function aPage(over: Partial<Connectors> = {}): Connectors {
  return {
    connectors: [aConnected()],
    unread: "",
    connecting: sentinel("connecting"),
    confirm_connect: sentinel("confirm-connect"),
    confirm_disconnect: sentinel("confirm-disconnect"),
    copy_policy: [{ what: sentinel("copied-thing"), verdict: "projected", why: sentinel("copied-why") }],
    budget_unread: sentinel("no-numerator"),
    may_connect: true,
    vault: "ready",
    vault_told: "",
    connectable: [aSource(), aSource({ name: "hubspot", label: "HubSpot", settings: [] })],
    not_connectable: [
      {
        name: "laravel",
        label: "Laravel database views",
        why: sentinel("laravel-why"),
        steps: [aStep("views"), aStep("user"), aStep("at_the_server")],
      },
    ],
    evidence: [],
    key_max_chars: 1000,
    key_blank: sentinel("key-blank"),
    ...over,
  };
}

function row(name: string, label: string, over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    name,
    label,
    status: "not_connected",
    health: null,
    department: null,
    last_read_at: null,
    connected_at: null,
    declaration_changed: false,
    connect_from: "console",
    may_manage: true,
    ...over,
  };
}

const LIST = {
  items: [
    row("xero", "Xero", {
      status: "connected",
      health: "ok",
      last_read_at: "2019-03-04T09:30:00Z",
      connected_at: "2019-03-04T09:00:00Z",
      declaration_changed: true,
    }),
    row("freshdesk", "Freshdesk", {
      status: "failing",
      health: "down",
      department: "support",
      connected_at: "2019-03-04T09:00:00Z",
    }),
    row("hubspot", "HubSpot"),
    row("lark_wiki", "Lark Wiki", { connect_from: "lark", may_manage: false }),
    row("laravel", "Laravel database views", { connect_from: "server", may_manage: false }),
  ],
  next_cursor: null,
  total: null,
};

const XERO_STATS = {
  connector: "xero",
  health: "ok",
  last_attempt: "2019-03-04T09:30:00Z",
  last_read_to_the_end: "2019-03-04T09:30:00Z",
  consecutive_failures: 0,
  index_ids: 1234,
  live_read_basis: "own",
  last_live_read: null,
  at_least: false,
  periods: ["7d", "30d"].map((range) => ({
    range,
    since: "2019-02-02T00:00:00Z",
    until: "2019-03-04T12:00:00Z",
    attempts: 24,
    read_to_the_end: 22,
    failures: 2,
    quota_waits: 0,
    live_reads: range === "30d" ? 317 : 0,
  })),
  unrecorded: [],
  calls: {
    window_seconds: 60,
    requests: 12,
    per_second: 0.2,
    per_minute: 12,
    concurrency: 1,
    quota_ratio: 0.25,
    error_ratio: 0,
    latency_p50_ms: 140,
    latency_p95_ms: 610,
    quiet: false,
  },
  calls_told: sentinel("calls-told"),
};

const XERO_DETAIL = {
  source: LIST.items[0],
  elsewhere: "",
  reading: sentinel("reading-sentence"),
  ceiling: sentinel("ceiling"),
  recorded: sentinel("recorded"),
  department_says: sentinel("no-department"),
  settings: [{ name: "tenant_id", label: "Organisation id", value: "tenant-one" }],
  keeps: [{ entity: "invoice", fields: ["invoice_number", "status"] }],
  reads_live: [{ tool: "xero.read_invoices", entity: "invoice", description: sentinel("reads-invoices") }],
  history: [
    {
      connected_at: "2019-03-04T09:00:00Z",
      connected_by: "u_admin",
      disconnected_at: null,
      disconnected_by: null,
      settings: [{ name: "tenant_id", label: "Organisation id", value: "tenant-one" }],
    },
    {
      connected_at: "2019-03-01T09:00:00Z",
      connected_by: "u_gone",
      disconnected_at: "2019-03-04T09:00:00Z",
      disconnected_by: "u_admin",
      settings: [{ name: "tenant_id", label: "Organisation id", value: "tenant-before" }],
    },
  ],
  people: { u_admin: "Ada Admin" },
  agents: [{ agent_id: "books-helper", display_name: "Books helper" }],
  skills: [{ name: "invoice-chaser", version: "1.2.0", state: "approved" }],
  confirm_edit: sentinel("confirm-edit"),
  confirm_key: sentinel("confirm-key"),
  steward: "u_admin",
  confirm_steward: sentinel("confirm-steward"),
};

/** What changed in Xero's declaration, as `brain.connector_routes.DeclarationDriftView` sends it. */
function aDrift(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    connector: "xero",
    changed: true,
    known: true,
    lines: [
      { kind: "added", what: "Now also keeps in its index: an invoice's due date", was: "" },
      { kind: "changed", what: sentinel("now-does"), was: sentinel("did-before") },
    ],
    now_does: [],
    was_version: "0.9.0",
    now_version: "1.0.0",
    agreed_digest: "a".repeat(64),
    current_digest: "c".repeat(64),
    may_accept: true,
    told: sentinel("drift-told"),
    confirm: sentinel("drift-confirm"),
    ...over,
  };
}

/** A connection test's answer, as `brain.connector_routes.ConnectorProbeView` sends it. */
function aProbe(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    connector: "xero",
    requested_at: null,
    pending: false,
    verdict: null,
    tested_at: null,
    health: null,
    said: sentinel("never-tested"),
    confirm: sentinel("confirm-test"),
    ...over,
  };
}

interface Answer {
  readonly status?: number;
  readonly body: unknown;
}

/** A write the source can be allowed to make, as `brain.connector_routes.WriteGrantView` sends it. */
function aGrant(): NonNullable<Connectable["writes"]>[number] {
  return {
    name: "dns_changes",
    label: "Allow approved DNS changes",
    credential_label: "A second token that can edit DNS",
    credential_hint: sentinel("grant-hint"),
    credential_shape: "key",
    credential_max_chars: 1000,
    not_allowed: sentinel("not-allowed"),
    confirmation: sentinel("confirm-grant"),
  };
}

const ANSWERS: Readonly<Record<string, Answer>> = {
  "/api/v1/console/connectors": { body: LIST },
  "/api/v1/connectors": { body: aPage() },
  "/api/v1/console/connectors/xero/stats": { body: XERO_STATS },
  "/api/v1/console/connectors/freshdesk/stats": { body: { ...XERO_STATS, connector: "freshdesk", index_ids: null } },
  "/api/v1/console/connectors/xero": { body: XERO_DETAIL },
  "/api/v1/console/connectors/hubspot": {
    body: { ...XERO_DETAIL, source: LIST.items[2], settings: [], keeps: [], reads_live: [], history: [], agents: [], skills: [] },
  },
  "/api/v1/console/connectors/xero/export": { body: { connector: "xero", credential: sentinel("no-key"), history: [] } },
  "/api/v1/console/connectors/xero/probe": { body: aProbe() },
  "/api/v1/console/connectors/xero/drift": { body: aDrift() },
};

/** The answers with Xero declaring one write, whose key the vault holds for the grants named. */
function withGrant(allowed: string[]): Readonly<Record<string, Answer>> {
  return {
    ...ANSWERS,
    "/api/v1/connectors": {
      body: aPage({
        connectors: [aConnected({ writes_allowed: allowed })],
        connectable: [aSource({ writes: [aGrant()] }), aSource({ name: "hubspot", label: "HubSpot", settings: [] })],
      }),
    },
  };
}

interface Mounted {
  readonly container: HTMLElement;
  readonly idp: FakeIdp;
}

async function consoleAt(path: string, answers: Readonly<Record<string, Answer>> = ANSWERS): Promise<Mounted> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      const pathname = new URL(url, CONSOLE_ORIGIN).pathname;
      if (init?.method === "POST") {
        return new Response(JSON.stringify({ told: sentinel("done") }), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }
      const answer = answers[pathname];
      if (answer === undefined) {
        return null;
      }
      return new Response(JSON.stringify(answer.body), {
        status: answer.status ?? 200,
        headers: { "content-type": "application/json" },
      });
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector("h1")) {
      throw new Error("the page has not arrived");
    }
  });
  await waitFor(() => {
    if (container.querySelector('[data-slot="loading-state"]') || container.querySelector('[data-slot="stats-strip"] [role="status"]')) {
      throw new Error("the page is still asking");
    }
  });
  return { container, idp };
}

function posts(idp: FakeIdp): { path: string; body: unknown }[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST" && new URL(call.url, CONSOLE_ORIGIN).pathname.startsWith("/api/"))
    .map((call) => ({
      path: new URL(call.url, CONSOLE_ORIGIN).pathname,
      body: call.init?.body === undefined ? undefined : (JSON.parse(String(call.init.body)) as unknown),
    }));
}

function asked(idp: FakeIdp, path: string): number {
  return idp.calls.filter((call) => new URL(call.url, CONSOLE_ORIGIN).pathname === path).length;
}

async function openMenu(name: string | RegExp): Promise<HTMLElement> {
  const trigger = screen.getByRole("button", { name });
  trigger.focus();
  await act(async () => {
    fireEvent.keyDown(trigger, { key: "Enter" });
  });
  return screen.findByRole("menu");
}

async function choose(menu: HTMLElement, name: string): Promise<void> {
  const item = within(menu).getByRole("menuitem", { name });
  await act(async () => {
    fireEvent.click(item);
  });
}

// ------------------------------------------------------------ what this module agrees with the API about

describe("what this module agrees with the API about", () => {
  test("no act the module calls coming soon has a route in the API document", () => {
    // What breaks if this is deleted: "coming soon" said about testing a connection after its route
    // lands, so a person is told they cannot do what they can.
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    for (const [one, { retiredBy }] of Object.entries(UNAVAILABLE)) {
      expect(paths.filter((path) => retiredBy.test(path)), one).toEqual([]);
    }
    // The positive sibling: every act on a source has its route now, testing a connection included.
    expect(Object.keys(UNAVAILABLE)).toEqual([]);
    expect(paths).toContain("/api/v1/connectors/{connector}/probe");
    expect(paths).toContain("/api/v1/console/connectors/{connector}/probe");
  });

  test("the edit and the key replacement send exactly the fields their routes declare, and an edit no key", () => {
    // What breaks if this is deleted: a body key the route forbids with `extra="forbid"`, refused
    // with a 422 naming no field the form can draw, or an edit that carries a key it must not.
    expect(declaredPropertyNames(declaredRequestBodySchema("/api/v1/connectors/{connector}/edit", "post"))).toEqual(["settings"]);
    expect(declaredPropertyNames(declaredRequestBodySchema("/api/v1/connectors/{connector}/key", "post"))).toEqual([
      "credential",
      "grant",
    ]);
    const acts = readConsoleFile("src/pages/connectors/SourceActs.tsx");
    expect(acts).toContain("const body = { settings: Object.fromEntries(");
    expect(acts).toContain("const credential = shaped ? credentialFor(asked.credential_shape, held, secret) : secret.take();");
    expect(acts).toContain("const body = grant === undefined ? { credential } : { credential, grant: grant.name };");
  });

  test("no model the module reads carries a field that could hold a key or where one is kept", () => {
    // What breaks if this is deleted: a `slot` or `key` field added to a row for convenience, which
    // is how a vault path reaches a screenshot in a support chat.
    for (const model of [
      "ConnectorSourceRowView",
      "ConnectorSourceView",
      "ConnectorSettingValueView",
      "ConnectorHistoryView",
      "ConnectorExportView",
      "ConnectorExportedConnectionView",
      "ConnectorEditedView",
      "ConnectorKeyReplacedView",
      "ConnectorProbeView",
      "WriteGrantView",
    ]) {
      const fields = backendModelFields(ROUTES, model);
      expect(fields.length, model).toBeGreaterThan(0);
      for (const forbidden of ["path", "slot", "secret", "vault_path", "token", "key", "value_of_key"]) {
        expect(fields, model).not.toContain(forbidden);
      }
    }
    // `credential` is the export's sentence saying why there is no key, and a request body field.
    expect(backendModelFields(ROUTES, "ConnectorSourceView")).not.toContain("credential");
  });

  test("nothing in the module reads a total or a count of what was left out", () => {
    // What breaks if this is deleted: "showing 3 of 7", which on the one screen whose subject is
    // reach is the disclosure by subtraction with every value correct.
    for (const file of [
      "src/pages/connectors/ConnectorsPage.tsx",
      "src/pages/connectors/ConnectorDetailPage.tsx",
      "src/pages/connectors/connectorSources.ts",
      "src/pages/connectors/connectorStats.ts",
    ]) {
      const text = readConsoleFile(file);
      expect(text, file).not.toMatch(/\.total\b/);
      expect(text, file).not.toMatch(/\["total"\]/);
    }
  });

  test("the served menu offers the module under the label the design names, in Knowledge and data", () => {
    // What breaks if this is deleted: the entry drifts to another label or group, and somebody
    // following the design cannot find it.
    for (const which of ["company", "department"] as const) {
      const holding = declaredNavigation(which).filter((one) =>
        one.entries.some((entry) => entry.to === CONNECTORS_PATH && entry.label === CONNECTORS_LABEL),
      );
      expect(holding.map((one) => one.heading), which).toEqual(["Knowledge and data"]);
    }
  });

  test("a row keeps only what was sent, and the sources the wizard named are offered first", () => {
    // What breaks if this is deleted: a cell drawn as "unknown" for a field the API did not send,
    // which says something was withheld, or first run offering a source this reader may not connect.
    const [only] = readSourceRows({ items: [row("xero", "Xero"), row("xero", "Again"), { name: "no_label" }] });
    expect(only).toEqual({ name: "xero", label: "Xero", status: "not_connected", declarationChanged: false, connectFrom: "console", mayManage: true });
    expect(offered([aSource(), aSource({ name: "hubspot", label: "HubSpot" })], " hubspot ").map((one) => one.name)).toEqual(["hubspot", "xero"]);
    expect(offered([aSource({ may_connect: false })])).toEqual([]);
  });
});

// ------------------------------------------------------------------------------------ the list

describe("the list", () => {
  test("every source is a row with its status, and a connected one its index size in ids", async () => {
    // What breaks if this is deleted: a list showing only connections, a failing source drawn as
    // connected, an index size invented for a source with none, or nought where nothing was sent.
    const { container, idp } = await consoleAt(CONNECTORS_PATH);
    await waitFor(() => {
      expect(container.textContent).toContain("1,234 ids");
    });
    const text = container.textContent ?? "";

    expect(container.querySelector("h1")?.textContent).toBe(CONNECTORS_HEADING);
    for (const label of ["Xero", "Freshdesk", "HubSpot", "Lark Wiki", "Laravel database views"]) {
      expect(text).toContain(label);
    }
    expect(text).toContain("Failing");
    expect(text).toContain("Declaration changed");
    expect(text).toContain("Connected through Connect Lark");
    const freshdesk = [...container.querySelectorAll("tbody tr")].find((one) => one.textContent?.includes("Freshdesk"));
    expect(freshdesk?.textContent).toContain(NOT_RECORDED);
    // Only the two connected rows were asked for figures.
    expect(asked(idp, "/api/v1/console/connectors/hubspot/stats")).toBe(0);
    expect(asked(idp, "/api/v1/console/connectors/xero/stats")).toBe(1);
    expect(text).not.toContain(NOT_AVAILABLE);
    expect(text).not.toContain(" of 5");
  });

  test("connecting says what each field takes, refuses a blank before asking, and sends the key once", async () => {
    // What breaks if this is deleted: a blank connection that opens a confirmation about nothing or
    // reaches the API, or a key kept in the page after it was sent.
    const { idp } = await consoleAt(CONNECTORS_PATH);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: CONNECT_A_SOURCE }));
    });
    const drawer = await screen.findByRole("dialog");
    await act(async () => {
      fireEvent.click(within(drawer).getByRole("button", { name: `${START}: Xero` }));
    });
    expect(within(drawer).getByText("Step 1 of 3")).toBeTruthy();
    await act(async () => {
      fireEvent.click(within(drawer).getByRole("button", { name: /Step 3 of 3/ }));
    });
    expect(drawer.textContent).toContain(sentinel("tenant-hint"));
    expect(drawer.textContent).toContain(sentinel("key-hint"));
    await act(async () => {
      fireEvent.click(within(drawer).getByRole("button", { name: "Connect Xero" }));
    });
    expect(drawer.textContent).toContain(sentinel("tenant-blank"));
    expect(drawer.textContent).toContain(sentinel("key-blank"));
    expect(drawer.querySelector(".confirm")).toBeNull();
    expect(posts(idp)).toEqual([]);

    fireEvent.change(within(drawer).getByLabelText("Organisation id"), { target: { value: "tenant-one" } });
    const key = within(drawer).getByLabelText("The key Xero issued for this connection") as HTMLInputElement;
    fireEvent.change(key, { target: { value: KEY } });
    await act(async () => {
      fireEvent.click(within(drawer).getByRole("button", { name: "Connect Xero" }));
    });
    const confirm = drawer.querySelector(".confirm") as HTMLElement;
    expect(confirm.textContent).toContain(sentinel("confirm-connect"));
    expect(confirm.textContent).not.toContain(KEY);
    await act(async () => {
      fireEvent.click(within(confirm).getByRole("button", { name: "Connect Xero" }));
    });
    await waitFor(() => {
      expect(posts(idp)).toEqual([
        { path: "/api/v1/connectors", body: { connector: "xero", settings: { tenant_id: "tenant-one" }, credential: KEY } },
      ]);
    });
    expect(document.body.innerHTML).not.toContain(KEY);
  });

  test("connecting is a flow of the source's own steps, each with its picture, and the form on the last", async () => {
    // What breaks if this is deleted: a connector opens a bare form again, with the vendor's
    // steps only as a hint under a field and no picture of where to press.
    await consoleAt(CONNECTORS_PATH);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: CONNECT_A_SOURCE }));
    });
    const dialog = await screen.findByRole("dialog");
    const sources = within(dialog).getByRole("list", { name: "Sources" });
    expect(sources.textContent).toContain(`Xero${FROM_HERE}`);
    expect(sources.textContent).toContain(`Laravel database views${AT_THE_SERVER}`);
    expect(sources.textContent).not.toContain("Lark");
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: `${START}: Xero` }));
    });
    expect(within(dialog).getByRole("heading", { name: "create-TITLE" })).toBeTruthy();
    expect(within(dialog).getByRole("img", { name: /A picture of the screen/ })).toBeTruthy();
    expect(within(dialog).getByRole("link", { name: /Open the vendor's apps/ }).getAttribute("href")).toBe(
      "https://vendor.example.test/apps",
    );
    // The form is on the last screen only.
    expect(within(dialog).queryByRole("button", { name: "Connect Xero" })).toBeNull();
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: "Next" }));
    });
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: "Next" }));
    });
    expect(within(dialog).getByRole("button", { name: "Connect Xero" })).toBeTruthy();
  });

  test("a source connected at the server shows its steps and no form", async () => {
    // What breaks if this is deleted: a source this screen cannot connect offers a form nobody
    // can send, or no way to learn how it is connected at all.
    await consoleAt(CONNECTORS_PATH);
    await choose(await openMenu("Actions for Laravel database views"), ACT_LABELS.howToConnect);
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Step 1 of 3")).toBeTruthy();
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: /Step 3 of 3/ }));
    });
    expect(dialog.textContent).toContain(sentinel("at_the_server-text"));
    expect(within(dialog).queryByRole("button", { name: "Next" })).toBeNull();
    expect(dialog.querySelector("form")).toBeNull();
  });

  test("closing the flow keeps the step and the settings typed, and never the key", async () => {
    // What breaks if this is deleted: somebody who closes the dialog to find the organisation id
    // in Xero comes back to the first step with the form empty, or the key outlives the dialog.
    await consoleAt(CONNECTORS_PATH);
    const open = async (): Promise<HTMLElement> => {
      await act(async () => {
        fireEvent.click(screen.getByRole("button", { name: CONNECT_A_SOURCE }));
      });
      const dialog = await screen.findByRole("dialog");
      await act(async () => {
        fireEvent.click(within(dialog).getByRole("button", { name: `${START}: Xero` }));
      });
      return dialog;
    };
    let dialog = await open();
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: /Step 3 of 3/ }));
    });
    fireEvent.change(within(dialog).getByLabelText("Organisation id"), { target: { value: "tenant-one" } });
    fireEvent.change(within(dialog).getByLabelText("The key Xero issued for this connection"), { target: { value: KEY } });
    await act(async () => {
      fireEvent.keyDown(dialog, { key: "Escape" });
    });
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    expect(document.body.innerHTML).not.toContain(KEY);
    dialog = await open();
    expect(within(dialog).getByText("Step 3 of 3")).toBeTruthy();
    expect((within(dialog).getByLabelText("Organisation id") as HTMLInputElement).value).toBe("tenant-one");
    expect((within(dialog).getByLabelText("The key Xero issued for this connection") as HTMLInputElement).value).toBe("");
  });

  test("disconnecting from a row is confirmed in the API's words, and keeping it sends nothing", async () => {
    // What breaks if this is deleted: a disconnect sent by one press, or a confirmation in the
    // console's words rather than the ones that say the key stays in the vault.
    const { idp } = await consoleAt(CONNECTORS_PATH);
    await choose(await openMenu("Actions for Xero"), ACT_LABELS.disconnect);
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain(sentinel("confirm-disconnect"));
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: "Keep it connected" }));
    });
    expect(posts(idp)).toEqual([]);

    await choose(await openMenu("Actions for Xero"), ACT_LABELS.disconnect);
    const again = await screen.findByRole("alertdialog");
    await act(async () => {
      fireEvent.click(within(again).getByRole("button", { name: ACT_LABELS.disconnect }));
    });
    await waitFor(() => {
      expect(posts(idp)).toEqual([{ path: "/api/v1/connectors/xero/disconnect", body: undefined }]);
    });
  });
});

// --------------------------------------------------------------------------------- one source

describe("one source's page", () => {
  test("the dashboard draws the stats route's figures and never nought for one it did not send", async () => {
    // What breaks if this is deleted: the figures read from somewhere other than the stats route,
    // or an index size drawn as 0 ids where the route sent none.
    const { container } = await consoleAt(connectorAddress("xero"));
    const strip = container.querySelector('[data-slot="kpi-strip"][aria-label="This source\'s figures"]');
    expect(strip?.textContent).toContain("1,234 ids");
    expect(strip?.textContent).toContain("24");
    const card = (label: string) =>
      [...(strip?.querySelectorAll('[data-slot="stat-card"]') ?? [])].find((one) => one.querySelector("dt")?.textContent === label);
    expect(card(LIVE_READS_LABEL)?.querySelector("dd")?.textContent).toContain("317");
    expect(card(LIVE_READS_LABEL)?.textContent).toContain("your questions");
    expect(card(LAST_LIVE_READ_LABEL)?.textContent).toContain(NO_LIVE_READ);
    expect(container.textContent).toContain(sentinel("reading"));
    expect(container.querySelectorAll(`[${UNAVAILABLE_MARK}]`).length).toBe(0);
    expect(screen.getByRole("button", { name: ACT_LABELS.test })).toBeTruthy();

    const hubspot = await consoleAt(connectorAddress("hubspot"));
    expect(hubspot.container.textContent).toContain(NOT_CONNECTED_TITLE);
    expect(asked(hubspot.idp, "/api/v1/console/connectors/hubspot/stats")).toBe(0);
  });

  test("the calls questions made to the source are drawn as the route sent them, with whose they are (M11.3.4)", async () => {
    // What breaks if this is deleted: a calls figure the page works out itself, a share drawn from
    // too few calls to mean one, or the calls drawn without the route's sentence about whose they are.
    expect(Object.keys(XERO_STATS).sort()).toEqual(backendModelFields(STATS_ROUTES, "ConnectorStatsView").sort());
    expect(Object.keys(XERO_STATS.calls).sort()).toEqual(backendModelFields(STATS_ROUTES, "ConnectorCallsView").sort());
    const { container } = await consoleAt(connectorAddress("xero"));
    const text = container.textContent ?? "";
    expect(text).toContain(sentinel("calls-told"));
    expect(text).toContain("25%");
    expect(text).toContain("140 ms typical, 610 ms slowest");
    const quiet = { ...XERO_STATS.calls, quiet: true };
    const said = readConnectorStats({ ...XERO_STATS, calls: quiet })?.calls;
    expect(said === undefined ? "" : shareWords(0.25, said)).toBe("Too few calls to say");
  });

  test("the profile shows settings, the minimal index and who uses it, names people, and shows no key", async () => {
    // What breaks if this is deleted: the minimal index gone from the page, a principal id drawn as
    // a name, or a key reaching the page.
    const { container } = await consoleAt(`${connectorAddress("xero")}/profile`);
    const text = container.textContent ?? "";

    expect(text).toContain("tenant-one");
    expect(text).toContain("invoice_number");
    expect(text).toContain(sentinel("reads-invoices"));
    expect(text).toContain("Ada Admin");
    expect(text).toContain("Books helper");
    expect(text).toContain("invoice-chaser");
    expect(text).not.toContain(NO_AGENT);
    // The profile's own Advanced, beside the drift card's, which holds the two digests.
    const advanced = [...container.querySelectorAll('[data-slot="advanced"]')].find((one) => one.textContent?.includes("u_admin"));
    expect(advanced?.textContent).toContain("u_admin");
    const outside = text.replace(advanced?.textContent ?? "", "");
    expect(outside).not.toContain("u_admin");
    expect(text).not.toContain(KEY);
  });

  test("the about view says how it is read and every connection it has had, by name", async () => {
    // What breaks if this is deleted: the history lost, or a person who has left drawn as an id.
    const { container } = await consoleAt(`${connectorAddress("xero")}/about`);
    const text = container.textContent ?? "";

    expect(text).toContain(sentinel("reading-sentence"));
    expect(text).toContain(sentinel("ceiling"));
    expect(text).toContain(sentinel("recorded"));
    expect(text).toContain("tenant-before");
    expect(text).toContain("a person no longer listed");
    expect(text).not.toContain("u_gone");
  });

  test("an edit says what each setting accepts, refuses a blank before asking, and sends settings only", async () => {
    // What breaks if this is deleted: a form that says what it accepts only after a refusal, an edit
    // sent without a confirmation, or an edit whose body carries a key.
    const { idp } = await consoleAt(`${connectorAddress("xero")}/profile`);
    await choose(await openMenu("Manage this source"), ACT_LABELS.edit);
    const drawer = await screen.findByRole("dialog");
    expect(drawer.textContent).toContain(sentinel("tenant-hint"));
    const field = within(drawer).getByLabelText("Organisation id") as HTMLInputElement;
    expect(field.value).toBe("tenant-one");

    fireEvent.change(field, { target: { value: " " } });
    await act(async () => {
      fireEvent.click(within(drawer).getByRole("button", { name: REVIEW_EDIT }));
    });
    expect(drawer.textContent).toContain(sentinel("tenant-blank"));
    expect(screen.queryByRole("alertdialog")).toBeNull();

    fireEvent.change(field, { target: { value: "tenant-two" } });
    await act(async () => {
      fireEvent.click(within(drawer).getByRole("button", { name: REVIEW_EDIT }));
    });
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain(sentinel("confirm-edit"));
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: "Edit settings" }));
    });
    await waitFor(() => {
      expect(posts(idp)).toEqual([{ path: "/api/v1/connectors/xero/edit", body: { settings: { tenant_id: "tenant-two" } } }]);
    });
  });

  test("a replaced key is confirmed, sent once in its own body, and gone from the page", async () => {
    // What breaks if this is deleted: a key sent without a confirmation, shown on the confirmation,
    // or left in the field after it was sent.
    const { container, idp } = await consoleAt(`${connectorAddress("xero")}/profile`);
    await choose(await openMenu("Manage this source"), ACT_LABELS.key);
    const drawer = await screen.findByRole("dialog");
    expect(drawer.textContent).toContain(sentinel("key-hint"));
    expect(drawer.textContent).toContain(SECRET_STORED);
    const field = within(drawer).getByLabelText("The key Xero issued for this connection") as HTMLInputElement;
    fireEvent.input(field, { target: { value: KEY } });
    await act(async () => {
      fireEvent.click(within(drawer).getByRole("button", { name: REVIEW_KEY }));
    });
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain(sentinel("confirm-key"));
    expect(dialog.textContent).toContain(KEY_SUPPLIED);
    expect(dialog.textContent).not.toContain(KEY);
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: "Replace key" }));
    });
    await waitFor(() => {
      expect(posts(idp)).toEqual([{ path: "/api/v1/connectors/xero/key", body: { credential: KEY } }]);
    });
    expect(field.value).toBe("");
    expect(document.body.innerHTML).not.toContain(KEY);
    expect(container.innerHTML).not.toContain(KEY);
  });

  test("a blank key opens no confirmation, sends nothing, and says what to paste", async () => {
    // What breaks if this is deleted: a confirmation about replacing a key with nothing.
    const { idp } = await consoleAt(`${connectorAddress("xero")}/profile`);
    await choose(await openMenu("Manage this source"), ACT_LABELS.key);
    const drawer = await screen.findByRole("dialog");
    await act(async () => {
      fireEvent.click(within(drawer).getByRole("button", { name: REVIEW_KEY }));
    });
    expect(drawer.textContent).toContain(sentinel("key-blank"));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(posts(idp)).toEqual([]);
  });

  test("allowing a write is its own item, asks for the grant's key in its words, and sends it naming the grant", async () => {
    // What breaks if this is deleted: Cloudflare's DNS Edit token pasted into the read key's drawer
    // and sent as the read key, the grant's key sent without a confirmation, or shown on one, or a
    // drawer that says a write is off while the vault holds its key (M11.7.3). The item is the
    // API's label, under the key; the body names the grant; the key leaves the page once.
    const grant = aGrant();
    const { container, idp } = await consoleAt(`${connectorAddress("xero")}/profile`, withGrant([]));
    const menu = await openMenu("Manage this source");
    expect(within(menu).getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
      ACT_LABELS.edit,
      ACT_LABELS.key,
      grant.label,
      ACT_LABELS.steward,
      ACT_LABELS.export,
      ACT_LABELS.disconnect,
    ]);
    await choose(menu, grant.label);
    const drawer = await screen.findByRole("dialog");
    expect(drawer.textContent).toContain(GRANT_OFF);
    expect(drawer.textContent).toContain(sentinel("grant-hint"));
    expect(drawer.textContent).not.toContain(sentinel("key-hint"));
    const field = within(drawer).getByLabelText(grant.credential_label) as HTMLInputElement;
    fireEvent.input(field, { target: { value: KEY } });
    await act(async () => {
      fireEvent.click(within(drawer).getByRole("button", { name: REVIEW_KEY }));
    });
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain(sentinel("confirm-grant"));
    expect(dialog.textContent).not.toContain(sentinel("confirm-key"));
    expect(dialog.textContent).toContain(KEY_SUPPLIED);
    expect(dialog.textContent).not.toContain(KEY);
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: grant.label }));
    });
    await waitFor(() => {
      expect(posts(idp)).toEqual([{ path: "/api/v1/connectors/xero/key", body: { credential: KEY, grant: grant.name } }]);
    });
    expect(field.value).toBe("");
    expect(document.body.innerHTML).not.toContain(KEY);
    expect(container.innerHTML).not.toContain(KEY);
  });

  test("a write whose key is held says it is on", async () => {
    // What breaks if this is deleted: a drawer that says off whatever the vault holds, which tells
    // an administrator a write is not happening while approved changes are being sent.
    await consoleAt(`${connectorAddress("xero")}/profile`, withGrant([aGrant().name]));
    await choose(await openMenu("Manage this source"), aGrant().label);
    const drawer = await screen.findByRole("dialog");
    expect(drawer.textContent).toContain(GRANT_ON);
    expect(drawer.textContent).not.toContain(GRANT_OFF);
    expect(drawer.textContent).toContain(SECRET_STORED);
  });

  test("a source that declares no write offers no item to allow one", async () => {
    // What breaks if this is deleted: the grant offered for every source, so a drawer asks Xero for
    // a DNS token it has no use for.
    await consoleAt(`${connectorAddress("xero")}/profile`);
    const plain = await openMenu("Manage this source");
    expect(within(plain).getAllByRole("menuitem").map((item) => item.textContent)).toEqual([
      ACT_LABELS.edit,
      ACT_LABELS.key,
      ACT_LABELS.steward,
      ACT_LABELS.export,
      ACT_LABELS.disconnect,
    ]);
  });

  test("the profile names the source's steward, and handing it on is confirmed in the API's words and sends only the person", async () => {
    // What breaks if this is deleted: a steward nobody can see on the page, a hand-over sent without
    // a confirmation, or one whose body carries anything but the person named (M7.7.2).
    const { container, idp } = await consoleAt(`${connectorAddress("xero")}/profile`);
    const fact = [...container.querySelectorAll("dt")].find((one) => one.textContent === STEWARD_LABEL);
    expect(fact?.nextElementSibling?.textContent).toBe("Ada Admin");

    await choose(await openMenu("Manage this source"), ACT_LABELS.steward);
    const drawer = await screen.findByRole("dialog");
    await act(async () => {
      fireEvent.click(within(drawer).getByRole("button", { name: REVIEW_STEWARD }));
    });
    expect(drawer.textContent).toContain(STEWARD_BLANK);
    expect(screen.queryByRole("alertdialog")).toBeNull();

    fireEvent.change(within(drawer).getByLabelText(STEWARD_FIELD_LABEL), { target: { value: " u_next " } });
    await act(async () => {
      fireEvent.click(within(drawer).getByRole("button", { name: REVIEW_STEWARD }));
    });
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain(sentinel("confirm-steward"));
    expect(posts(idp)).toEqual([]);
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: ACT_LABELS.steward }));
    });
    await waitFor(() => {
      expect(posts(idp)).toEqual([{ path: "/api/v1/connectors/xero/steward", body: { steward_id: "u_next" } }]);
    });
  });

  test("a source the reader may not be told the steward of offers no hand-over", async () => {
    // What breaks if this is deleted: a menu that offers to hand on a source whose steward the API
    // did not send, which would be a form for a reader who may not name one.
    await consoleAt(connectorAddress("xero"), {
      ...ANSWERS,
      "/api/v1/console/connectors/xero": { body: { ...XERO_DETAIL, steward: "" } },
    });
    const menu = await openMenu("Manage this source");
    expect(within(menu).queryByText(ACT_LABELS.steward)).toBeNull();
    expect(within(menu).getByText(ACT_LABELS.export)).toBeTruthy();
  });

  test("the steward's request body is the one the route declares", () => {
    // What breaks if this is deleted: a renamed body field the route refuses as an unknown one.
    expect(declaredPropertyNames(declaredRequestBodySchema("/api/v1/connectors/{connector}/steward", "post"))).toEqual(["steward_id"]);
    expect(backendModelFields(ROUTES, "ConnectorSourceView")).toEqual(expect.arrayContaining(["steward", "confirm_steward"]));
  });

  test("the export reads the record and changes nothing", async () => {
    // What breaks if this is deleted: an export that writes, or one read from the wrong address.
    const { idp } = await consoleAt(connectorAddress("xero"));
    await choose(await openMenu("Manage this source"), ACT_LABELS.export);
    await waitFor(() => {
      expect(asked(idp, "/api/v1/console/connectors/xero/export")).toBe(1);
    });
    expect(posts(idp)).toEqual([]);
  });
});

// --------------------------------------------------------------------- testing a connection

describe("testing a connection", () => {
  test("a test is confirmed in the API's words, asked once, waits for the worker and then says what it found", async () => {
    // What breaks if this is deleted: a test sent by one press, a confirmation in the console's words
    // rather than the ones that say one call is made and nothing kept, a page that never shows the
    // result the worker recorded, or one that shows the previous test as the answer to this press.
    const answers: Record<string, Answer> = { ...ANSWERS };
    const { container, idp } = await consoleAt(connectorAddress("xero"), answers);
    // The button waits for the test's own answer, because its confirmation is in the API's words.
    await waitFor(
      () => {
        expect((screen.getByRole("button", { name: ACT_LABELS.test }) as HTMLButtonElement).disabled).toBe(false);
      },
      { timeout: 5_000 },
    );
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: ACT_LABELS.test }));
    });
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain(sentinel("confirm-test"));
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: NOT_NOW }));
    });
    expect(posts(idp)).toEqual([]);

    answers["/api/v1/console/connectors/xero/probe"] = {
      body: aProbe({ pending: true, requested_at: "2019-03-04T10:00:00Z", said: sentinel("waiting") }),
    };
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: ACT_LABELS.test }));
    });
    const again = await screen.findByRole("alertdialog");
    await act(async () => {
      fireEvent.click(within(again).getByRole("button", { name: ACT_LABELS.test }));
    });
    await waitFor(() => {
      expect(posts(idp)).toEqual([{ path: "/api/v1/connectors/xero/probe", body: undefined }]);
    });
    await waitFor(
      () => {
        expect(container.querySelector('[data-slot="connection-test"]')?.textContent).toContain(sentinel("waiting"));
      },
      { timeout: 5_000 },
    );
    const waiting = container.querySelector('[data-slot="connection-test"]');
    expect(waiting?.textContent).toContain(TESTING_WORDS);
    expect((screen.getByRole("button", { name: ACT_LABELS.test }) as HTMLButtonElement).disabled).toBe(true);
    const pageAsks = asked(idp, "/api/v1/console/connectors/xero");

    answers["/api/v1/console/connectors/xero/probe"] = {
      body: aProbe({
        requested_at: "2019-03-04T10:00:00Z",
        verdict: "failed",
        tested_at: "2019-03-04T10:00:40Z",
        health: "down",
        said: sentinel("key-declined"),
      }),
    };
    await act(async () => {
      fireEvent.click(within(waiting as HTMLElement).getByRole("button", { name: CHECK_AGAIN }));
    });
    // The page is asked again, so the health the test left is drawn, and the result stays.
    await waitFor(
      () => {
        expect(asked(idp, "/api/v1/console/connectors/xero")).toBeGreaterThan(pageAsks);
      },
      { timeout: 5_000 },
    );
    await waitFor(
      () => {
        const note = container.querySelector('[data-slot="connection-test"]')?.textContent ?? "";
        expect(note).toContain(sentinel("key-declined"));
        expect(note).toContain(VERDICT_WORDS.failed);
      },
      { timeout: 5_000 },
    );
    expect(document.body.innerHTML).not.toContain(KEY);
  });

  test("a reader who may not manage the source sees the newest test and no button", async () => {
    // What breaks if this is deleted: a test offered to somebody the API will refuse, or the result
    // of a test hidden from the people the page is for.
    const answers: Record<string, Answer> = {
      ...ANSWERS,
      "/api/v1/console/connectors/xero": { body: { ...XERO_DETAIL, source: { ...LIST.items[0], may_manage: false } } },
      "/api/v1/console/connectors/xero/probe": {
        body: aProbe({ verdict: "answered", tested_at: "2019-03-04T10:00:40Z", health: "ok", said: sentinel("works") }),
      },
    };
    const { container } = await consoleAt(connectorAddress("xero"), answers);
    await waitFor(() => {
      expect(container.querySelector('[data-slot="connection-test"]')?.textContent).toContain(sentinel("works"));
    });
    expect(container.querySelector('[data-slot="connection-test"]')?.textContent).toContain(VERDICT_WORDS.answered);
    expect(screen.queryByRole("button", { name: ACT_LABELS.test })).toBeNull();
  });

  test("a source never tested draws no result line", async () => {
    // What breaks if this is deleted: a "not tested yet" line on every connected source's page,
    // which is clutter the owner asked to be rid of.
    const { container } = await consoleAt(connectorAddress("xero"));
    expect(container.querySelector('[data-slot="connection-test"]')).toBeNull();
  });
});

describe("a changed declaration", () => {
  test("what changed is shown before the accept, and accepting is confirmed and names the digest shown", async () => {
    // What breaks if this is deleted: the pill says a source stopped being read and a person
    // accepts the change without being shown it, or accepts one they did not read.
    const { idp } = await consoleAt(connectorAddress("xero"));
    const card = await screen.findByRole("region", { name: DRIFT_HEADING });
    expect(card.textContent).toContain("Now also keeps in its index: an invoice's due date");
    expect(card.textContent).toContain(`${BEFORE}: ${sentinel("did-before")}`);
    expect(card.textContent).toContain("Version 0.9.0 to 1.0.0");
    await act(async () => {
      fireEvent.click(within(card).getByRole("button", { name: ACCEPT }));
    });
    const confirm = await screen.findByRole("alertdialog");
    expect(confirm.textContent).toContain(sentinel("drift-confirm"));
    expect(confirm.textContent).toContain("an invoice's due date");
    expect(posts(idp)).toEqual([]);
    await act(async () => {
      fireEvent.click(within(confirm).getByRole("button", { name: ACCEPT }));
    });
    await waitFor(() => {
      expect(posts(idp)).toEqual([{ path: "/api/v1/connectors/xero/accept", body: { digest: "c".repeat(64) } }]);
    });
  });

  test("a reader who may not accept is shown the change and offered no accept", async () => {
    // What breaks if this is deleted: anybody who can read the screen is offered a button that
    // agrees a source to a new declaration, or the change is hidden from the people who watch it.
    await consoleAt(connectorAddress("xero"), {
      ...ANSWERS,
      "/api/v1/console/connectors/xero/drift": { body: aDrift({ may_accept: false }) },
    });
    const card = await screen.findByRole("region", { name: DRIFT_HEADING });
    expect(card.textContent).toContain("an invoice's due date");
    expect(within(card).queryByRole("button", { name: ACCEPT })).toBeNull();
  });

  test("a declaration that was not kept lists everything the source does now", async () => {
    // What breaks if this is deleted: a connection agreed before the declaration was kept shows
    // an empty list, which reads as nothing having changed.
    await consoleAt(connectorAddress("xero"), {
      ...ANSWERS,
      "/api/v1/console/connectors/xero/drift": {
        body: aDrift({ known: false, lines: [], now_does: [sentinel("reads-invoices"), sentinel("keeps-status")] }),
      },
    });
    const now = await screen.findByRole("region", { name: NOW_DOES });
    expect(now.textContent).toContain(sentinel("reads-invoices"));
    expect(now.textContent).toContain(sentinel("keeps-status"));
  });

  test("an unchanged source shows no pill and asks for no diff", async () => {
    // What breaks if this is deleted: every source shows a change to accept, which teaches people
    // to accept without reading.
    const { idp } = await consoleAt(connectorAddress("hubspot"));
    expect(document.body.textContent).not.toContain(DECLARATION_CHANGED_WORDS);
    expect(screen.queryByRole("region", { name: DRIFT_HEADING })).toBeNull();
    expect(asked(idp, "/api/v1/console/connectors/hubspot/drift")).toBe(0);
  });
});
