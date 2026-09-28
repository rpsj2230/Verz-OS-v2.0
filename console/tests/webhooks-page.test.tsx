/**
 * The Webhooks module on the page kit: the list, one subscriber's three views, the three writes and
 * their confirmations, and the two acts drawn as not built yet.
 *
 * Reached through the application's own route table. The failures worth testing look like the page
 * working: a control for a reader the API said may not manage, a write sent without its
 * confirmation, a confirmation that paraphrases the API, a signing secret left in the page after it
 * was sent, a blank field said only after a refusal, and a principal id drawn where a name belongs.
 *
 * **What each write sends is read against the route's own request body**, so a key this console
 * invented is a failure here rather than a 422 in front of an administrator.
 *
 * Task ids: M27.8.12, M27.8.5, M27.15.44, M27.16.1
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { ACT_LABELS, UNAVAILABLE } from "../src/pages/webhooks/webhookActions";
import { NOT_MANAGEABLE } from "../src/pages/webhooks/WebhooksPage";
import { BLANK_SENTENCES, REGISTRATION_FORMATS, type SubscriberRow, type WebhooksBody } from "../src/pages/webhooksQuery";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { apiDocument, declaredRequestBodySchema } from "./support/openapi";
import { installRadixStubs } from "./support/radix";
import { readRepoFile } from "./support/repo";

const CONSOLE_ORIGIN = "https://console.test";
const SECRET = "whsec-SIGNING-SENTINEL-0123456789abcdefABCDEF";
const REGISTERING = "The subscriber is told, at this address, whenever one of the chosen kinds happens.";
const REPLACING = "The new secret signs every request from now on.";
const SWITCHING_OFF = "The subscriber is told nothing more. This cannot be undone.";

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/Webhook");
}, 60_000);

function subscriber(overrides: Partial<SubscriberRow> = {}): SubscriberRow {
  return {
    subscriber_id: "billing_bridge",
    endpoint: "https://hooks.example.test/brain",
    kinds: ["approval.requested"],
    active: true,
    created_by: "u_ada",
    created_at: "2019-03-04T09:00:00Z",
    deactivated_at: null,
    last_delivered_at: null,
    secret_held: true,
    secret_written_at: "2019-03-04T09:00:05Z",
    deliveries: [
      {
        kind: "approval.requested",
        state: "exhausted",
        attempts: 5,
        occurred_at: "2019-03-04T09:10:00Z",
        last_attempt_at: "2019-03-04T09:40:00Z",
        reason: "not sent: refused",
        next_attempt_at: null,
      },
    ],
    changes: [{ change: "registered", changed_by: "u_ada", changed_at: "2019-03-04T09:00:00Z", secret_written_at: null }],
    ...overrides,
  };
}

function page(overrides: Partial<WebhooksBody> = {}): WebhooksBody {
  return {
    manageable: true,
    vault: "ready",
    vault_told: "The secrets vault answered.",
    subscribers: [subscriber()],
    findings: ["billing_bridge is told about nothing it can act on."],
    kinds: ["automation.run_finished", "operation.settled", "connector.health_changed", "approval.requested"],
    delivery: "The worker sends what is due every minute.",
    dispatcher: {
      runs_here: true,
      paused: false,
      last_started_at: "2019-03-04T09:20:00Z",
      last_finished_at: "2019-03-04T09:20:01Z",
      last_outcome: "ok",
      last_report: "1 delivered",
      told: "The dispatch runs every minute, and its last run is shown here.",
    },
    inbound: { channels: [], channels_told: "", automation_path: "/api/v1/automation/tool-call", automation_told: "An automation calls in." },
    registering: REGISTERING,
    replacing: REPLACING,
    switching_off: SWITCHING_OFF,
    secret_minimum: 32,
    people: { u_ada: "Ada Admin" },
    ...overrides,
  };
}

interface Sent {
  readonly method: string;
  readonly path: string;
  readonly body: unknown;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

async function consoleAt(path: string, body: WebhooksBody): Promise<{ container: HTMLElement; sent: Sent[] }> {
  const sent: Sent[] = [];
  const idp = fakeIdentityProvider({
    api(url, init) {
      const where = new URL(url, CONSOLE_ORIGIN).pathname;
      const method = (init?.method ?? "GET").toUpperCase();
      sent.push({ method, path: where, body: typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : null });
      if (method !== "GET") {
        return json({ subscriber_id: "x", change: "registered", changed_at: "2019-03-04T09:00:00Z", secret_written_at: null, told: "Done." });
      }
      return where === "/api/v1/webhooks" ? json(body) : null;
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

describe("the Webhooks list", () => {
  test("a subscriber reads as where it is told, what about, its state and secret, and its registrar is no id", async () => {
    // What breaks if this is deleted: the list draws a principal id, or a secret held reads as not held.
    const { container } = await consoleAt("/webhooks", page());
    const text = container.querySelector("tbody")?.textContent ?? "";
    expect(text).toContain("billing_bridge");
    expect(text).toContain("https://hooks.example.test/brain");
    expect(text).toContain("approval.requested");
    expect(text).toContain("On");
    expect(text).toContain("Held");
    expect(text).toContain("Never");
    expect(container.textContent).toContain("billing_bridge is told about nothing it can act on.");
    expect(container.textContent).not.toContain("u_ada");
  });

  test("a reader who may not manage sees no list and no control, and is told what managing needs", async () => {
    // What breaks if this is deleted: a register button for a reader every write refuses.
    const { container } = await consoleAt("/webhooks", page({ manageable: false, subscribers: [] }));
    expect(container.textContent).toContain(NOT_MANAGEABLE);
    expect([...container.querySelectorAll("button")].some((one) => one.textContent?.includes(ACT_LABELS.register))).toBe(false);
  });

  test("a blank registration says what to fill in beside each field before anything is asked or sent", async () => {
    // What breaks if this is deleted: an empty registration is one press from a confirmation asking
    // to register "this subscriber", which is what the old screen did on 2026-09-17.
    const { container, sent } = await consoleAt("/webhooks", page());
    fireEvent.click(button(container, ACT_LABELS.register));
    const form = await waitFor(() => {
      const found = document.body.querySelector<HTMLFormElement>(`form[aria-label="${ACT_LABELS.register}"]`);
      expect(found).not.toBeNull();
      return found as HTMLFormElement;
    });
    expect(form.textContent).toContain(REGISTRATION_FORMATS.subscriber_id);
    expect(form.textContent).toContain(REGISTRATION_FORMATS.endpoint);
    fireEvent.submit(form);
    expect(form.querySelector('[aria-label="Problems with subscriber_id"]')?.textContent).toBe(BLANK_SENTENCES.subscriber_id);
    expect(form.querySelector('[aria-label="Problems with endpoint"]')?.textContent).toBe(BLANK_SENTENCES.endpoint);
    expect(form.querySelector('[aria-label="Problems with kinds"]')?.textContent).toBe(BLANK_SENTENCES.kinds);
    expect(form.querySelector('[aria-label="Problems with secret"]')?.textContent).toBe(BLANK_SENTENCES.secret);
    expect(document.body.querySelector('[data-slot="confirm-dialog"]')).toBeNull();
    expect(posts(sent)).toEqual([]);
  });

  test("registering is confirmed in the API's words and sends exactly the route's four fields, then forgets the secret", async () => {
    // What breaks if this is deleted: a registration sent unconfirmed, a key the route does not
    // declare, or the signing secret left in the page after it went.
    const { container, sent } = await consoleAt("/webhooks", page());
    fireEvent.click(button(container, ACT_LABELS.register));
    const form = await waitFor(() => {
      const found = document.body.querySelector<HTMLFormElement>(`form[aria-label="${ACT_LABELS.register}"]`);
      expect(found).not.toBeNull();
      return found as HTMLFormElement;
    });
    fireEvent.change(form.querySelector('input[name="subscriber_id"]') as HTMLInputElement, { target: { value: "new_bridge" } });
    fireEvent.change(form.querySelector('input[name="endpoint"]') as HTMLInputElement, { target: { value: "https://hooks.example.test/new" } });
    fireEvent.click(form.querySelector('input[name="kinds"]') as HTMLInputElement);
    fireEvent.input(form.querySelector('[data-slot="secret-field"] input') as HTMLInputElement, { target: { value: SECRET } });
    fireEvent.submit(form);
    expect(dialog().textContent).toContain(REGISTERING);
    expect(posts(sent)).toEqual([]);
    fireEvent.click(button(dialog(), ACT_LABELS.reviewRegistration));
    await waitFor(() => {
      expect(posts(sent)).toEqual([
        [
          "/api/v1/webhooks/subscribers",
          { subscriber_id: "new_bridge", endpoint: "https://hooks.example.test/new", kinds: ["automation.run_finished"], secret: SECRET },
        ],
      ]);
    });
    const declared = Object.keys((declaredRequestBodySchema("/api/v1/webhooks/subscribers", "post")["properties"] ?? {}) as Record<string, unknown>);
    expect(Object.keys(posts(sent)[0]?.[1] as Record<string, unknown>).sort()).toEqual(declared.sort());
    expect(document.body.innerHTML).not.toContain(SECRET);
  });

  test("the sentences for a blank field are the API's own", () => {
    // What breaks if this is deleted: the console's copy of the four sentences drifting from the
    // ones the route answers with. Read from the Python, with its implicitly joined literals joined.
    const python = readRepoFile("src/brain/ops/webhook_admin.py").replace(/"\s+"/g, "");
    for (const [name, sentence] of Object.entries(BLANK_SENTENCES)) {
      expect(python, name).toContain(`"${sentence}"`);
    }
  });
});

describe("one subscriber's page", () => {
  test("the Dashboard lists its deliveries, and a delivery given up offers a replay that is drawn and inert", async () => {
    // What breaks if this is deleted: an exhausted delivery reads as a working replay control, or
    // the replay is hidden so the page says the product has no such act.
    const { container, sent } = await consoleAt("/webhooks/billing_bridge", page());
    expect(container.querySelector("h1")?.textContent).toBe("billing_bridge");
    const table = container.querySelector("tbody")?.textContent ?? "";
    expect(table).toContain("Given up");
    expect(table).toContain("not sent: refused");
    const replay = container.querySelector('[data-unavailable][aria-describedby]');
    expect(replay).not.toBeNull();
    expect(container.textContent).toContain(UNAVAILABLE.replay.reason);
    fireEvent.click(replay as HTMLElement);
    expect(posts(sent)).toEqual([]);
  });

  test("replacing the secret and switching off are each confirmed in the API's words and send only themselves", async () => {
    // What breaks if this is deleted: either write goes out on one press, or with a body the route
    // does not take.
    const { container, sent } = await consoleAt("/webhooks/billing_bridge/profile", page());
    fireEvent.click(button(container.querySelector('[data-slot="detail-header"]') as HTMLElement, ACT_LABELS.replace));
    const form = await waitFor(() => {
      const found = document.body.querySelector<HTMLFormElement>(`form[aria-label="${ACT_LABELS.replace} of billing_bridge"]`);
      expect(found).not.toBeNull();
      return found as HTMLFormElement;
    });
    fireEvent.submit(form);
    expect(form.querySelector('[aria-label="Problems with secret"]')?.textContent).toBe(BLANK_SENTENCES.secret);
    fireEvent.input(form.querySelector('[data-slot="secret-field"] input') as HTMLInputElement, { target: { value: SECRET } });
    fireEvent.submit(form);
    expect(dialog().textContent).toContain(REPLACING);
    fireEvent.click(button(dialog(), ACT_LABELS.replace));
    await waitFor(() => {
      expect(posts(sent)).toEqual([["/api/v1/webhooks/subscribers/billing_bridge/secret", { secret: SECRET }]]);
    });
    await waitFor(() => {
      expect(document.body.querySelector('[data-slot="confirm-dialog"]')).toBeNull();
    });
    fireEvent.click(button(container.querySelector('[data-slot="detail-header"]') as HTMLElement, ACT_LABELS.switchOff));
    expect(dialog().textContent).toContain(SWITCHING_OFF);
    fireEvent.click(button(dialog(), ACT_LABELS.switchOff));
    await waitFor(() => {
      expect(posts(sent).at(-1)).toEqual(["/api/v1/webhooks/subscribers/billing_bridge/switch-off", null]);
    });
  });

  test("a switched-off subscriber offers no write, and switching back on is drawn and inert with its reason", async () => {
    // What breaks if this is deleted: a control on a subscriber every write refuses, or "switch back
    // on" hidden as though the product had no such act.
    const off = page({ subscribers: [subscriber({ active: false, deactivated_at: "2019-03-05T09:00:00Z" })] });
    const { container } = await consoleAt("/webhooks/billing_bridge/profile", off);
    const header = container.querySelector('[data-slot="detail-header"]') as HTMLElement;
    expect([...header.querySelectorAll("button:not([data-unavailable])")].map((one) => one.textContent)).toEqual([]);
    expect(container.textContent).toContain(UNAVAILABLE.switchOn.reason);
  });

  test("the About view names who registered and changed it, with each id under Advanced alone", async () => {
    // What breaks if this is deleted: the history draws a principal id where a person's name belongs.
    const { container } = await consoleAt("/webhooks/billing_bridge/about", page());
    const copy = container.cloneNode(true) as HTMLElement;
    copy.querySelectorAll('[data-slot="advanced"]').forEach((one) => {
      one.remove();
    });
    expect(copy.textContent).toContain("Ada Admin");
    expect(copy.textContent).not.toContain("u_ada");
    expect(container.querySelector('[data-slot="advanced"]')?.textContent).toContain("u_ada");
  });

  test("a subscriber the list does not hold reads as no subscriber here, whatever the reason", async () => {
    // What breaks if this is deleted: an address for a hidden subscriber and one for a missing one
    // read differently.
    const { container } = await consoleAt("/webhooks/somebody_else", page({ manageable: false, subscribers: [] }));
    expect(container.textContent).toContain("No subscriber here");
  });

  test("every act drawn as unavailable names no route the API document declares", () => {
    // What breaks if this is deleted: a switch-on or replay route lands and the page goes on saying
    // "coming soon" about it.
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    for (const [act, { retiredBy }] of Object.entries(UNAVAILABLE)) {
      expect(paths.filter((path) => retiredBy.test(path)), act).toEqual([]);
    }
    expect(UNAVAILABLE.switchOn.retiredBy.test("/api/v1/webhooks/subscribers/{subscriber_id}/switch-on")).toBe(true);
    expect(UNAVAILABLE.replay.retiredBy.test("/api/v1/webhooks/deliveries/{delivery}/replay")).toBe(true);
  });
});
