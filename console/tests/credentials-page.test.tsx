/**
 * The Credentials module on the shared page kit: the list of every slot under the vault's state, one
 * slot's three views, and the write-only form, reached through the application's own route table.
 *
 * The failures worth testing look like the page working: a value drawn back after a save, a vault
 * path in the page text, a sealed vault drawn as slots that hold nothing, a live read waiting on the
 * owner that nobody is told of, a last use that nothing records drawn as a time, and a key pair sent
 * as two writes.
 *
 * Task ids: M27.11.10, M27.15.50, M27.16.1, M27.8.7, M13.8.10
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { NOT_RECORDED } from "../src/components/kit";
import { UNAVAILABLE } from "../src/pages/credentials/credentialActions";
import { CREDENTIALS_HEADING, NOT_OUTRANKED } from "../src/pages/credentials/CredentialsPage";
import { SET_VALUE, REPLACE_VALUE, KEEP_IT, TYPE_FIRST } from "../src/pages/credentials/SetValueForm";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { apiDocument } from "./support/openapi";
import { installRadixStubs } from "./support/radix";

const CONSOLE_ORIGIN = "https://console.test";
const LIST = "/api/v1/credentials";
const SENTINEL = "sk-sentinel-never-drawn";
const AT = "2019-03-04T05:06:07Z";
const WAITING = "Answers cannot read connected sources live yet: load the policies again.";
const FORMAT = "One unbroken line of at most 1,000 characters.";
const HELD = "Template signing key: held. Agents can be published and installed from the console.";
const KEY_WAITING = "Template signing key: not yet created, waiting for the vault policy reload.";

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/Credential");
}, 60_000);

function vault(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    seal: "open",
    told: "The secrets vault is open.",
    slots_unread: "",
    token_policy: "own",
    token_policies: ["application", "default"],
    token_told: "",
    live_reads: "ready",
    live_reads_told: "Answers can read a connected source live.",
    template_key: "held",
    template_key_told: HELD,
    ...overrides,
  };
}

function row(slot: string, overrides: Record<string, unknown> = {}): Record<string, unknown> {
  const [family = "", name = ""] = slot.split("/");
  return {
    slot,
    family,
    name,
    kind: "provider",
    holder: name,
    state: "held",
    held: true,
    set_at: AT,
    outranked_by: null,
    read_by: "application",
    writable: true,
    write_told: "",
    ...overrides,
  };
}

function detail(slot: string, overrides: Record<string, unknown> = {}, rowOverrides: Record<string, unknown> = {}) {
  return {
    vault: vault(),
    row: row(slot, rowOverrides),
    description: "The password for the relay's user name.",
    fields: [{ field: "value", label: "Password", accepts: FORMAT }],
    ask_for: ["the password of a relay user that may only send mail"],
    never: ["a mailbox administrator's password"],
    takes_effect: "next_use",
    takes_effect_told: "The password is held in the vault and is used for the next message sent.",
    use_recorded: false,
    last_used_at: null,
    last_used_told: "Nothing records when mail is sent with the password, so no time is shown.",
    history: [
      { at: AT, by: "Ada Admin", by_id: "u_ada" },
      { at: AT, by: "The setup wizard", by_id: "first-run" },
    ],
    history_told: "Every value written into this slot, from the audit ledger.",
    ...overrides,
  };
}

interface Sent {
  readonly method: string;
  readonly path: string;
  readonly body: unknown;
}

interface Mounted {
  readonly container: HTMLElement;
  readonly idp: FakeIdp;
  readonly sent: Sent[];
}

async function consoleAt(path: string, answer: (method: string, path: string, body: unknown) => unknown): Promise<Mounted> {
  const sent: Sent[] = [];
  const idp = fakeIdentityProvider({
    api(url, init) {
      const where = new URL(url, CONSOLE_ORIGIN).pathname;
      const method = (init?.method ?? "GET").toUpperCase();
      const body = typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : null;
      sent.push({ method, path: where, body });
      const found = answer(method, where, body);
      if (found === undefined) {
        return null;
      }
      return new Response(JSON.stringify(found), { status: 200, headers: { "content-type": "application/json" } });
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector("h1") || container.querySelector('[data-slot="loading-state"]')) {
      throw new Error("the page has not arrived");
    }
  });
  return { container, idp, sent };
}

function button(root: ParentNode, name: string): HTMLButtonElement {
  const found = [...root.querySelectorAll("button")].find((one) => one.textContent?.trim() === name);
  if (found === undefined) {
    throw new Error(`No button reading ${name}.`);
  }
  return found;
}

describe("the list", () => {
  test("every slot is drawn by name and kind with whether a value is held, when, and what outranks it, and never a path", async () => {
    // What breaks if this is deleted: the one screen that lists every secret loses a column, draws a
    // vault path as the row's name, or calls an outranked key in use.
    const { container } = await consoleAt("/credentials", (method, path) =>
      method === "GET" && path === LIST
        ? {
            vault: vault(),
            items: [
              row("providers/anthropic", { holder: "Anthropic (Claude)", outranked_by: "ANTHROPIC_API_KEY" }),
              row("providers/openai", { holder: "OpenAI", state: "empty", held: false, set_at: null }),
              row("connector_keys/xero", { holder: "Xero", kind: "connector", state: "defined", held: false, set_at: null, writable: false, write_told: "Its first key goes in when the source is connected." }),
            ],
            next_cursor: null,
          }
        : undefined,
    );
    const table = container.querySelector('[data-slot="entity-table"]')?.textContent ?? "";

    expect(container.querySelector("h1")?.textContent).toBe(CREDENTIALS_HEADING);
    expect(table).toContain("Anthropic (Claude)");
    expect(table).toContain("Model provider");
    expect(table).toContain("Connected source");
    expect(table).toContain("2019-03-04 05:06 UTC");
    expect(table).toContain("Outranked by ANTHROPIC_API_KEY");
    expect(table).toContain(NOT_OUTRANKED);
    expect(table).toContain("Defined, empty");
    expect(container.textContent).not.toContain("connector_keys/xero");
    expect(container.textContent).not.toContain("providers/anthropic");
    const links = [...container.querySelectorAll('[data-slot="entity-table"] tbody a')].map((one) => one.getAttribute("href"));
    expect(links).toContain("/credentials/providers/anthropic");
  });

  test("the vault's seal and policies are above the list, and a live read waiting on the owner is said", async () => {
    // What breaks if this is deleted: needs-rupash 99's reload is waited on with nothing on the
    // screen saying so, or the sentence is drawn when nothing waits.
    const waiting = await consoleAt("/credentials", (method, path) =>
      path === LIST ? { vault: vault({ live_reads: "waiting", live_reads_told: WAITING }), items: [row("providers/anthropic")], next_cursor: null } : undefined,
    );
    const card = waiting.container.querySelector('[aria-label="The vault\'s state"]')?.textContent ?? "";
    expect(card).toContain("Unsealed");
    expect(card).toContain("application, default");
    expect(card).toContain(WAITING);

    const ready = await consoleAt("/credentials", (method, path) =>
      path === LIST ? { vault: vault(), items: [row("providers/anthropic")], next_cursor: null } : undefined,
    );
    expect(ready.container.textContent).not.toContain(WAITING);
  });

  test("the vault card says whether the template signing key is held, in the API's sentence", async () => {
    // What breaks if this is deleted: needs-rupash 82's key waits on the owner's policy reload with
    // nothing on the screen saying so, or the card draws a held key after the API said otherwise.
    const waiting = await consoleAt("/credentials", (method, path) =>
      path === LIST
        ? { vault: vault({ template_key: "waiting", template_key_told: KEY_WAITING }), items: [row("providers/anthropic")], next_cursor: null }
        : undefined,
    );
    const card = waiting.container.querySelector('[aria-label="The vault\'s state"]')?.textContent ?? "";
    expect(card).toContain("Template signing key");
    expect(card).toContain(KEY_WAITING);
    expect(card).not.toContain(HELD);

    const held = await consoleAt("/credentials", (method, path) =>
      path === LIST ? { vault: vault(), items: [row("providers/anthropic")], next_cursor: null } : undefined,
    );
    const heldCard = held.container.querySelector('[aria-label="The vault\'s state"]')?.textContent ?? "";
    expect(heldCard).toContain(HELD);
    expect(heldCard).not.toContain(KEY_WAITING);
  });

  test("a sealed vault is said, and a slot it could not read is not known rather than empty", async () => {
    // What breaks if this is deleted: a sealed vault reads as a vault with no keys.
    const sealed = "The secrets vault is sealed, so nothing can read or keep a credential.";
    const { container } = await consoleAt("/credentials", (method, path) =>
      path === LIST
        ? {
            vault: vault({ seal: "sealed", told: sealed, token_policies: [] }),
            items: [row("providers/anthropic", { state: "unknown", held: null, set_at: null, writable: false, write_told: sealed })],
            next_cursor: null,
          }
        : undefined,
    );
    expect(container.textContent).toContain("Sealed");
    expect(container.textContent).toContain(sealed);
    expect(container.querySelector('[data-slot="entity-table"]')?.textContent).toContain("Not known");
    expect(container.querySelector('[data-slot="entity-table"]')?.textContent).not.toContain("Empty");
  });
});

describe("one slot", () => {
  const RELAY = "/api/v1/credentials/providers/mail_relay";

  test("the Dashboard draws when it was set, and a last use nothing records as not recorded, never as a time", async () => {
    // What breaks if this is deleted: a last use drawn as a date nothing measured, or the count of
    // changes drawn where the ledger could not be read.
    const { container } = await consoleAt("/credentials/providers/mail_relay", (method, path) =>
      path === RELAY ? detail("providers/mail_relay", {}, { holder: "Mail relay", kind: "relay" }) : undefined,
    );
    const figure = (label: string): string =>
      [...container.querySelectorAll('[data-slot="stat-card"]')]
        .find((one) => one.querySelector("dt")?.textContent === label)
        ?.querySelector("dd")?.textContent ?? "";
    expect(container.querySelector("h1")?.textContent).toBe("Mail relay");
    expect(figure("Last set")).toBe("2019-03-04 05:06 UTC");
    expect(figure("Last used")).toContain(NOT_RECORDED);
    expect(figure("Last used")).toContain("Nothing records when mail is sent");
    expect(figure("Last used")).not.toMatch(/\d{4}-\d{2}-\d{2}/);
    expect(figure("Changes recorded")).toBe("2");
    expect(container.textContent).not.toContain("providers/mail_relay");
  });

  test("the About view names who wrote each value, and keeps the path and the ids in Advanced", async () => {
    // What breaks if this is deleted: the history names people by their ledger ids in the page text,
    // or loses the path an administrator quotes in a support request.
    const { container } = await consoleAt("/credentials/providers/mail_relay/about", (method, path) =>
      path === RELAY ? detail("providers/mail_relay", {}, { holder: "Mail relay", kind: "relay" }) : undefined,
    );
    const history = container.querySelector('table[aria-label="History"]')?.textContent ?? "";
    expect(history).toContain("Ada Admin");
    expect(history).toContain("The setup wizard");
    expect(history).not.toContain("u_ada");
    const advanced = container.querySelector('[data-slot="advanced"]')?.textContent ?? "";
    expect(advanced).toContain("providers/mail_relay");
    expect(advanced).toContain("u_ada");
  });

  test("a value is sent only from its confirmation, is never drawn back, and what the field accepts is said before it is sent", async () => {
    // What breaks if this is deleted: M27.8.7 on this page. A value that lingers in the field or the
    // page after a save, a write sent with one press, or a format a person learns only from a refusal.
    const { container, sent } = await consoleAt("/credentials/providers/mail_relay/profile", (method, path) => {
      if (method === "PUT" && path === RELAY) {
        return { slot: "providers/mail_relay", held: true, set_at: AT, in_use: "next_use", told: "TOLD-SENTINEL" };
      }
      return path === RELAY ? detail("providers/mail_relay", {}, { holder: "Mail relay", kind: "relay" }) : undefined;
    });
    const puts = () => sent.filter((one) => one.method === "PUT");

    expect(container.textContent).toContain(FORMAT);
    fireEvent.click(button(container, REPLACE_VALUE));
    expect(container.textContent).toContain(TYPE_FIRST);
    expect(puts()).toEqual([]);

    const input = container.querySelector<HTMLInputElement>('[data-slot="secret-field"] input');
    if (input === null) {
      throw new Error("No secret field was drawn.");
    }
    fireEvent.input(input, { target: { value: SENTINEL } });
    fireEvent.click(button(container, REPLACE_VALUE));
    fireEvent.click(button(document.body, KEEP_IT));
    expect(puts()).toEqual([]);

    fireEvent.click(button(container, REPLACE_VALUE));
    const dialog = document.body.querySelector('[data-slot="confirm-dialog"]');
    expect(dialog?.textContent).toContain("Replace the credential for Mail relay?");
    fireEvent.click(button(dialog ?? document.body, REPLACE_VALUE));
    await waitFor(() => {
      expect(container.textContent).toContain("TOLD-SENTINEL");
    });
    expect(puts()).toEqual([{ method: "PUT", path: RELAY, body: { value: SENTINEL } }]);
    expect(document.body.innerHTML).not.toContain(SENTINEL);
  });

  test("a key pair is one write of both fields, and a slot that is not offered says why and draws no form", async () => {
    // What breaks if this is deleted: the object store's pair is sent as two writes, or a source's
    // slot with no first key offers a form the API will refuse.
    const STORE = "/api/v1/credentials/providers/seaweedfs";
    const { container, sent } = await consoleAt("/credentials/providers/seaweedfs/profile", (method, path) => {
      if (method === "PUT") {
        return { slot: "providers/seaweedfs", held: true, set_at: AT, in_use: "at_start", told: "Restart the system." };
      }
      return path === STORE
        ? detail(
            "providers/seaweedfs",
            {
              fields: [
                { field: "access_key_id", label: "Access key ID", accepts: FORMAT },
                { field: "secret_access_key", label: "Secret access key", accepts: FORMAT },
              ],
            },
            { holder: "File store (SeaweedFS)", kind: "store", state: "empty", held: false, set_at: null },
          )
        : undefined;
    });
    const inputs = [...container.querySelectorAll<HTMLInputElement>('[data-slot="secret-field"] input')];
    expect(inputs).toHaveLength(2);
    inputs.forEach((one, index) => {
      fireEvent.input(one, { target: { value: `${SENTINEL}-${String(index)}` } });
    });
    fireEvent.click(button(container, SET_VALUE));
    fireEvent.click(button(document.body.querySelector('[data-slot="confirm-dialog"]') ?? document.body, SET_VALUE));
    await waitFor(() => {
      expect(container.textContent).toContain("Restart the system.");
    });
    expect(sent.filter((one) => one.method === "PUT")).toEqual([
      {
        method: "PUT",
        path: STORE,
        body: { values: { access_key_id: `${SENTINEL}-0`, secret_access_key: `${SENTINEL}-1` } },
      },
    ]);

    const refused = "Its first key goes in when the source is connected.";
    const xero = await consoleAt("/credentials/connector_keys/xero/profile", (method, path) =>
      path === "/api/v1/credentials/connector_keys/xero"
        ? detail("connector_keys/xero", {}, { holder: "Xero", kind: "connector", state: "defined", held: false, writable: false, write_told: refused })
        : undefined,
    );
    expect(xero.container.textContent).toContain(refused);
    expect(xero.container.querySelector('[data-slot="secret-field"]')).toBeNull();
  });
});

describe("what cannot be done yet", () => {
  test("every act drawn as coming soon has no route in the API document yet", () => {
    // What breaks if this is deleted: a route lands and the page goes on saying the act is coming,
    // so a person is told they cannot do what they can.
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    for (const [act, { retiredBy }] of Object.entries(UNAVAILABLE)) {
      expect(paths.filter((path) => retiredBy.test(path)), act).toEqual([]);
    }
    expect(UNAVAILABLE.checkSource.retiredBy.test("/api/v1/connectors/{connector}/test")).toBe(true);
    // The positive sibling: the write this page makes is declared.
    expect(paths).toContain("/api/v1/credentials/{family}/{name}");
  });
});
