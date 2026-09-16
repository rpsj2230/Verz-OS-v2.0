/**
 * The Webhooks screen: the list, the three controls, their confirmations and the sentences.
 *
 * Mounted directly on a memory router at its own address, for the reason
 * `tests/sessions-page.test.tsx` gives. The failures worth testing look like the screen working: a
 * control for a reader the API said may not manage, a write sent without its confirmation, a
 * confirmation that paraphrases the API, a secret left in the page after it was sent, and a problem
 * shown away from its field.
 *
 * **What each write sends is read against the route's own request body**, so a key this console
 * invented is a failure here rather than a 422 in front of an administrator.
 *
 * Task ids: M27.8.12
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  KEEP_LABEL,
  NOT_MANAGEABLE,
  NO_SUBSCRIBERS,
  READING_WEBHOOKS,
  REGISTER_CONFIRM,
  REGISTER_LABEL,
  REPLACE_LABEL,
  SWITCH_OFF_LABEL,
} from "../src/pages/Webhooks";
import { BLANK_SENTENCES, type SubscriberRow, type WebhooksBody } from "../src/pages/webhooksQuery";
import { readRepoFile } from "./support/repo";
import { SOMETHING_DID_NOT_WORK } from "../src/pages/Overview";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { declaredRequestBodySchema } from "./support/openapi";

const LISTING = "/api/v1/webhooks";
const REGISTER = "/api/v1/webhooks/subscribers";
const CONSOLE_ORIGIN = "https://console.test";
const SECRET = "whsec-SIGNING-SENTINEL-0123456789abcdefABCDEF";

const REGISTERING = "The subscriber is told, at this address, whenever one of the chosen kinds happens.";
const REPLACING = "The new secret signs every request from now on.";
const SWITCHING_OFF = "The subscriber is told nothing more. This cannot be undone.";
const DELIVERY = "The worker sends what is due every minute.";
const DISPATCH_TOLD = "The dispatch runs every minute, and its last run is shown here.";

beforeAll(async () => {
  await import("../src/pages/Webhooks");
}, 60_000);

function subscriber(overrides: Partial<SubscriberRow> = {}): SubscriberRow {
  return {
    subscriber_id: "billing_bridge",
    endpoint: "https://hooks.example.test/brain",
    kinds: ["approval.requested"],
    active: true,
    created_by: "u_admin",
    created_at: "2019-03-04T09:00:00Z",
    deactivated_at: null,
    last_delivered_at: null,
    secret_held: true,
    secret_written_at: "2019-03-04T09:00:05Z",
    deliveries: [
      {
        kind: "approval.requested",
        state: "exhausted",
        attempts: 0,
        occurred_at: "2019-03-04T09:10:00Z",
        last_attempt_at: null,
        reason: "not sent: refused",
        next_attempt_at: null,
      },
    ],
    changes: [
      {
        change: "registered",
        changed_by: "u_admin",
        changed_at: "2019-03-04T09:00:00Z",
        secret_written_at: "2019-03-04T09:00:05Z",
      },
    ],
    ...overrides,
  };
}

function page(overrides: Partial<WebhooksBody> = {}): WebhooksBody {
  return {
    manageable: true,
    vault: "ready",
    vault_told: "The secrets vault answered.",
    subscribers: [subscriber()],
    findings: [],
    kinds: ["automation.run_finished", "operation.settled", "connector.health_changed", "approval.requested"],
    delivery: DELIVERY,
    dispatcher: {
      runs_here: true,
      paused: false,
      last_started_at: "2019-03-04T09:20:00Z",
      last_finished_at: "2019-03-04T09:20:01Z",
      last_outcome: "ok",
      last_report: "1 delivered, 0 to be tried again later, 0 set aside for a person",
      told: DISPATCH_TOLD,
    },
    inbound: {
      channels: [
        { channel: "lark", verification: "not_written", check: "", how: "Nothing here checks either yet." },
        { channel: "slack", verification: "written", check: "brain.channels.slack:verify", how: "Slack signs each request." },
      ],
      channels_told: "No channel on this install receives a webhook.",
      automation_path: "/api/v1/automation/tool-call",
      automation_told: "An automation calls this system with a credential of its own.",
    },
    registering: REGISTERING,
    replacing: REPLACING,
    switching_off: SWITCHING_OFF,
    secret_minimum: 32,
    ...overrides,
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
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
  const { Webhooks } = await import("../src/pages/Webhooks");
  const router = createMemoryRouter([{ path: "/webhooks", element: <Webhooks /> }], {
    initialEntries: ["/webhooks"],
  });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (container.textContent?.includes(READING_WEBHOOKS)) {
      throw new Error("still reading");
    }
  });
  return { container, idp };
}

function posts(idp: FakeIdp): { url: URL; body: unknown }[] {
  return idp.calls
    .filter(
      (call) =>
        call.init?.method === "POST" && new URL(call.url, CONSOLE_ORIGIN).pathname.startsWith("/api/"),
    )
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
  const found = [...container.querySelectorAll("label")].find(
    (one) => one.textContent?.trim() === label,
  );
  const input = found?.querySelector("input");
  if (!input) {
    throw new Error(`no field labelled ${label}`);
  }
  return input;
}

function confirmButton(container: HTMLElement, label: string): HTMLButtonElement {
  return button(container.querySelector(".confirm") as HTMLElement, label);
}

describe("what the webhooks screen shows", () => {
  test("a subscriber reads as where it is told, what about, whether its secret is held and what happened", async () => {
    // What breaks if this is deleted: every refusal below is satisfied by a page showing nothing.
    const { container } = await mount((url) => (url.pathname === LISTING ? json(page()) : null));
    const table = container.querySelector('[aria-label="Webhook subscribers"]')?.textContent ?? "";
    expect(table).toContain("billing_bridge");
    expect(table).toContain("https://hooks.example.test/brain");
    expect(table).toContain("approval.requested");
    expect(table).toContain("Held, written 2019-03-04 09:00");
    expect(container.textContent).toContain("not sent: refused");
    expect(container.textContent).toContain(DELIVERY);
    expect(container.textContent).toContain("No channel on this install receives a webhook.");
  });

  test("what the dispatch last did is shown beside the deliveries, with when each waits to be tried", async () => {
    // What breaks if this is deleted: an administrator is told how delivery works and never whether
    // it is happening, and a pending delivery reads as stuck with no time it will be tried again.
    const waiting = subscriber({
      deliveries: [
        {
          kind: "approval.requested",
          state: "pending",
          attempts: 2,
          occurred_at: "2019-03-04T09:10:00Z",
          last_attempt_at: "2019-03-04T09:11:00Z",
          reason: "attempt 2 of 8 came back unavailable; next in 120s",
          next_attempt_at: "2019-03-04T09:13:00Z",
        },
      ],
    });
    const { container } = await mount((url) =>
      url.pathname === LISTING ? json(page({ subscribers: [waiting] })) : null,
    );
    expect(container.textContent).toContain(DISPATCH_TOLD);
    const run = container.querySelector('[aria-label="The last run"]')?.textContent ?? "";
    expect(run).toContain("Finished at 2019-03-04 09:20");
    expect(run).toContain("1 delivered, 0 to be tried again later, 0 set aside for a person");
    const deliveries = container.querySelector('[aria-label="Recent deliveries to billing_bridge"]');
    expect(deliveries?.textContent).toContain("2019-03-04 09:13");
  });

  test("a reader shown no dispatcher sees no sentence about it, and a failed run says it failed", async () => {
    // What breaks if this is deleted: the page draws a dispatch state the API did not send, or a
    // failed run reads as a finished one.
    const hidden = await mount((url) =>
      url.pathname === LISTING ? json(page({ manageable: false, subscribers: [], dispatcher: null })) : null,
    );
    expect(hidden.container.textContent).not.toContain(DISPATCH_TOLD);
    const failed = await mount((url) =>
      url.pathname === LISTING
        ? json(
            page({
              dispatcher: {
                runs_here: true,
                paused: false,
                last_started_at: "2019-03-04T09:20:00Z",
                last_finished_at: "2019-03-04T09:20:01Z",
                last_outcome: "failed",
                last_report: "The run failed with OutboxStoreError.",
                told: "The dispatch's last run failed.",
              },
            }),
          )
        : null,
    );
    const run = failed.container.querySelector('[aria-label="The last run"]')?.textContent ?? "";
    expect(run).toContain("Failed at 2019-03-04 09:20");
    expect(run).toContain("The run failed with OutboxStoreError.");
  });

  test("each arriving channel says whether its check is written and names it when it is", async () => {
    // What breaks if this is deleted: a channel with no check reads the same as one with a check.
    const { container } = await mount((url) => (url.pathname === LISTING ? json(page()) : null));
    const rows = [...(container.querySelector('[aria-label="Channels"]')?.querySelectorAll("tbody tr") ?? [])].map(
      (row) => row.textContent ?? "",
    );
    expect(rows).toHaveLength(2);
    expect(rows[0]).toContain("lark");
    expect(rows[0]).toContain("Not written");
    expect(rows[1]).toContain("Written");
    expect(rows[1]).toContain("brain.channels.slack:verify");
  });

  test("a reader who may not manage sees no list and no control, and is told why", async () => {
    // What breaks if this is deleted: the register form and its button drawn for a reader the API
    // said may change nothing.
    const { container } = await mount((url) =>
      url.pathname === LISTING ? json(page({ manageable: false, subscribers: [] })) : null,
    );
    expect(container.textContent).toContain(NOT_MANAGEABLE);
    expect(container.textContent).not.toContain(NO_SUBSCRIBERS);
    expect(container.querySelectorAll("button")).toHaveLength(0);
  });

  test("a secret the vault cannot be asked about reads as not known, never as not held", async () => {
    // What breaks if this is deleted: a silent vault reads as a subscriber with no secret.
    const { container } = await mount((url) =>
      url.pathname === LISTING
        ? json(page({ vault: "unreachable", vault_told: "The secrets vault did not answer.", subscribers: [subscriber({ secret_held: null, secret_written_at: null })] }))
        : null,
    );
    expect(container.textContent).toContain("Not known");
    expect(container.textContent).not.toContain("Not held");
    expect(container.textContent).toContain("The secrets vault did not answer.");
  });

  test("a switched-off subscriber has no control", async () => {
    // What breaks if this is deleted: a control offered for an act the route will refuse.
    const { container } = await mount((url) =>
      url.pathname === LISTING
        ? json(page({ subscribers: [subscriber({ active: false, deactivated_at: "2019-03-05T00:00:00Z" })] }))
        : null,
    );
    const labels = [...container.querySelectorAll("button")].map((one) => one.textContent);
    expect(labels).toEqual([REGISTER_LABEL]);
    expect(container.textContent).toContain("Off since 2019-03-05 00:00");
  });
});

describe("what the webhooks screen does", () => {
  test("registering is confirmed in the API's words and sends exactly the route's four fields", async () => {
    // What breaks if this is deleted: a registration sent with no second step, a body key the route
    // forbids, or a secret left sitting in the form after it was sent.
    let registered = false;
    const { container, idp } = await mount((url) => {
      if (url.pathname === REGISTER) {
        registered = true;
        return json({
          subscriber_id: "new_bridge",
          change: "registered",
          changed_at: "2019-03-04T10:00:00Z",
          secret_written_at: "2019-03-04T10:00:00Z",
          told: "The subscriber is registered and its signing secret is held in the vault.",
        });
      }
      return url.pathname === LISTING ? json(page({ subscribers: registered ? [] : [subscriber()] })) : null;
    });
    const declared = declaredRequestBodySchema(REGISTER, "post");

    fireEvent.change(field(container, "Id"), { target: { value: "new_bridge" } });
    fireEvent.change(field(container, "Address it is told at"), { target: { value: "https://hooks.example.test/new" } });
    fireEvent.click(field(container, "operation.settled"));
    fireEvent.change(field(container, "Signing secret"), { target: { value: SECRET } });
    fireEvent.click(button(container, REGISTER_LABEL));

    const panel = container.querySelector(".confirm") as HTMLElement;
    expect(panel.textContent).toContain("new_bridge");
    expect(panel.textContent).toContain(REGISTERING);
    expect(posts(idp)).toEqual([]);

    fireEvent.click(confirmButton(container, REGISTER_CONFIRM));
    await waitFor(() => {
      expect(container.textContent).toContain("The subscriber is registered");
    });
    const [sent] = posts(idp);
    expect(Object.keys(sent?.body as object).sort()).toEqual(Object.keys(declared["properties"] as object).sort());
    expect(sent?.body).toEqual({
      subscriber_id: "new_bridge",
      endpoint: "https://hooks.example.test/new",
      kinds: ["operation.settled"],
      secret: SECRET,
    });
    expect(container.innerHTML).not.toContain(SECRET);
  });

  test("a registration with a blank field says what to fill in beside each one, and asks and sends nothing", async () => {
    // What breaks if this is deleted: a registration with no id, no address, no kind and no secret
    // opening a confirmation a person can agree to, and being refused only after they have.
    const { container, idp } = await mount((url) => (url.pathname === LISTING ? json(page()) : null));

    fireEvent.click(button(container, REGISTER_LABEL));

    expect(container.querySelector(".confirm")).toBeNull();
    expect(posts(idp)).toEqual([]);
    for (const [name, sentence] of Object.entries(BLANK_SENTENCES)) {
      expect(container.querySelector(`[aria-label="Problems with ${name}"]`)?.textContent, name).toBe(sentence);
    }

    fireEvent.change(field(container, "Id"), { target: { value: "new_bridge" } });
    fireEvent.change(field(container, "Address it is told at"), { target: { value: "https://hooks.example.test/new" } });
    fireEvent.click(field(container, "operation.settled"));
    fireEvent.change(field(container, "Signing secret"), { target: { value: SECRET } });
    fireEvent.click(button(container, REGISTER_LABEL));
    expect(container.querySelector(".confirm")).not.toBeNull();
    expect(container.querySelector('[aria-label^="Problems with"]')).toBeNull();
  });

  test("the sentences for a blank field are the API's own", () => {
    // What breaks if this is deleted: the console's copy of the four sentences drifting from the
    // ones the route answers with, so the same blank field is described two ways depending on which
    // side noticed it. Read from the Python, with its implicitly joined literals joined.
    const python = readRepoFile("src/brain/ops/webhook_admin.py").replace(/"\s+"/g, "");
    for (const [name, sentence] of Object.entries(BLANK_SENTENCES)) {
      expect(python, name).toContain(`"${sentence}"`);
    }
  });

  test("a refused registration shows each problem beside its field and keeps the secret out of the page", async () => {
    // What breaks if this is deleted: a 422 reads as a generic failure, or the secret stays in the
    // field for the next person at the screen.
    const { container } = await mount((url) => {
      if (url.pathname === REGISTER) {
        return json(
          {
            problems: [
              { field: "subscriber_id", code: "taken", message: "A subscriber with this id is already registered." },
              { field: "secret", code: "too_short", message: "Use a secret of at least 32 characters." },
            ],
          },
          422,
        );
      }
      return url.pathname === LISTING ? json(page()) : null;
    });
    fireEvent.change(field(container, "Id"), { target: { value: "billing_bridge" } });
    fireEvent.change(field(container, "Address it is told at"), { target: { value: "https://hooks.example.test/new" } });
    fireEvent.click(field(container, "operation.settled"));
    fireEvent.change(field(container, "Signing secret"), { target: { value: "short-SENTINEL" } });
    fireEvent.click(button(container, REGISTER_LABEL));
    fireEvent.click(confirmButton(container, REGISTER_CONFIRM));

    await waitFor(() => {
      expect(container.querySelector('[aria-label="Problems with subscriber_id"]')?.textContent).toContain(
        "already registered",
      );
    });
    expect(container.querySelector('[aria-label="Problems with secret"]')?.textContent).toContain("32 characters");
    expect(container.textContent).not.toContain(SOMETHING_DID_NOT_WORK);
    expect(field(container, "Signing secret").value).toBe("");
  });

  test("replacing a secret and switching off are each confirmed, and keeping things sends nothing", async () => {
    // What breaks if this is deleted: a press switches a subscriber off for good with no second
    // step, or the confirmation is this console's paraphrase.
    const { container, idp } = await mount((url) => {
      if (url.pathname.endsWith("/switch-off") || url.pathname.endsWith("/secret")) {
        return json({ subscriber_id: "billing_bridge", change: "switched_off", changed_at: "2019-03-04T10:00:00Z", secret_written_at: null, told: "The subscriber is switched off." });
      }
      return url.pathname === LISTING ? json(page()) : null;
    });

    fireEvent.click(button(container, SWITCH_OFF_LABEL));
    expect((container.querySelector(".confirm") as HTMLElement).textContent).toContain(SWITCHING_OFF);
    fireEvent.click(confirmButton(container, KEEP_LABEL));
    expect(container.querySelector(".confirm")).toBeNull();
    expect(posts(idp)).toEqual([]);

    fireEvent.click(button(container, REPLACE_LABEL));
    fireEvent.change(field(container, "New signing secret"), { target: { value: SECRET } });
    fireEvent.submit(container.querySelector('[aria-label="Replace the signing secret of billing_bridge"]') as HTMLFormElement);
    expect((container.querySelector(".confirm") as HTMLElement).textContent).toContain(REPLACING);
    fireEvent.click(confirmButton(container, REPLACE_LABEL));
    await waitFor(() => {
      expect(posts(idp)).toHaveLength(1);
    });
    const [rotated] = posts(idp);
    expect(rotated?.url.pathname).toBe("/api/v1/webhooks/subscribers/billing_bridge/secret");
    expect(rotated?.body).toEqual({ secret: SECRET });
  });
});
