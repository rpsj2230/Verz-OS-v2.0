/**
 * Notifications and email, and Subscribers, on the page kit: what each draws, and every write the
 * Notifications page sends, each from a confirmation in the API's words.
 *
 * Reached through the application's own route table. The failures worth testing look like the page
 * working: a principal id drawn where a name belongs, a notice with no switch drawn as switchable, a
 * write sent without its confirmation, a relay field that says what it wanted only after a refusal,
 * the relay's password left in the page, a removal offered with nothing saved, and a subscriber row
 * carrying who set it up by id.
 *
 * Task ids: M27.8.11, M27.8.5, M27.7.12, M23.2.2, M27.16.1
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { ALWAYS_ON } from "../src/pages/notifications/NotificationsPage";
import {
  EDIT_RELAY_LABEL,
  PASSWORD_LABEL,
  REMOVE_LABEL,
  SAVE_PASSWORD_LABEL,
  SAVE_RELAY_LABEL,
  SET_PASSWORD_LABEL,
  SWITCH_OFF_LABEL,
  TRIAL_LABEL,
} from "../src/pages/notifications/RelayActs";
import { BLANK_SENTENCES, RELAY_FORMATS, type NotificationsBody } from "../src/pages/notificationsQuery";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { declaredRequestBodySchema } from "./support/openapi";
import { installRadixStubs } from "./support/radix";
import { readRepoFile } from "./support/repo";

const CONSOLE_ORIGIN = "https://console.test";
const SECRET = "relay-PASSWORD-SENTINEL-0123456789";
const SWITCHING_OFF = "Nobody is sent this notice from now on.";
const SAVING = "Mail is sent through this relay from now on.";
const KEEPING = "The relay's password is kept in the vault.";
const REMOVING = "No mail is sent from now on, and a test message is refused until a relay is saved again.";

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/Notifications");
  await import("../src/pages/Subscribers");
}, 60_000);

function page(overrides: Partial<NotificationsBody> = {}): NotificationsBody {
  return {
    alerts: [{ subject: "u_colleague", said: "Keeps asking for what they may not read.", raised_at: "2019-03-04T09:00:00Z" }],
    alerts_unread: "",
    notices: [
      {
        kind: "reverification_request",
        title: "Knowledge due to be checked again",
        told: "The owner of a knowledge item.",
        about: "That the item needs checking.",
        how: "Recorded as an approval request.",
        sent: true,
        switchable: true,
        fixed_because: "",
        on: true,
        changed_by: "u_ada",
        changed_at: "2019-03-04T09:00:00Z",
      },
      {
        kind: "emergency_access",
        title: "Somebody took emergency access",
        told: "Every standing super administrator.",
        about: "Who took it.",
        how: "Nothing sends it.",
        sent: false,
        switchable: false,
        fixed_because: "A switch here would be a way to take the access and not be seen.",
        on: true,
        changed_by: null,
        changed_at: null,
      },
    ],
    email: {
      configured: true,
      host: "smtp.example.test",
      port: 587,
      security: "starttls",
      sender: "console@example.test",
      username: "relay_user",
      changed_by: "u_ada",
      changed_at: "2019-03-04T09:00:00Z",
      password: { held: true, written_at: "2019-03-04T09:00:00Z", vault: "ready", vault_told: "The vault answered." },
      branded_sender: "console@example.test",
    },
    securities: ["starttls", "tls"],
    email_used_for: "Email is used by the test message on this screen today.",
    subscribers: "Systems outside the company are listed on the Webhooks screen.",
    ships_on: "No row means on.",
    only_the_last_change_is_kept: "A switch keeps its last change.",
    switching_off: SWITCHING_OFF,
    switching_on: "This notice is sent again from the next one.",
    saving_email: SAVING,
    keeping_password: KEEPING,
    sending_trial: "One test message is sent to this address through the saved relay.",
    removing_email: REMOVING,
    plain_smtp_refused: "SMTP without TLS is refused.",
    people: { u_ada: "Ada Admin", u_colleague: "Col League" },
    ...overrides,
  };
}

const SUBSCRIBERS = {
  items: [
    {
      subscriber_id: "billing_bridge",
      endpoint: "https://hooks.example.test/brain",
      kinds: ["approval.requested"],
      active: false,
      created_by: "u_ada",
      last_delivered_at: null,
    },
  ],
  findings: ["billing_bridge is told about nothing it can act on."],
  kinds: ["approval.requested"],
  staleness: null,
  stopping: "A subscriber is switched off on the Webhooks screen.",
  scope: "Only webhook subscribers are listed.",
  told: "",
};

interface Sent {
  readonly method: string;
  readonly path: string;
  readonly body: unknown;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

async function consoleAt(path: string, read: Record<string, unknown>): Promise<{ container: HTMLElement; sent: Sent[] }> {
  const sent: Sent[] = [];
  const idp = fakeIdentityProvider({
    api(url, init) {
      const where = new URL(url, CONSOLE_ORIGIN).pathname;
      const method = (init?.method ?? "GET").toUpperCase();
      sent.push({ method, path: where, body: typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : null });
      if (method !== "GET") {
        return json({ told: "Done." });
      }
      return where in read ? json(read[where]) : null;
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
  return { container, sent };
}

function button(root: ParentNode, name: string): HTMLButtonElement {
  const found = [...root.querySelectorAll("button")].find(
    (one) => one.textContent?.trim() === name || one.getAttribute("aria-label")?.startsWith(name),
  );
  if (found === undefined) {
    throw new Error(`No button reading ${name}.`);
  }
  return found;
}

function dialog(): HTMLElement {
  const found = document.body.querySelector<HTMLElement>('[data-slot="confirm-dialog"]');
  if (found === null) {
    throw new Error("No confirmation is open.");
  }
  return found;
}

function posts(sent: Sent[]): [string, unknown][] {
  return sent.filter((one) => one.method === "POST").map((one) => [one.path, one.body]);
}

async function drawerForm(label: string): Promise<HTMLFormElement> {
  return waitFor(() => {
    const found = document.body.querySelector<HTMLFormElement>(`form[aria-label="${label}"]`);
    expect(found).not.toBeNull();
    return found as HTMLFormElement;
  });
}

function outsideAdvanced(container: HTMLElement): string {
  const copy = container.cloneNode(true) as HTMLElement;
  copy.querySelectorAll('[data-slot="advanced"]').forEach((one) => {
    one.remove();
  });
  return copy.textContent ?? "";
}

describe("the Notifications page", () => {
  test("each notice says who is told and whether it is sent, a fixed one says always on, and people are names", async () => {
    // What breaks if this is deleted: a notice with no switch drawn with one, or a principal id
    // drawn beside a switch or an alert where a name belongs.
    const { container } = await consoleAt("/notifications", { "/api/v1/notifications": page() });
    const text = outsideAdvanced(container);
    expect(text).toContain("Knowledge due to be checked again");
    expect(text).toContain("The owner of a knowledge item.");
    expect(text).toContain(ALWAYS_ON);
    expect(text).toContain("Ada Admin");
    expect(text).toContain("Col League");
    expect(text).not.toContain("u_ada");
    expect(text).not.toContain("u_colleague");
    expect(button(container, `${SWITCH_OFF_LABEL}: Knowledge due`)).toBeDefined();
    const switches = [...container.querySelectorAll("button")].map((one) => one.getAttribute("aria-label") ?? "");
    expect(switches.filter((one) => /^Switch (on|off): Somebody took emergency/.test(one))).toEqual([]);
    expect(container.querySelector('[data-slot="advanced"]')?.textContent).toContain("u_ada");
  });

  test("switching a notice off is confirmed in the API's words and sends only the switch", async () => {
    // What breaks if this is deleted: a notice silenced on one press, or with a body the route refuses.
    const { container, sent } = await consoleAt("/notifications", { "/api/v1/notifications": page() });
    fireEvent.click(button(container, `${SWITCH_OFF_LABEL}: Knowledge due`));
    expect(dialog().textContent).toContain(SWITCHING_OFF);
    expect(posts(sent)).toEqual([]);
    fireEvent.click(button(dialog(), SWITCH_OFF_LABEL));
    await waitFor(() => {
      expect(posts(sent)).toEqual([["/api/v1/notifications/notices/reverification_request", { on: false }]]);
    });
  });

  test("the relay form says what each field accepts, a blank one is said beside it, and a save sends the route's five fields", async () => {
    // What breaks if this is deleted: a blank relay one press from a confirmation, a field saying
    // what it wanted only after a refusal, or a key the route does not declare.
    const { container, sent } = await consoleAt("/notifications", { "/api/v1/notifications": page() });
    fireEvent.click(button(container, EDIT_RELAY_LABEL));
    const form = await drawerForm("Save the relay");
    expect(form.textContent).toContain(RELAY_FORMATS.host);
    expect(form.textContent).toContain(RELAY_FORMATS.port);
    fireEvent.change(form.querySelector('input[name="host"]') as HTMLInputElement, { target: { value: "" } });
    fireEvent.submit(form);
    expect(form.querySelector('[aria-label="Problems with host"]')?.textContent).toBe(BLANK_SENTENCES.host);
    expect(document.body.querySelector('[data-slot="confirm-dialog"]')).toBeNull();
    fireEvent.change(form.querySelector('input[name="host"]') as HTMLInputElement, { target: { value: "smtp.example.org" } });
    fireEvent.submit(form);
    expect(dialog().textContent).toContain(SAVING);
    fireEvent.click(button(dialog(), SAVE_RELAY_LABEL));
    await waitFor(() => {
      expect(posts(sent)).toEqual([
        [
          "/api/v1/notifications/relay",
          { host: "smtp.example.org", port: 587, security: "starttls", sender: "console@example.test", username: "relay_user" },
        ],
      ]);
    });
    const declared = Object.keys((declaredRequestBodySchema("/api/v1/notifications/relay", "post")["properties"] ?? {}) as Record<string, unknown>);
    expect(Object.keys(posts(sent)[0]?.[1] as Record<string, unknown>).sort()).toEqual(declared.sort());
  });

  test("a password is refused blank beside its field, confirmed when typed, sent once and gone from the page", async () => {
    // What breaks if this is deleted: the password kept in the page after it was sent, or sent blank.
    const { container, sent } = await consoleAt("/notifications", { "/api/v1/notifications": page() });
    fireEvent.click(button(container, PASSWORD_LABEL));
    const form = await drawerForm("Save the relay's password");
    fireEvent.submit(form);
    expect(form.querySelector('[aria-label="Problems with password"]')?.textContent).toBe(BLANK_SENTENCES.password);
    fireEvent.input(form.querySelector('[data-slot="secret-field"] input') as HTMLInputElement, { target: { value: SECRET } });
    fireEvent.submit(form);
    expect(dialog().textContent).toContain(KEEPING);
    fireEvent.click(button(dialog(), SAVE_PASSWORD_LABEL));
    await waitFor(() => {
      expect(posts(sent)).toEqual([["/api/v1/notifications/relay/password", { password: SECRET }]]);
    });
    expect(document.body.innerHTML).not.toContain(SECRET);
  });

  test("with no password held the act is to set one, not to replace one", async () => {
    // Found on the owner's install on 2026-09-29: "Replace password" beside "No relay is saved".
    // What breaks if this is deleted: the page offers to replace a password that does not exist.
    const unsaved = page({
      email: {
        ...page().email,
        configured: false,
        host: null,
        port: null,
        sender: null,
        username: null,
        changed_by: null,
        changed_at: null,
        password: { held: false, written_at: null, vault: "ready", vault_told: "The vault answered." },
      },
    });
    const { container } = await consoleAt("/notifications", { "/api/v1/notifications": unsaved });
    expect(() => button(container, PASSWORD_LABEL)).toThrow();
    fireEvent.click(button(container, SET_PASSWORD_LABEL));
    const form = await drawerForm("Save the relay's password");
    expect(form.closest('[role="dialog"]')?.textContent).toContain(SET_PASSWORD_LABEL);
  });

  test("a test message says what it accepts, and blank it says what to fill in and sends nothing", async () => {
    // What breaks if this is deleted: a test message sent to nobody, or a blank one confirmed.
    const { container, sent } = await consoleAt("/notifications", { "/api/v1/notifications": page() });
    fireEvent.click(button(container, TRIAL_LABEL));
    const form = await drawerForm("Send a test message");
    expect(form.textContent).toContain(RELAY_FORMATS.to);
    fireEvent.submit(form);
    expect(form.querySelector('[aria-label="Problems with to"]')?.textContent).toBe(BLANK_SENTENCES.to);
    expect(document.body.querySelector('[data-slot="confirm-dialog"]')).toBeNull();
    expect(posts(sent)).toEqual([]);
  });

  test("removing the relay is confirmed in the API's words and offered only while a relay is saved", async () => {
    // What breaks if this is deleted: the relay removed on one press, or a removal offered for a
    // relay nobody saved, which the API refuses.
    const { container, sent } = await consoleAt("/notifications", { "/api/v1/notifications": page() });
    fireEvent.click(button(container, REMOVE_LABEL));
    expect(dialog().textContent).toContain(REMOVING);
    expect(posts(sent)).toEqual([]);
    fireEvent.click(button(dialog(), REMOVE_LABEL));
    await waitFor(() => {
      expect(posts(sent)).toEqual([["/api/v1/notifications/relay/removal", null]]);
    });

    const unsaved = page({
      email: { ...page().email, configured: false, host: null, port: null, security: null, sender: null, username: null, changed_by: null, changed_at: null },
    });
    const again = await consoleAt("/notifications", { "/api/v1/notifications": unsaved });
    const labels = [...again.container.querySelectorAll("button")].map((one) => one.textContent?.trim());
    expect(labels).not.toContain(REMOVE_LABEL);
    expect(labels).not.toContain(TRIAL_LABEL);
  });

  test("the sentences for a blank field are the API's own", () => {
    // What breaks if this is deleted: the console's copy drifting from the route's words.
    const python = readRepoFile("src/brain/ops/mail.py").replace(/"\s+"/g, "");
    for (const [name, sentence] of Object.entries(BLANK_SENTENCES)) {
      expect(python, name).toContain(`"${sentence}`);
    }
  });
});

describe("the Subscribers page", () => {
  test("each subscriber links to its page under Webhooks, and nobody is shown by id", async () => {
    // What breaks if this is deleted: the list draws who set a subscriber up by principal id, or a
    // subscriber has nowhere to be changed from.
    const { container } = await consoleAt("/subscribers", { "/api/v1/govern/subscribers": SUBSCRIBERS });
    const link = container.querySelector<HTMLAnchorElement>('tbody a[href="/webhooks/billing_bridge"]');
    expect(link?.textContent).toBe("billing_bridge");
    expect(container.textContent).toContain("Off");
    expect(container.textContent).toContain("billing_bridge is told about nothing it can act on.");
    expect(container.textContent).toContain("A subscriber is switched off on the Webhooks screen.");
    expect(container.textContent).not.toContain("u_ada");
  });

  test("no subscribers is its own sentence, the same for a reader who may not manage them", async () => {
    // What breaks if this is deleted: an empty answer drawn as an empty table, or worded to tell a
    // reader without the grant apart from an install with no subscribers.
    const { container } = await consoleAt("/subscribers", { "/api/v1/govern/subscribers": { ...SUBSCRIBERS, items: [], findings: [] } });
    expect(container.textContent).toContain("No subscribers to show");
    expect(container.querySelector("tbody")).toBeNull();
  });
});
