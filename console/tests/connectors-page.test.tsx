/**
 * The connectors screen in the browser: what it says about each connected source, connecting one,
 * disconnecting one, and the ways it could reassure somebody wrongly.
 *
 * This is the screen the owner of a fresh install opens to find out what his system has access
 * to, so the failures worth testing are not layout failures. They are: an empty table drawn where
 * nothing looked, a key or a vault path appearing anywhere on the page, a figure drawn for today's
 * use that nothing measured, a connect sent without a confirmation or without saying that nothing
 * will read from the source, and a key left in the page after it was sent.
 *
 * **The columns and bodies are compared with the Python model and the API document rather than
 * with themselves.** `tests/support/python.ts` reads the field names out of
 * `brain.connector_routes`, and `tests/support/openapi.ts` reads the request body the route
 * declares, so a field added on either side and handled nowhere fails here.
 *
 * **The phone case lives in `tests/phone-width.test.tsx` and the notice cases live here.** That
 * file waits for `[role="status"]` to go away before it measures and `ui/Notice.tsx` carries that
 * role, so the states on this screen that draw a notice can never settle there.
 *
 * Task ids: M42.6.5
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { KEY_SUPPLIED, KEEP_UNCONNECTED } from "../src/components/ConnectSource";
import {
  CONNECTED_AT_THE_SERVER,
  DISCONNECT_LABEL,
  KEEP_CONNECTED,
  NONE_OF_YOURS_FROM_HERE,
  NOTHING_LOOKED,
  NOT_YOURS_TO_CONNECT,
  NO_SOURCE_TO_SHOW,
  TESTED_AND_LIVE,
  WHAT_WE_COPY,
  WHICH_SOURCE,
} from "../src/pages/Connectors";
import {
  CONNECTORS_LABEL,
  CONNECTORS_PATH,
  NEVER_READ,
  NOT_TRIED,
  TRUST_COLUMNS,
  TRUST_DETAIL,
  keyWords,
  lastRead,
  offered,
  stateOf,
  type Connectable,
  type Connected,
  type Connectors,
  type Trust,
} from "../src/pages/connectorsQuery";
import { STATE_TONES } from "../src/ui/Status";
import { everythingInStorage, fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { declaredPropertyNames, declaredRequestBodySchema } from "./support/openapi";
import { backendModelFields } from "./support/python";
import { readConsoleFile, readRepoFile } from "./support/repo";

const ROUTES = "src/brain/connector_routes.py";
const API_PATH = "/api/v1/connectors";
const CONSOLE_ORIGIN = "https://console.test";

/** A key nothing else could contain, so finding it anywhere is a leak. */
const KEY = "SOURCE-KEY-SENTINEL-51c0de";

/** A value that appears nowhere else, so a dropped one cannot be covered by another. */
function sentinel(name: string): string {
  return `${name.toUpperCase()}-SENTINEL`;
}

/** The vault path a connected source's key is kept at, which must never reach this console. */
const VAULT_PATH = "connector_keys/xero";

beforeAll(async () => {
  await import("../src/pages/Connectors");
}, 60_000);

function aTrust(over: Partial<Trust> = {}): Trust {
  return {
    name: "xero",
    wiring: "rest",
    credential: sentinel("key-sentence"),
    budget: sentinel("ceiling-sentence"),
    projected_fields: 9,
    checked_at: null,
    health: "",
    lifecycle: "registered",
    serving: false,
    version: "1.0.0",
    reaches: sentinel("reaches"),
    access: sentinel("access"),
    permission_sync: sentinel("sync"),
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
    trust: aTrust(),
    may_disconnect: true,
    last_synced_at: null,
    next_sync_at: null,
    sync: sentinel("reading"),
    ...over,
  };
}

function aSource(over: Partial<Connectable> = {}): Connectable {
  return {
    name: "xero",
    label: "Xero",
    settings: [
      {
        name: "tenant_id",
        label: "Organisation id",
        hint: sentinel("tenant-hint"),
        max_chars: 200,
        blank: sentinel("tenant-blank"),
      },
    ],
    credential_label: "The key Xero issued for this connection",
    credential_hint: sentinel("key-hint"),
    may_connect: true,
    ...over,
  };
}

function aBody(over: Partial<Connectors> = {}): Connectors {
  return {
    connectors: [aConnected()],
    unread: "",
    connecting: sentinel("connecting"),
    confirm_connect: sentinel("confirm-connect"),
    confirm_disconnect: sentinel("confirm-disconnect"),
    copy_policy: [
      { what: sentinel("copied-thing"), verdict: "projected", why: sentinel("copied-why") },
      { what: sentinel("never-thing"), verdict: "never", why: sentinel("never-why") },
    ],
    budget_unread: sentinel("no-numerator"),
    may_connect: true,
    vault: "ready",
    vault_told: "",
    connectable: [aSource(), aSource({ name: "hubspot", label: "HubSpot", may_connect: false })],
    not_connectable: [{ name: "freshdesk", label: "Freshdesk", why: sentinel("freshdesk-why") }],
    evidence: [
      {
        name: "xero",
        label: "Xero",
        recorded: sentinel("xero-recorded"),
        credential: sentinel("xero-credential"),
        live_read: sentinel("xero-live"),
        last_read_live_at: "2019-03-04T09:30:00Z",
      },
      {
        name: "freshdesk",
        label: "Freshdesk",
        recorded: sentinel("freshdesk-recorded"),
        credential: sentinel("freshdesk-credential"),
        live_read: "",
        last_read_live_at: null,
      },
    ],
    key_max_chars: 1000,
    key_blank: sentinel("key-blank"),
    ...over,
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

type Answer = (url: URL, init: RequestInit | undefined) => Response | null;

/** Mount the page against a stand-in API and wait for the first read to settle. */
async function mount(answer: Answer): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      return answer(new URL(url, CONSOLE_ORIGIN), init);
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { Connectors: Page } = await import("../src/pages/Connectors");
  const router = createMemoryRouter([{ path: "/connectors", element: <Page /> }], {
    initialEntries: ["/connectors"],
  });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector("h1") || container.querySelector(".note[role='status']")) {
      throw new Error("still reading");
    }
  });
  return { container, idp };
}

/** A page whose API answers the listing with one body and refuses everything else. */
function answering(body: unknown): Answer {
  return (url, init) => (url.pathname === API_PATH && init?.method !== "POST" ? json(body) : null);
}

function posts(idp: FakeIdp): { path: string; body: unknown }[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST" && new URL(call.url, CONSOLE_ORIGIN).pathname.startsWith("/api/"))
    .map((call) => ({
      path: new URL(call.url, CONSOLE_ORIGIN).pathname,
      body: call.init?.body === undefined ? undefined : (JSON.parse(String(call.init.body)) as unknown),
    }));
}

function button(scope: ParentNode, name: string): HTMLButtonElement {
  const found = [...scope.querySelectorAll("button")].find(
    (one) => one.textContent === name || one.getAttribute("aria-label")?.startsWith(name),
  );
  if (!found) {
    throw new Error(`no button named ${name}`);
  }
  return found as HTMLButtonElement;
}

function input(container: HTMLElement, id: string): HTMLInputElement {
  const found = container.querySelector(`#${id}`);
  if (!found) {
    throw new Error(`no control #${id}`);
  }
  return found as HTMLInputElement;
}

function confirmPanel(container: HTMLElement): HTMLElement {
  const found = container.querySelector(".confirm");
  if (!found) {
    throw new Error("no confirmation is open");
  }
  return found as HTMLElement;
}

// --- what this page agrees with the API about ---------------------------------------------------

describe("what this page agrees with the API about", () => {
  test("every field the API sends about what a source may read is drawn somewhere", () => {
    // What breaks if this is deleted: a field added to the row model arrives and is dropped
    // silently, which on this screen means a fact about what a source may do to a client's
    // system that nobody sees. The names come out of the Python source.
    const drawn = [...TRUST_COLUMNS.map((one) => one.field), ...TRUST_DETAIL.map((one) => one.field)];

    expect([...drawn].sort()).toEqual(backendModelFields(ROUTES, "TrustView").sort());
  });

  test("a connect sends exactly the fields the route declares, and only the settings the source asks for", async () => {
    // What breaks if this is deleted: a body key the route forbids with `extra="forbid"`, which the
    // API refuses with a 422 naming no field the form can draw, or a setting left over from another
    // source sent to this one.
    const declared = declaredPropertyNames(declaredRequestBodySchema(API_PATH, "post"));
    const { connectionBody } = await import("../src/pages/connectorsQuery");
    const body = connectionBody(aSource(), { tenant_id: "t", portal_id: "left-over" }, KEY);

    expect(Object.keys(body).sort()).toEqual(declared);
    expect(body).toEqual({ connector: "xero", settings: { tenant_id: "t" }, credential: KEY });
  });

  test("no sentence this screen shows can choose a colour", () => {
    // What breaks if this is deleted: somebody adds a word from one of these sentences to the one
    // table in this console where a value picks a tone, and a connector that may write to a
    // client's finance system renders green.
    expect(Object.keys(STATE_TONES)).not.toContain(NOT_TRIED);
    for (const word of ["read_only", "write", "none", "predicate", "delegated", "registered"]) {
      expect(Object.keys(STATE_TONES)).not.toContain(word);
    }
  });

  test("nothing on this screen reads a total, a count or a numerator off a response", () => {
    // What breaks if this is deleted: the page grows "showing 3 of 14", which on the one screen
    // whose subject is reach is the disclosure by subtraction with every value correct.
    for (const source of [
      "src/pages/connectorsQuery.ts",
      "src/pages/Connectors.tsx",
      "src/components/ConnectSource.tsx",
      "src/setup/ConnectSourcesStep.tsx",
    ]) {
      const text = readConsoleFile(source);
      expect(text, source).not.toMatch(/\.total\b/);
      expect(text, source).not.toMatch(/\.truncated\b/);
      expect(text, source).not.toMatch(/\.used\b/);
    }
  });

  test("the shell offers this screen under the label the design names, in Operate", () => {
    // What breaks if this is deleted: the entry drifts to the registry's title, "Connector health",
    // and `brain.ops.console_design.navigation_gaps` reports a screen that cannot be found.
    const shell = readConsoleFile("src/layout/Shell.tsx");
    expect(shell).toContain(`{ to: "${CONNECTORS_PATH}", label: "${CONNECTORS_LABEL}" }`);
    expect(shell.indexOf(CONNECTORS_PATH)).toBeLessThan(shell.indexOf('label: "Roles"'));
  });

  test("no row model carries a field that could hold a vault path or a key", () => {
    // What breaks if this is deleted: somebody adds `slot` or `key` to a row and a column for it,
    // which is how a vault path reaches a screenshot in a support chat.
    for (const model of ["TrustView", "ConnectedView", "ConnectorsView", "ConnectorChangedView"]) {
      const fields = backendModelFields(ROUTES, model);
      for (const forbidden of ["path", "slot", "secret", "vault_path", "token", "key"]) {
        expect(fields, model).not.toContain(forbidden);
      }
    }
    // `credential` is on the trust row as the API's sentence about the key, and on no response
    // besides; the request body is where a key travels, and that model is not a response.
    for (const model of ["ConnectedView", "ConnectorsView", "ConnectorChangedView"]) {
      expect(backendModelFields(ROUTES, model), model).not.toContain("credential");
    }
    expect(readConsoleFile("src/components/ConnectSource.tsx")).not.toMatch(/type="password"/);
  });

  test("the sources the wizard named are offered first, and only sources this reader may connect", () => {
    // What breaks if this is deleted: first run offers a form for a source the API said this person
    // may not connect, or the order the person typed is lost.
    const hubspot = aSource({ name: "hubspot", label: "HubSpot" });
    const others = aSource({ name: "other", label: "Other", may_connect: false });

    expect(offered([aSource(), hubspot, others], " hubspot , nothing").map((one) => one.name)).toEqual([
      "hubspot",
      "xero",
    ]);
    expect(offered([others])).toEqual([]);
  });
});

// --- what the screen draws ----------------------------------------------------------------------

describe("the connectors screen", () => {
  test("every connected source reaches the table with who connected it, its key and its sentences", async () => {
    // What breaks if this is deleted: the positive case goes untested, and every assertion below
    // about what must not appear is satisfied by a page that draws nothing at all.
    const { container } = await mount(answering(aBody()));

    const text = container.textContent ?? "";
    for (const one of ["reaches", "access", "sync", "reading", "key-sentence", "declaration", "copied-why", "never-why"]) {
      expect(text).toContain(sentinel(one));
    }
    expect(text).toContain("xero");
    expect(text).toContain("u_admin");
    expect(text).toContain(keyWords(aConnected()));
    expect(text).toContain("9 fields");
    expect(readRepoFile("docs/screens.html")).toContain(WHAT_WE_COPY);
    expect(text).toContain(WHAT_WE_COPY);
  });

  test("every connector says what it was tested against apart from whether it is live here", async () => {
    // What breaks if this is deleted: the recordings sentence and the live one can be merged into
    // one badge, and a connector tested against documented shapes reads as one working here.
    const { container } = await mount(answering(aBody()));
    const card = [...container.querySelectorAll("section")].find((one) =>
      one.textContent?.includes(TESTED_AND_LIVE),
    );
    const text = card?.textContent ?? "";

    for (const one of ["xero-recorded", "xero-credential", "xero-live", "freshdesk-recorded", "freshdesk-credential"]) {
      expect(text).toContain(sentinel(one));
    }
    expect(text).toContain("2019-03-04 09:30");
    expect(card?.querySelectorAll("dt").length).toBe(5);
  });

  test("the last read is the last time a source was read to the end, and never the last attempt", async () => {
    // What breaks if this is deleted: the last-read column draws the attempt's time, and a source
    // whose key expired, attempted every hour and read never, shows as read an hour ago.
    const failing = aConnected({
      trust: aTrust({ checked_at: "2019-03-06T10:00:00Z", health: "down" }),
      last_synced_at: "2019-03-04T09:30:00Z",
      next_sync_at: "2019-03-06T11:00:00Z",
    });

    expect(lastRead(failing)).toBe("2019-03-04 09:30");
    expect(lastRead(aConnected())).toBe(NEVER_READ);
    const { container } = await mount(answering(aBody({ connectors: [failing] })));
    const text = container.textContent ?? "";
    expect(text).toContain("2019-03-04 09:30");
    expect(text).toContain(sentinel("reading"));
  });

  test("a source nothing has tried, and one this release cannot rebuild, each show words rather than blanks", async () => {
    // What breaks if this is deleted: an empty state cell, which reads as nothing being wrong with a
    // source nobody has reached, or a connection with no trust row drawn as an empty line.
    expect(stateOf(aTrust({ health: "" }))).toBe(NOT_TRIED);
    const { container } = await mount(
      answering(
        aBody({
          connectors: [
            aConnected(),
            aConnected({ name: "laravel", trust: null, pinned: false, key_held: null, declaration: sentinel("unreadable") }),
          ],
        }),
      ),
    );

    expect(container.textContent).toContain(NOT_TRIED);
    expect(container.textContent).toContain(NEVER_READ);
    expect(container.textContent).toContain(sentinel("unreadable"));
    expect(container.textContent).toContain("Not known");
  });

  test("nothing looked and nothing connected are drawn differently", async () => {
    // What breaks if this is deleted: an install where nothing can say what is connected renders as
    // an install that reads no outside data.
    const unread = await mount(answering(aBody({ connectors: null, unread: sentinel("nothing-looked") })));
    expect(unread.container.textContent).toContain(NOTHING_LOOKED);
    expect(unread.container.textContent).toContain(sentinel("nothing-looked"));
    expect(unread.container.querySelector("table")).toBeNull();

    const empty = await mount(answering(aBody({ connectors: [] })));
    expect(empty.container.textContent).toContain(NO_SOURCE_TO_SHOW);
    expect(empty.container.textContent).not.toContain(NOTHING_LOOKED);
  });

  test("the ceiling column carries the API's reason for having no figure for today", async () => {
    // What breaks if this is deleted: the column reads as the whole answer, and somebody plans a
    // backfill believing the screen would have shown how much of the allowance was already spent.
    const { container } = await mount(answering(aBody()));

    expect(container.textContent).toContain(sentinel("no-numerator"));
  });

  test("a reader who may not connect is told what connecting does and gets no form", async () => {
    // What breaks if this is deleted: a form drawn for a reader the API said may connect nothing,
    // or the sentence about what connecting does not do dropped for the reader who has to ask
    // somebody else to do it. The sources connected at the server are explained to everybody.
    const { container } = await mount(
      answering(
        aBody({
          may_connect: false,
          connectable: [aSource({ may_connect: false })],
          connectors: [aConnected({ may_disconnect: false })],
        }),
      ),
    );

    expect(container.textContent).toContain(sentinel("connecting"));
    expect(container.textContent).toContain(NOT_YOURS_TO_CONNECT);
    expect(container.textContent).toContain(CONNECTED_AT_THE_SERVER);
    expect(container.textContent).toContain(sentinel("freshdesk-why"));
    expect(container.querySelector("input")).toBeNull();
    expect(container.querySelector("select")).toBeNull();
    expect(container.querySelectorAll("button")).toHaveLength(0);

    // The sibling: a grant that covers only sources this screen cannot connect is told that, and
    // not that it holds no grant, which would send the reader to ask for one they already have.
    const scoped = await mount(answering(aBody({ may_connect: true, connectable: [aSource({ may_connect: false })] })));
    expect(scoped.container.textContent).toContain(NONE_OF_YOURS_FROM_HERE);
    expect(scoped.container.textContent).not.toContain(NOT_YOURS_TO_CONNECT);
  });

  test("connecting is confirmed in the API's words, sends the key once, and keeps it out of the page", async () => {
    // What breaks if this is deleted: M42.6.5's control. A connect sent with no second step, a
    // confirmation that shows the key, a key left in the field or anywhere in the document or a
    // browser store after it was sent, or a success that does not read the list again.
    let connected = false;
    const { container, idp } = await mount((url, init) => {
      if (url.pathname !== API_PATH) {
        return null;
      }
      if (init?.method === "POST") {
        connected = true;
        return json({
          connector: "xero",
          change: "connected",
          changed_at: "2019-03-04T10:00:00Z",
          key_written_at: "2019-03-04T10:00:00Z",
          told: sentinel("connected-told"),
        });
      }
      return json(aBody({ connectors: connected ? [aConnected()] : [] }));
    });

    const which = container.querySelector("#connect-which") as HTMLSelectElement;
    expect(container.textContent).toContain(WHICH_SOURCE);
    expect([...which.options].map((one) => one.textContent)).toEqual(["Xero"]);
    fireEvent.change(which, { target: { value: "xero" } });
    expect(container.textContent).toContain(sentinel("tenant-hint"));
    expect(container.textContent).toContain(sentinel("key-hint"));

    fireEvent.change(input(container, "connect-xero-tenant_id"), { target: { value: "11111111" } });
    fireEvent.change(input(container, "connect-xero-credential"), { target: { value: KEY } });
    fireEvent.submit(input(container, "connect-xero-credential").form as HTMLFormElement);

    const panel = confirmPanel(container);
    expect(panel.textContent).toContain(sentinel("confirm-connect"));
    expect(panel.textContent).toContain("11111111");
    expect(panel.textContent).toContain(KEY_SUPPLIED);
    expect(panel.innerHTML).not.toContain(KEY);
    expect(posts(idp)).toEqual([]);

    fireEvent.click(button(panel, "Connect Xero"));
    await waitFor(() => {
      expect(container.textContent).toContain(sentinel("connected-told"));
    });
    expect(posts(idp)).toEqual([
      { path: API_PATH, body: { connector: "xero", settings: { tenant_id: "11111111" }, credential: KEY } },
    ]);
    expect(container.innerHTML).not.toContain(KEY);
    expect(JSON.stringify(everythingInStorage())).not.toContain(KEY);
    await waitFor(() => {
      expect(container.textContent).toContain(sentinel("declaration"));
    });
  });

  test("a connection sent blank opens no confirmation, sends nothing, and says what to fill in, in the API's words", async () => {
    // What breaks if this is deleted: a confirmation about nothing that a person can agree to and
    // be refused for afterwards, or blank sentences typed into the console that part from the ones
    // the API answers with. The sentences are the ones the API served beside the form.
    const { container, idp } = await mount(answering(aBody({ connectors: [] })));

    fireEvent.submit(input(container, "connect-xero-credential").form as HTMLFormElement);

    expect(container.querySelector(".confirm")).toBeNull();
    expect(posts(idp)).toEqual([]);
    expect(container.querySelector("#connect-xero-tenant_id-problem")?.textContent).toContain(sentinel("tenant-blank"));
    expect(container.querySelector("#connect-xero-credential-problem")?.textContent).toContain(sentinel("key-blank"));
  });

  test("a refused connection shows each problem beside its field and asks for the key again", async () => {
    // What breaks if this is deleted: a 422 reads as a generic failure, the key stays in the field
    // for the next person at the screen, or keeping things as they are sends something.
    const { container, idp } = await mount((url, init) => {
      if (url.pathname !== API_PATH) {
        return null;
      }
      if (init?.method === "POST") {
        return json(
          {
            problems: [
              { field: "tenant_id", code: "refused", message: sentinel("tenant-refused") },
              { field: "credential", code: "not_one_piece", message: sentinel("key-refused") },
            ],
          },
          422,
        );
      }
      return json(aBody({ connectors: [] }));
    });
    fireEvent.change(container.querySelector("#connect-which") as HTMLSelectElement, { target: { value: "xero" } });
    fireEvent.change(input(container, "connect-xero-tenant_id"), { target: { value: "*" } });
    fireEvent.change(input(container, "connect-xero-credential"), { target: { value: `${KEY} x` } });

    fireEvent.submit(input(container, "connect-xero-credential").form as HTMLFormElement);
    fireEvent.click(button(confirmPanel(container), KEEP_UNCONNECTED));
    expect(posts(idp)).toEqual([]);
    expect(input(container, "connect-xero-credential").value).toBe(`${KEY} x`);

    fireEvent.submit(input(container, "connect-xero-credential").form as HTMLFormElement);
    fireEvent.click(button(confirmPanel(container), "Connect Xero"));
    await waitFor(() => {
      expect(container.querySelector("#connect-xero-tenant_id-problem")?.textContent).toContain(
        sentinel("tenant-refused"),
      );
    });
    expect(container.querySelector("#connect-xero-credential-problem")?.textContent).toContain(sentinel("key-refused"));
    expect(input(container, "connect-xero-tenant_id").getAttribute("aria-describedby")).toBe(
      "connect-xero-tenant_id-problem",
    );
    expect(input(container, "connect-xero-credential").value).toBe("");
    expect(container.innerHTML).not.toContain(KEY);
  });

  test("disconnecting is confirmed in the API's words and keeping it connected sends nothing", async () => {
    // What breaks if this is deleted: a disconnect with no second step, or one whose confirmation
    // does not say that the key stays in the vault, which is the sentence the API sends.
    let gone = false;
    const { container, idp } = await mount((url, init) => {
      if (url.pathname === `${API_PATH}/xero/disconnect` && init?.method === "POST") {
        gone = true;
        return json({
          connector: "xero",
          change: "disconnected",
          changed_at: "2019-03-04T10:00:00Z",
          key_written_at: null,
          told: sentinel("disconnected-told"),
        });
      }
      return url.pathname === API_PATH ? json(aBody({ connectors: gone ? [] : [aConnected()] })) : null;
    });

    fireEvent.click(button(container, DISCONNECT_LABEL));
    expect(confirmPanel(container).textContent).toContain(sentinel("confirm-disconnect"));
    fireEvent.click(button(confirmPanel(container), KEEP_CONNECTED));
    expect(posts(idp)).toEqual([]);

    fireEvent.click(button(container, DISCONNECT_LABEL));
    fireEvent.click(button(confirmPanel(container), DISCONNECT_LABEL));
    await waitFor(() => {
      expect(container.textContent).toContain(sentinel("disconnected-told"));
    });
    expect(posts(idp)).toEqual([{ path: `${API_PATH}/xero/disconnect`, body: undefined }]);
    await waitFor(() => {
      expect(container.textContent).toContain(NO_SOURCE_TO_SHOW);
    });
  });

  test("the vault's own sentence is drawn when it has something to say", async () => {
    // What breaks if this is deleted: an install with no vault offers a form whose every submit is
    // refused, with nothing on the screen saying why before the person types a key.
    const { container } = await mount(answering(aBody({ vault: "absent", vault_told: sentinel("no-vault") })));

    expect(container.textContent).toContain(sentinel("no-vault"));
  });

  test("this console draws no vault path, whatever a sentence it was sent contains", async () => {
    // What breaks if this is deleted: somebody adds a slot to a row and a column for it here. The
    // API sends none, and nothing in this console's own source names one either.
    const { container } = await mount(answering(aBody()));

    expect(container.textContent).not.toContain(VAULT_PATH);
    for (const source of ["src/pages/connectorsQuery.ts", "src/pages/Connectors.tsx", "src/components/ConnectSource.tsx"]) {
      expect(readConsoleFile(source), source).not.toMatch(/connector_keys/);
    }
  });
});
