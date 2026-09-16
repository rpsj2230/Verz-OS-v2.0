/**
 * The Notifications screen: who is told what, the switch, the relay, its password and a test message.
 *
 * Mounted directly on a memory router at its own address, for the reason
 * `tests/sessions-page.test.tsx` gives. The failures worth testing look like the screen working: a
 * switch pressed with no second step, a notice with no switch drawn with one, a confirmation that
 * paraphrases the API, a password left in the page after it was sent, a blank field sent anyway, and
 * a body key the route forbids.
 *
 * Task ids: M27.8.11
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  KEEP_LABEL,
  KEEP_PASSWORD_LABEL,
  NO_SWITCH,
  READING_NOTIFICATIONS,
  SAVE_RELAY_LABEL,
  SEND_TRIAL_LABEL,
  SWITCH_OFF_LABEL,
} from "../src/pages/Notifications";
import { BLANK_SENTENCES, type NotificationsBody } from "../src/pages/notificationsQuery";
import { readRepoFile } from "./support/repo";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { declaredRequestBodySchema } from "./support/openapi";

const LISTING = "/api/v1/notifications";
const RELAY = "/api/v1/notifications/relay";
const PASSWORD = "/api/v1/notifications/relay/password";
const TRIAL = "/api/v1/notifications/relay/test";
const CONSOLE_ORIGIN = "https://console.test";
const SECRET = "relay-PASSWORD-SENTINEL-0123456789";

const SWITCHING_OFF = "Nobody is sent this notice from now on.";
const SAVING = "Mail is sent through this relay from now on.";
const KEEPING = "The relay's password is replaced in the vault.";
const SENDING = "One test message is sent to this address through the saved relay.";

beforeAll(async () => {
  await import("../src/pages/Notifications");
}, 60_000);

function page(overrides: Partial<NotificationsBody> = {}): NotificationsBody {
  return {
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
        changed_by: null,
        changed_at: null,
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
      changed_by: "u_admin",
      changed_at: "2019-03-04T09:00:00Z",
      password: { held: null, written_at: null, vault: "unreachable", vault_told: "The secrets vault did not answer." },
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
    sending_trial: SENDING,
    plain_smtp_refused: "SMTP without TLS is refused.",
    ...overrides,
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

type Answer = (url: URL, init: RequestInit | undefined) => Response | null;

async function mount(answer: Answer): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      return answer(new URL(url, CONSOLE_ORIGIN), init);
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { Notifications } = await import("../src/pages/Notifications");
  const router = createMemoryRouter([{ path: "/notifications", element: <Notifications /> }], {
    initialEntries: ["/notifications"],
  });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (container.textContent?.includes(READING_NOTIFICATIONS)) {
      throw new Error("still reading");
    }
  });
  return { container, idp };
}

function posts(idp: FakeIdp): { url: URL; body: unknown }[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST" && new URL(call.url, CONSOLE_ORIGIN).pathname.startsWith("/api/"))
    .map((call) => ({
      url: new URL(call.url, CONSOLE_ORIGIN),
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

function field(container: HTMLElement, label: string): HTMLInputElement {
  const found = [...container.querySelectorAll("label")].find((one) => one.textContent?.trim() === label);
  const input = found?.querySelector("input");
  if (!input) {
    throw new Error(`no field labelled ${label}`);
  }
  return input;
}

function confirmButton(container: HTMLElement, label: string): HTMLButtonElement {
  return button(container.querySelector(".confirm") as HTMLElement, label);
}

describe("what the notifications screen shows", () => {
  test("each notice says who is told what, whether it is sent, and a notice with no switch says why", async () => {
    // What breaks if this is deleted: every refusal below is satisfied by a page showing nothing, and
    // a notice with no switch can be drawn with a button.
    const { container } = await mount((url) => (url.pathname === LISTING ? json(page()) : null));
    const rows = [...(container.querySelector('[aria-label="Notices"]')?.querySelectorAll("tbody tr") ?? [])];
    expect(rows).toHaveLength(2);
    expect(rows[0]?.textContent).toContain("The owner of a knowledge item.");
    expect(rows[0]?.textContent).toContain("Sent");
    expect(rows[0]?.querySelector("button")?.textContent).toBe(SWITCH_OFF_LABEL);
    expect(rows[1]?.textContent).toContain("Not sent yet");
    expect(rows[1]?.textContent).toContain(`${NO_SWITCH}: A switch here would be`);
    expect(rows[1]?.querySelector("button")).toBeNull();
    const relay = container.querySelector('[aria-label="The saved relay"]')?.textContent ?? "";
    expect(relay).toContain("smtp.example.test");
    expect(relay).toContain("console@example.test");
    expect(container.textContent).toContain("Not known");
    expect(container.textContent).toContain("The secrets vault did not answer.");
  });
});

describe("what the notifications screen does", () => {
  test("switching a notice off is confirmed in the API's words and sends only the switch", async () => {
    // What breaks if this is deleted: a notice silenced with one press, or a body the route refuses.
    const { container, idp } = await mount((url) => {
      if (url.pathname === "/api/v1/notifications/notices/reverification_request") {
        return json({ ...page().notices[0], on: false, changed_by: "u_admin", changed_at: "2019-03-04T10:00:00Z" });
      }
      return url.pathname === LISTING ? json(page()) : null;
    });
    const declared = declaredRequestBodySchema("/api/v1/notifications/notices/{kind}", "post");

    fireEvent.click(button(container, SWITCH_OFF_LABEL));
    expect((container.querySelector(".confirm") as HTMLElement).textContent).toContain(SWITCHING_OFF);
    fireEvent.click(confirmButton(container, KEEP_LABEL));
    expect(posts(idp)).toEqual([]);

    fireEvent.click(button(container, SWITCH_OFF_LABEL));
    fireEvent.click(confirmButton(container, SWITCH_OFF_LABEL));
    await waitFor(() => {
      expect(posts(idp)).toHaveLength(1);
    });
    const [sent] = posts(idp);
    expect(sent?.url.pathname).toBe("/api/v1/notifications/notices/reverification_request");
    expect(Object.keys(sent?.body as object)).toEqual(Object.keys(declared["properties"] as object));
    expect(sent?.body).toEqual({ on: false });
  });

  test("saving the relay is confirmed and sends exactly the route's five fields", async () => {
    // What breaks if this is deleted: a relay saved with no second step, or a port sent as text.
    const { container, idp } = await mount((url) => {
      if (url.pathname === RELAY) {
        return json(page().email);
      }
      return url.pathname === LISTING ? json(page()) : null;
    });
    const declared = declaredRequestBodySchema(RELAY, "post");

    fireEvent.change(field(container, "Host"), { target: { value: "smtp.other.test" } });
    fireEvent.change(field(container, "Port"), { target: { value: "465" } });
    fireEvent.click(button(container, SAVE_RELAY_LABEL));
    expect((container.querySelector(".confirm") as HTMLElement).textContent).toContain(SAVING);
    expect(posts(idp)).toEqual([]);
    fireEvent.click(confirmButton(container, SAVE_RELAY_LABEL));
    await waitFor(() => {
      expect(posts(idp)).toHaveLength(1);
    });
    const [sent] = posts(idp);
    expect(Object.keys(sent?.body as object).sort()).toEqual(Object.keys(declared["properties"] as object).sort());
    expect(sent?.body).toEqual({
      host: "smtp.other.test",
      port: 465,
      security: "starttls",
      sender: "console@example.test",
      username: "relay_user",
    });
  });

  test("a blank relay, password or recipient says what to fill in beside each field, and asks and sends nothing", async () => {
    // What breaks if this is deleted: a confirmation a person can agree to for a relay with no host,
    // and a refusal only after they have.
    const { container, idp } = await mount((url) => (url.pathname === LISTING ? json(page()) : null));

    fireEvent.change(field(container, "Host"), { target: { value: "" } });
    fireEvent.change(field(container, "Port"), { target: { value: "not a port" } });
    fireEvent.change(field(container, "Sender address"), { target: { value: "" } });
    fireEvent.click(button(container, SAVE_RELAY_LABEL));
    expect(container.querySelector(".confirm")).toBeNull();
    expect(container.querySelector('[aria-label="Problems with host"]')?.textContent).toBe(BLANK_SENTENCES.host);
    expect(container.querySelector('[aria-label="Problems with port"]')?.textContent).toBe(BLANK_SENTENCES.port);
    expect(container.querySelector('[aria-label="Problems with sender"]')?.textContent).toBe(BLANK_SENTENCES.sender);

    fireEvent.click(button(container, KEEP_PASSWORD_LABEL));
    expect(container.querySelector('[aria-label="Problems with password"]')?.textContent).toBe(BLANK_SENTENCES.password);
    fireEvent.click(button(container, SEND_TRIAL_LABEL));
    expect(container.querySelector('[aria-label="Problems with to"]')?.textContent).toBe(BLANK_SENTENCES.to);
    expect(container.querySelector(".confirm")).toBeNull();
    expect(posts(idp)).toEqual([]);
  });

  test("the sentences for a blank field are the API's own", () => {
    // What breaks if this is deleted: the console's copy drifting from the route's words.
    const python = readRepoFile("src/brain/ops/mail.py").replace(/"\s+"/g, "");
    for (const [name, sentence] of Object.entries(BLANK_SENTENCES)) {
      expect(python, name).toContain(`"${sentence}`);
    }
  });

  test("a password is confirmed, sent, cleared from the page, and a refusal is shown beside the field", async () => {
    // What breaks if this is deleted: the relay's password left in the field for the next person at
    // the screen, or a 422 read as a generic failure.
    const { container, idp } = await mount((url) => {
      if (url.pathname === PASSWORD) {
        return json({ problems: [{ field: "password", code: "not_one_piece", message: "The password has a space inside it." }] }, 422);
      }
      return url.pathname === LISTING ? json(page()) : null;
    });
    fireEvent.change(field(container, "Password"), { target: { value: SECRET } });
    fireEvent.click(button(container, KEEP_PASSWORD_LABEL));
    expect((container.querySelector(".confirm") as HTMLElement).textContent).toContain(KEEPING);
    expect(container.querySelector(".confirm")?.textContent).not.toContain(SECRET);
    fireEvent.click(confirmButton(container, KEEP_PASSWORD_LABEL));
    await waitFor(() => {
      expect(container.querySelector('[aria-label="Problems with password"]')?.textContent).toContain("space inside it");
    });
    expect(posts(idp).map((one) => one.body)).toEqual([{ password: SECRET }]);
    expect(field(container, "Password").value).toBe("");
    expect(container.innerHTML).not.toContain(SECRET);
  });

  test("a test message is confirmed and what the relay did is said in the API's words", async () => {
    // What breaks if this is deleted: a message sent with one press, or its outcome not shown.
    const { container, idp } = await mount((url) => {
      if (url.pathname === TRIAL) {
        return json({ outcome: "sent", told: "The relay accepted the test message." });
      }
      return url.pathname === LISTING ? json(page()) : null;
    });
    fireEvent.change(field(container, "Send it to"), { target: { value: "someone@example.test" } });
    fireEvent.click(button(container, SEND_TRIAL_LABEL));
    expect((container.querySelector(".confirm") as HTMLElement).textContent).toContain(SENDING);
    fireEvent.click(confirmButton(container, SEND_TRIAL_LABEL));
    await waitFor(() => {
      expect(container.textContent).toContain("The relay accepted the test message.");
    });
    expect(posts(idp).map((one) => one.body)).toEqual([{ to: "someone@example.test" }]);
  });
});
