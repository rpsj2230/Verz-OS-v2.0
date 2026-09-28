/**
 * The Channels screen and a person's own channels card: what each draws, and every write they send.
 *
 * Mounted directly on a memory router, for the reason `tests/audit-page.test.tsx` gives. The failures
 * worth testing look like the screen working: a secret drawn back, a switch sent without being
 * confirmed, an unbinding that names the wrong person, a set-up sent blank, and a code minted and
 * then kept on the page after the person disconnected.
 *
 * Task ids: M10.3.1, M10.3.4, M10.1.2, M10.1.3, M10.1.4
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  DISCONNECT_LABEL,
  GET_CODE_LABEL,
  READING_MY_CHANNELS,
} from "../src/components/MyChannels";
import {
  KEEP_LABEL,
  READING_CHANNELS,
  SAVE_LABEL,
  SWITCH_OFF_CONSEQUENCE,
  UNBIND_CONSEQUENCE,
} from "../src/pages/Channels";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { PAGES } from "./support/pageCases";

const CONSOLE_ORIGIN = "https://console.test";
const SECRET_TYPED = "channel-secret-typed-in-0123456789";
const CODE = "Qm9vZ2llV29vZ2llMTIzNA";

beforeAll(async () => {
  await import("../src/pages/Channels");
  await import("../src/components/MyChannels");
}, 60_000);

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

/** The page case's answers for reads, and a fixed answer for every write. */
function answering(answers: Readonly<Record<string, unknown>>, written: unknown) {
  return (url: string, init: RequestInit | undefined): Response | null => {
    const path = new URL(url, CONSOLE_ORIGIN).pathname;
    if (init?.method !== undefined && init.method !== "GET") {
      return json(written);
    }
    return path in answers ? json(answers[path]) : null;
  };
}

async function mount(
  element: "channels" | "mine",
  written: unknown,
): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const answers = element === "channels" ? PAGES["/channels"]?.answers : PAGES["/me"]?.answers;
  const idp = fakeIdentityProvider({ api: answering(answers ?? {}, written) });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { Channels } = await import("../src/pages/Channels");
  const { MyChannels } = await import("../src/components/MyChannels");
  const router = createMemoryRouter(
    [{ path: "/x", element: element === "channels" ? <Channels /> : <MyChannels /> }],
    { initialEntries: ["/x"] },
  );
  const { container } = render(<RouterProvider router={router} />);
  const reading = element === "channels" ? READING_CHANNELS : READING_MY_CHANNELS;
  await waitFor(() => {
    if (container.textContent?.includes(reading) || container.textContent?.includes("Reading")) {
      throw new Error("still reading");
    }
  });
  return { container, idp };
}

function sent(idp: FakeIdp, method: string, path: string): unknown[] {
  return idp.calls
    .filter((call) => call.init?.method === method && new URL(call.url, CONSOLE_ORIGIN).pathname === path)
    .map((call) => JSON.parse(String(call.init?.body ?? "null")) as unknown);
}

function button(container: HTMLElement, name: string): HTMLButtonElement {
  const found = [...container.querySelectorAll("button")].find(
    (one) => one.textContent === name || one.getAttribute("aria-label")?.startsWith(name),
  );
  if (found === undefined) {
    throw new Error(`no button named ${name}`);
  }
  return found as HTMLButtonElement;
}

describe("the Channels screen", () => {
  test("a card draws the identifiers, that a secret is held and never a secret, what it may carry and its health", async () => {
    // What breaks if this is deleted: the screen the install check reads could drop the health, the
    // declared ceiling or the secret's state, or draw a value where only its state belongs.
    const { container } = await mount("channels", {});
    const text = container.textContent ?? "";
    expect(text).toContain("reply_url");
    expect(text).toContain("Held in the vault. It is never shown.");
    expect(text).toContain("Failing");
    expect(text).toContain("Carries at most internal information.");
    expect(text).toContain("outbound, refused: vendor refused (403)");
    expect(text).toContain("/api/v1/channels/webhook/events");
    expect(text).toContain("This release cannot receive or reply on this channel yet");
  });

  test("switching a channel off is confirmed, says what it does, and sends only the new state", async () => {
    // What breaks if this is deleted: one press switches a channel off, or the confirmation's
    // second button is the one that does it.
    const { container, idp } = await mount("channels", {});
    fireEvent.click(button(container, "Switch off"));
    expect(container.textContent).toContain(SWITCH_OFF_CONSEQUENCE);
    expect(sent(idp, "POST", "/api/v1/channels/webhook/switch")).toEqual([]);
    fireEvent.click(button(container, KEEP_LABEL));
    expect(sent(idp, "POST", "/api/v1/channels/webhook/switch")).toEqual([]);
    fireEvent.click(button(container, "Switch off"));
    const confirm = [...container.querySelectorAll("section.confirm button")].at(-1) as HTMLButtonElement;
    fireEvent.click(confirm);
    await waitFor(() => {
      expect(sent(idp, "POST", "/api/v1/channels/webhook/switch")).toEqual([{ enabled: false }]);
    });
  });

  test("unbinding a person is confirmed and sends that person and nobody else", async () => {
    // What breaks if this is deleted: an unbinding sent without a confirmation, or for the wrong row.
    const { container, idp } = await mount("channels", { principal_id: "x", told: "Unbound." });
    const rows = PAGES["/channels"]?.answers["/api/v1/channels/webhook/bindings"] as {
      items: { principal_id: string; display_name: string }[];
    };
    const person = rows.items[0];
    fireEvent.click(button(container, "Unbind:"));
    expect(container.textContent).toContain(UNBIND_CONSEQUENCE);
    const confirm = [...container.querySelectorAll("section.confirm button")].at(-1) as HTMLButtonElement;
    fireEvent.click(confirm);
    await waitFor(() => {
      expect(sent(idp, "POST", "/api/v1/channels/webhook/bindings/unbind")).toEqual([
        { principal_id: person?.principal_id },
      ]);
    });
  });

  test("a set-up is refused blank, and filled it is confirmed and sends the secret once and keeps nothing", async () => {
    // What breaks if this is deleted: a blank identifier saved over a working one, or a secret kept
    // in the field or the page after it was sent.
    const { container, idp } = await mount("channels", PAGES["/channels"]?.answers["/api/v1/channels"]);
    const form = [...container.querySelectorAll("form")].find((one) =>
      one.getAttribute("aria-label")?.startsWith("Set up"),
    ) as HTMLFormElement;
    const reply = form.querySelector('input[name="reply_url"]') as HTMLInputElement;
    fireEvent.change(reply, { target: { value: "" } });
    fireEvent.submit(form);
    expect(container.textContent).toContain("Fill in reply_url");
    expect(sent(idp, "PUT", "/api/v1/channels/webhook")).toEqual([]);

    fireEvent.change(reply, { target: { value: "https://replies.example.test/brain" } });
    const secret = [...form.querySelectorAll("input")].find(
      (one) => one.getAttribute("type") === "text" && one.getAttribute("name") === null,
    ) as HTMLInputElement;
    fireEvent.input(secret, { target: { value: SECRET_TYPED } });
    fireEvent.submit(form);
    expect(sent(idp, "PUT", "/api/v1/channels/webhook")).toEqual([]);
    const confirm = [...container.querySelectorAll("section.confirm button")].at(-1) as HTMLButtonElement;
    expect(confirm.textContent).toBe(SAVE_LABEL);
    fireEvent.click(confirm);
    await waitFor(() => {
      expect(sent(idp, "PUT", "/api/v1/channels/webhook")).toEqual([
        { enabled: true, tenant: { reply_url: "https://replies.example.test/brain" }, secret: SECRET_TYPED },
      ]);
    });
    expect(secret.value).toBe("");
    expect(container.innerHTML).not.toContain(SECRET_TYPED);
  });
});

describe("a person's own channels card", () => {
  test("a code is asked for, shown once with how long it lasts, and disconnecting is confirmed", async () => {
    // What breaks if this is deleted: the one flow a person uses to connect a chat has no test at
    // the screen, or disconnecting goes out on one press.
    const { container, idp } = await mount("mine", {
      channel: "webhook",
      code: CODE,
      expires_at: "2019-03-04T09:10:00Z",
      told: "Send this code, on its own, to the Brain on webhook within 10 minutes.",
    });
    fireEvent.click(button(container, `${GET_CODE_LABEL}: webhook`));
    await waitFor(() => {
      expect(container.textContent).toContain(CODE);
    });
    expect(sent(idp, "POST", "/api/v1/me/channels/webhook/code")).toEqual([null]);
    fireEvent.click(button(container, `${DISCONNECT_LABEL}: lark`));
    expect(sent(idp, "POST", "/api/v1/me/channels/lark/unbind")).toEqual([]);
    const confirm = [...container.querySelectorAll("section.confirm button")].at(-1) as HTMLButtonElement;
    fireEvent.click(confirm);
    await waitFor(() => {
      expect(sent(idp, "POST", "/api/v1/me/channels/lark/unbind")).toEqual([null]);
    });
    await waitFor(() => {
      expect(container.textContent).not.toContain(CODE);
    });
  });
});
