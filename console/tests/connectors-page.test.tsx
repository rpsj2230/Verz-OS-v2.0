/**
 * The Connectors module on the shared page kit: the list of every source, one source's page in its
 * three views, and the acts that change a connection.
 *
 * This is the screen the owner of a fresh install opens to find out what his system has access to,
 * so the failures worth testing are not layout failures. They are: a key reaching the page, a figure
 * drawn where the API sent none, a write sent without a confirmation, an edit that sends a key, a
 * form that says what it accepts only after a refusal, and an act called "coming soon" whose route
 * has arrived.
 *
 * **Reachable means through the application's own route table.** Every page test mounts `routes`
 * from `src/App.tsx` on a memory router, signed in through the real session modules and answered by
 * a stand-in API, so a test passes only if the address resolves.
 *
 * **The bodies are compared with the Python models and the API document rather than with
 * themselves**: `tests/support/python.ts` reads field names out of `brain.connector_routes`, and
 * `tests/support/openapi.ts` the request bodies and paths the routes declare.
 *
 * Task ids: M27.11.9, M27.15.39, M27.15.58, M11.7.7, M27.16.1, M42.6.5
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
import { NOT_CONNECTED_TITLE } from "../src/pages/connectors/ConnectorDashboard";
import { NO_AGENT } from "../src/pages/connectors/ConnectorProfile";
import { connectorAddress, readSourceRows } from "../src/pages/connectors/connectorSources";
import { CONNECT_A_SOURCE, CONNECTORS_HEADING, NOT_AVAILABLE } from "../src/pages/connectors/ConnectorsPage";
import { KEY_SUPPLIED, REVIEW_EDIT, REVIEW_KEY } from "../src/pages/connectors/SourceActs";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { declaredNavigation } from "./support/navigation";
import { apiDocument, declaredPropertyNames, declaredRequestBodySchema } from "./support/openapi";
import { backendModelFields } from "./support/python";
import { installRadixStubs } from "./support/radix";
import { readConsoleFile } from "./support/repo";

const ROUTES = "src/brain/connector_routes.py";
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

function aSource(over: Partial<Connectable> = {}): Connectable {
  return {
    name: "xero",
    label: "Xero",
    settings: [
      { name: "tenant_id", label: "Organisation id", hint: sentinel("tenant-hint"), max_chars: 200, blank: sentinel("tenant-blank") },
    ],
    credential_label: "The key Xero issued for this connection",
    credential_hint: sentinel("key-hint"),
    may_connect: true,
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
    not_connectable: [{ name: "laravel", label: "Laravel database views", why: sentinel("laravel-why") }],
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
  at_least: false,
  periods: ["7d", "30d"].map((range) => ({
    range,
    since: "2019-02-02T00:00:00Z",
    until: "2019-03-04T12:00:00Z",
    attempts: 24,
    read_to_the_end: 22,
    failures: 2,
    quota_waits: 0,
  })),
  unrecorded: [{ figure: "live_reads", why: sentinel("live-reads-why") }],
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
};

interface Answer {
  readonly status?: number;
  readonly body: unknown;
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
};

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
    // The positive sibling: the pattern matches the path it is written for, and not Connect Lark's.
    expect(UNAVAILABLE.test.retiredBy.test("/api/v1/connectors/{connector}/test")).toBe(true);
    expect(UNAVAILABLE.test.retiredBy.test("/api/v1/connectors/lark-app/test")).toBe(false);
  });

  test("the edit and the key replacement send exactly the fields their routes declare, and an edit no key", () => {
    // What breaks if this is deleted: a body key the route forbids with `extra="forbid"`, refused
    // with a 422 naming no field the form can draw, or an edit that carries a key it must not.
    expect(declaredPropertyNames(declaredRequestBodySchema("/api/v1/connectors/{connector}/edit", "post"))).toEqual(["settings"]);
    expect(declaredPropertyNames(declaredRequestBodySchema("/api/v1/connectors/{connector}/key", "post"))).toEqual(["credential"]);
    const acts = readConsoleFile("src/pages/connectors/SourceActs.tsx");
    expect(acts).toContain("const body = { settings: Object.fromEntries(");
    expect(acts).toContain("const body = { credential: secret.take() };");
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
    expect(container.textContent).toContain(sentinel("reading"));
    expect(container.querySelectorAll(`[${UNAVAILABLE_MARK}]`).length).toBeGreaterThan(0);

    const hubspot = await consoleAt(connectorAddress("hubspot"));
    expect(hubspot.container.textContent).toContain(NOT_CONNECTED_TITLE);
    expect(asked(hubspot.idp, "/api/v1/console/connectors/hubspot/stats")).toBe(0);
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
    const advanced = container.querySelector('[data-slot="advanced"]');
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
