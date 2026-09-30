/**
 * The Channels module on the page kit, and a person's own channels card: the list, one channel's
 * three views, every write they send, and the acts drawn as not built yet.
 *
 * Reached through the application's own route table, so the list, the lazily loaded detail page
 * and its views are the ones an administrator opens. The failures worth testing look like the page
 * working: a principal id drawn where a name belongs, a figure the API did not send drawn as nought,
 * a switch or an unbinding sent without being confirmed, a set-up sent blank or with its secret
 * left in the page, and a "coming soon" left standing after its route landed.
 *
 * Task ids: M27.13.1, M27.15.43, M27.16.1, M10.3.1, M10.3.4, M10.1.2, M10.1.3, M10.1.4
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { NOT_COPIED_TEXT, NOT_RECORDED } from "../src/components/kit";
import { DISCONNECT_LABEL, GET_CODE_LABEL, READING_MY_CHANNELS } from "../src/components/MyChannels";
import { TENANT_FORMAT } from "../src/pages/channelsQuery";
import { ACT_LABELS, UNAVAILABLE } from "../src/pages/channels/channelActions";
import { SWITCH_OFF_CONSEQUENCE } from "../src/pages/channels/ChannelDetailPage";
import { UNBIND_CONSEQUENCE } from "../src/pages/channels/ChannelDashboard";
import { partLabel, SECRET_FORMAT } from "../src/pages/channels/ChannelProfile";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { apiDocument } from "./support/openapi";
import { PAGES } from "./support/pageCases";
import { installRadixStubs } from "./support/radix";

const CONSOLE_ORIGIN = "https://console.test";
const SECRET_TYPED = "channel-secret-typed-in-0123456789";
const CODE = "Qm9vZ2llV29vZ2llMTIzNA";
const AT = "2019-03-04T09:00:00Z";
const ROOMS_TOLD = "This channel cannot say who is in a group, so a group's floor is taken as nothing.";

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/Channel");
  await import("../src/components/MyChannels");
}, 60_000);

function row(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    channel: "webhook",
    label: "Webhook",
    receives: true,
    status: "on",
    secret: "held",
    health: "working",
    last_delivered_at: AT,
    events_path: "/api/v1/channels/webhook/events",
    events_address: "",
    steps: [],
    tenant_fields: ["reply_url"],
    secret_parts: [],
    tenant: { reply_url: "https://hooks.example.test/reply" },
    changed_at: AT,
    changed_by: "u_ada",
    changed_by_name: "Ada Admin",
    ...overrides,
  };
}

const SLACK = row({
  channel: "slack",
  label: "Slack",
  receives: false,
  status: "not_set_up",
  secret: "none",
  health: "not_set_up",
  last_delivered_at: null,
  events_path: "",
  tenant_fields: [],
  tenant: {},
  changed_at: null,
  changed_by: null,
  changed_by_name: null,
});

function stats(period: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    channel: "webhook",
    bound_people: 3,
    bound_basis: "everyone",
    last_event: AT,
    at_least: false,
    periods: ["7d", "30d"].map((range) => ({
      range,
      since: AT,
      until: AT,
      received: 12,
      sent: 11,
      failed: 1,
      unknown: 0,
      refused_inbound: 2,
      ...period,
    })),
    unrecorded: [],
  };
}

const HEALTH = {
  channel: "webhook",
  receives: true,
  features: ["cards"],
  max_classification: "internal",
  can_carry_label: true,
  verbs: ["invoke", "read"],
  rooms: "as_nothing",
  rooms_told: ROOMS_TOLD,
  health: "working",
  told: "Working. The newest delivery that says anything about it went through.",
  last_received_at: AT,
  last_sent_at: AT,
  last_fault: null,
};

const BOUND = {
  channel: "webhook",
  items: [
    { principal_id: "u_bo", display_name: "Bo Bound", bound_at: AT },
    { principal_id: "u_cy", display_name: "Cy Chat", bound_at: AT },
  ],
  next_cursor: null,
  truncated: false,
  told: "Each person listed proved a chat account is theirs.",
};

const DELIVERIES = {
  channel: "webhook",
  deliveries: [{ direction: "inbound", outcome: "refused", reason: "bad_signature", vendor_status: null, recorded_at: AT }],
};

function answers(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    "/api/v1/console/channels": { items: [row(), SLACK], next_cursor: null },
    "/api/v1/console/channels/webhook": row(),
    "/api/v1/console/channels/webhook/stats": stats(),
    "/api/v1/channels/webhook/health": HEALTH,
    "/api/v1/channels/webhook/bindings": BOUND,
    "/api/v1/channels/webhook/deliveries": DELIVERIES,
    "/api/v1/webhooks": {
      inbound: {
        channels: [{ channel: "webhook", verification: "written", check: "x", how: "The company's system signs each request." }],
      },
    },
    ...overrides,
  };
}

interface Sent {
  readonly method: string;
  readonly path: string;
  readonly query: string;
  readonly body: unknown;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

async function consoleAt(path: string, read: Record<string, unknown>): Promise<{ container: HTMLElement; sent: Sent[]; idp: FakeIdp }> {
  const sent: Sent[] = [];
  const idp = fakeIdentityProvider({
    api(url, init) {
      const where = new URL(url, CONSOLE_ORIGIN);
      const method = (init?.method ?? "GET").toUpperCase();
      const body = typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : null;
      sent.push({ method, path: where.pathname, query: where.search, body });
      if (method !== "GET") {
        return json({ told: "Done." });
      }
      return where.pathname in read ? json(read[where.pathname]) : null;
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
  return { container, sent, idp };
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

/** The page's text with the Advanced section taken out, which is the one place an id may be. */
function outsideAdvanced(container: HTMLElement): string {
  const copy = container.cloneNode(true) as HTMLElement;
  copy.querySelectorAll('[data-slot="advanced"]').forEach((one) => {
    one.remove();
  });
  return copy.textContent ?? "";
}

describe("the Channels list", () => {
  test("each channel reads by name with its status, secret, health, bound people and last activity, and no id", async () => {
    // What breaks if this is deleted: the list drops a channel nobody set up, draws a principal id,
    // or reads nought bound people on a channel this release does not receive on.
    const { container } = await consoleAt("/channels", answers());
    await waitFor(() => {
      expect(container.textContent).toContain("3");
    });
    const rows = [...container.querySelectorAll("tbody tr")].map((one) => one.textContent ?? "");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toContain("Webhook");
    expect(rows[0]).toContain("On");
    expect(rows[0]).toContain("Held");
    expect(rows[0]).toContain("Working");
    expect(rows[1]).toContain("Slack");
    expect(rows[1]).toContain("Not set up");
    expect(rows[1]).toContain("None kept");
    expect(rows[1]).toContain("Never");
    expect(container.textContent).not.toContain("u_ada");
  });

  test("the search asks the list route, which searches on the server", async () => {
    // What breaks if this is deleted: the search box narrows nothing, or narrows only what arrived.
    const { container, sent } = await consoleAt("/channels", answers());
    const search = container.querySelector<HTMLInputElement>('input[type="search"]');
    expect(search).not.toBeNull();
    fireEvent.change(search as HTMLInputElement, { target: { value: "teams" } });
    await waitFor(() => {
      expect(sent.some((one) => one.path === "/api/v1/console/channels" && one.query.includes("q=teams"))).toBe(true);
    });
  });
});

describe("one channel's page", () => {
  test("the Dashboard draws the stats route's figures, and a figure it did not send reads not recorded, never nought", async () => {
    // What breaks if this is deleted: a period with no sent figure reads 0 sent, which is a claim
    // somebody counted and found none.
    const read = answers({ "/api/v1/console/channels/webhook/stats": stats({ sent: undefined }) });
    const { container } = await consoleAt("/channels/webhook", read);
    await waitFor(() => {
      expect(container.querySelector('[data-slot="kpi-strip"][aria-label="This channel\'s figures"]')).not.toBeNull();
    });
    const strip = container.querySelector('[aria-label="This channel\'s figures"]')?.textContent ?? "";
    expect(strip).toContain("12");
    expect(strip).toContain(NOT_RECORDED);
    expect(strip).toContain("2");
    await waitFor(() => {
      expect(container.textContent).toContain("Bo Bound");
    });
    expect(outsideAdvanced(container)).not.toContain("u_bo");
    expect(outsideAdvanced(container)).not.toContain("u_ada");
    expect(container.textContent).toContain("Ada Admin");
  });

  test("unbinding is confirmed, says what it does, and sends that person and nobody else", async () => {
    // What breaks if this is deleted: an unbinding goes out on one press, or names the wrong person.
    const { container, sent } = await consoleAt("/channels/webhook", answers());
    await waitFor(() => {
      expect(container.textContent).toContain("Cy Chat");
    });
    fireEvent.click(button(container, `${ACT_LABELS.unbind}: Cy Chat`));
    expect(sent.filter((one) => one.method === "POST")).toEqual([]);
    expect(dialog().textContent).toContain(UNBIND_CONSEQUENCE);
    fireEvent.click(button(dialog(), ACT_LABELS.unbind));
    await waitFor(() => {
      expect(sent.filter((one) => one.method === "POST").map((one) => [one.path, one.body])).toEqual([
        ["/api/v1/channels/webhook/bindings/unbind", { principal_id: "u_cy" }],
      ]);
    });
  });

  test("switching off is confirmed with what it refuses, and sends only the new state", async () => {
    // What breaks if this is deleted: the switch goes out unconfirmed, or the page stops saying that
    // a channel switched off refuses its vendor's requests (M27.15.43).
    const { container, sent } = await consoleAt("/channels/webhook", answers());
    fireEvent.click(button(container, ACT_LABELS.switchOff));
    expect(dialog().textContent).toContain(SWITCH_OFF_CONSEQUENCE);
    expect(SWITCH_OFF_CONSEQUENCE).toContain("refused");
    fireEvent.click(button(dialog(), ACT_LABELS.switchOff));
    await waitFor(() => {
      expect(sent.filter((one) => one.method === "POST").map((one) => [one.path, one.body])).toEqual([
        ["/api/v1/channels/webhook/switch", { enabled: false }],
      ]);
    });
  });

  test("the set-up says what each field accepts, is refused blank beside the field, and filled sends the secret once", async () => {
    // What breaks if this is deleted: a blank identifier is one press from a confirmation, a field
    // says what it wanted only after a refusal, or the secret stays in the page after it is sent.
    const { container, sent } = await consoleAt("/channels/webhook/profile", answers());
    const form = container.querySelector<HTMLFormElement>('form[aria-label="Set up Webhook"]');
    expect(form).not.toBeNull();
    expect(form?.textContent).toContain(TENANT_FORMAT);
    expect(form?.textContent).toContain(SECRET_FORMAT);
    const identifier = form?.querySelector<HTMLInputElement>('input[name="reply_url"]') as HTMLInputElement;
    fireEvent.change(identifier, { target: { value: "" } });
    fireEvent.click(button(form as HTMLFormElement, ACT_LABELS.save));
    expect(form?.querySelector('[aria-label="Problems with reply_url"]')?.textContent).toContain("Fill in reply_url");
    expect(document.body.querySelector('[data-slot="confirm-dialog"]')).toBeNull();

    fireEvent.change(identifier, { target: { value: "https://hooks.example.test/next" } });
    const secret = form?.querySelector<HTMLInputElement>('[data-slot="secret-field"] input') as HTMLInputElement;
    fireEvent.input(secret, { target: { value: SECRET_TYPED } });
    fireEvent.click(button(form as HTMLFormElement, ACT_LABELS.save));
    fireEvent.click(button(dialog(), ACT_LABELS.save));
    await waitFor(() => {
      expect(sent.filter((one) => one.method === "PUT").map((one) => [one.path, one.body])).toEqual([
        [
          "/api/v1/channels/webhook",
          { enabled: true, tenant: { reply_url: "https://hooks.example.test/next" }, secret: SECRET_TYPED },
        ],
      ]);
    });
    expect(document.body.innerHTML).not.toContain(SECRET_TYPED);
  });

  test("the About view says the verbs, how a group is answered and what switching off refuses, with ids under Advanced", async () => {
    // What breaks if this is deleted: M27.15.43's statements drop off the page, or the channel's key
    // and a person's id are drawn in the page text rather than under Advanced.
    const { container } = await consoleAt("/channels/webhook/about", answers());
    await waitFor(() => {
      expect(container.textContent).toContain(ROOMS_TOLD);
    });
    const text = outsideAdvanced(container);
    expect(text).toContain("Ask and read");
    expect(text).toContain("Run tools");
    expect(text).not.toContain("Approve");
    expect(text).toContain("refused");
    expect(text).toContain("Written. The company's system signs each request.");
    await waitFor(() => {
      expect(container.textContent).toContain("bad signature");
    });
    expect(text).not.toContain("u_ada");
    const advanced = container.querySelector('[data-slot="advanced"]')?.textContent ?? "";
    expect(advanced).toContain("u_ada");
    expect(advanced).toContain("webhook");
  });

  test("a channel this release does not receive on says so instead of an empty strip or a form", async () => {
    // What breaks if this is deleted: Slack's page draws a strip of figures nothing records, or a
    // set-up form whose save the API refuses.
    const read = answers({
      "/api/v1/console/channels/slack": SLACK,
      "/api/v1/channels/slack/health": { ...HEALTH, channel: "slack", receives: false, rooms: "not_received" },
    });
    const { container, sent } = await consoleAt("/channels/slack", read);
    expect(container.textContent).toContain("Not received by this release");
    expect(container.querySelector('[data-slot="kpi-strip"][aria-label="This channel\'s figures"]')).toBeNull();
    expect(sent.some((one) => one.path.endsWith("/stats") || one.path.endsWith("/bindings"))).toBe(false);
  });

  test("every act drawn as unavailable names no route the API document declares", () => {
    // What breaks if this is deleted: a verification route lands and the page goes on saying "coming
    // soon" about it.
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    for (const [act, { retiredBy }] of Object.entries(UNAVAILABLE)) {
      expect(paths.filter((path) => retiredBy.test(path)), act).toEqual([]);
    }
    expect(UNAVAILABLE.verify.retiredBy.test("/api/v1/channels/{name}/verify")).toBe(true);
  });
});

const SCRIPT = "export default { async email(message, env) {} };";
const ADDRESS_TO_PASTE = "https://brain.example.test/api/v1/channels/email/events";

function aStep(key: string, extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    key,
    title: `Do ${key}`,
    text: `What to press for ${key}.`,
    sketch: { place: "Vendor", heading: key, menu: [], menu_mark: "", tabs: [], tab_mark: "", lines: [], button: "" },
    link: "",
    link_label: "",
    asks: [],
    copy_text: "",
    copy_label: "",
    path: "",
    choices: [],
    ...extra,
  };
}

const EMAIL = row({
  channel: "email",
  label: "Email",
  status: "not_set_up",
  secret: "none",
  health: "not_set_up",
  last_delivered_at: null,
  events_path: "/api/v1/channels/email/events",
  events_address: ADDRESS_TO_PASTE,
  tenant_fields: ["address"],
  tenant: {},
  changed_at: null,
  changed_by: null,
  changed_by_name: null,
  steps: [
    aStep("address", { link: "https://dash.example.test/", link_label: "Open the vendor" }),
    aStep("worker", { asks: ["events_address"], copy_text: SCRIPT, copy_label: "Copy the Worker script" }),
    aStep("save", { asks: ["address", "secret"] }),
  ],
});

function emailAnswers(): Record<string, unknown> {
  return answers({
    "/api/v1/console/channels/email": EMAIL,
    "/api/v1/console/channels/email/stats": { ...stats(), channel: "email" },
    "/api/v1/channels/email/health": { ...HEALTH, channel: "email" },
    "/api/v1/channels/email/bindings": { ...BOUND, channel: "email", items: [] },
    "/api/v1/channels/email/deliveries": { channel: "email", deliveries: [] },
  });
}

function flow(): HTMLElement {
  const found = document.body.querySelector<HTMLElement>('[data-slot="flow-dialog"]');
  if (found === null) {
    throw new Error("No connect flow is open.");
  }
  return found;
}

describe("connecting a channel one screen at a time", () => {
  test("a channel with steps offers them from its header, with the address to paste and the script to copy", async () => {
    // What breaks if this is deleted: the steps a channel's module declares reach no screen, the
    // Worker step shows no address to paste, or its script can only be retyped by hand when the
    // browser refuses the clipboard.
    const { container } = await consoleAt("/channels/email", emailAnswers());
    fireEvent.click(button(container, "Connect Email"));
    expect(flow().textContent).toContain("Step 1 of 3");
    expect(flow().querySelector('a[href="https://dash.example.test/"]')?.textContent).toContain("Open the vendor");
    fireEvent.click(button(flow(), "Step 2 of 3"));
    expect(flow().textContent).toContain(ADDRESS_TO_PASTE);
    fireEvent.click(button(flow(), "Copy the Worker script"));
    await waitFor(() => {
      expect(flow().textContent).toContain(NOT_COPIED_TEXT);
    });
    const script = flow().querySelector<HTMLTextAreaElement>('textarea[aria-label="Copy the Worker script"]');
    expect(script?.value).toBe(SCRIPT);
  });

  test("the last screen is the set-up form, sends the secret once, and then offers a test message", async () => {
    // What breaks if this is deleted: the flow ends in a form that saves nothing, sends the secret
    // twice or leaves it in the page, or closes before the test message it promises.
    const { container, sent } = await consoleAt("/channels/email", emailAnswers());
    fireEvent.click(button(container, "Connect Email"));
    fireEvent.click(button(flow(), "Step 3 of 3"));
    const form = flow().querySelector<HTMLFormElement>('form[aria-label="Set up Email"]') as HTMLFormElement;
    expect(flow().querySelector('form[aria-label="Send test message on Email"]')).toBeNull();
    fireEvent.change(form.querySelector('input[name="address"]') as HTMLInputElement, {
      target: { value: "ask@ask.example.test" },
    });
    fireEvent.input(form.querySelector('[data-slot="secret-field"] input') as HTMLInputElement, {
      target: { value: SECRET_TYPED },
    });
    fireEvent.click(form.querySelector('input[name="enabled"]') as HTMLInputElement);
    fireEvent.click(button(form, ACT_LABELS.save));
    fireEvent.click(button(dialog(), ACT_LABELS.save));
    await waitFor(() => {
      expect(sent.filter((one) => one.method === "PUT").map((one) => [one.path, one.body])).toEqual([
        ["/api/v1/channels/email", { enabled: true, tenant: { address: "ask@ask.example.test" }, secret: SECRET_TYPED }],
      ]);
    });
    await waitFor(() => {
      expect(flow().querySelector('form[aria-label="Send test message on Email"]')).not.toBeNull();
    });
    expect(document.body.innerHTML).not.toContain(SECRET_TYPED);
  });

  test("a secret of two parts is typed in two fields and sent whole, never one part alone", async () => {
    // What breaks if this is deleted: Slack's form takes one secret field that no wire can read, or
    // saves a new signing secret beside an old token, which verifies and then cannot send.
    const slack = row({
      channel: "slack",
      label: "Slack",
      status: "not_set_up",
      secret: "none",
      health: "not_set_up",
      last_delivered_at: null,
      events_path: "/api/v1/channels/slack/events",
      events_address: "https://brain.example.test/api/v1/channels/slack/events",
      tenant_fields: ["bot_id"],
      secret_parts: ["signing_secret", "bot_token"],
      tenant: {},
      changed_at: null,
      changed_by: null,
      changed_by_name: null,
      steps: [
        aStep("create", { asks: ["events_address"], copy_text: "{}", copy_label: "Copy the app manifest" }),
        aStep("save", { asks: ["bot_id", "signing_secret", "bot_token"] }),
        aStep("verify"),
      ],
    });
    const read = answers({
      "/api/v1/console/channels/slack": slack,
      "/api/v1/console/channels/slack/stats": { ...stats(), channel: "slack" },
      "/api/v1/channels/slack/health": { ...HEALTH, channel: "slack" },
      "/api/v1/channels/slack/bindings": { ...BOUND, channel: "slack", items: [] },
      "/api/v1/channels/slack/deliveries": { channel: "slack", deliveries: [] },
    });
    const { container, sent } = await consoleAt("/channels/slack", read);
    fireEvent.click(button(container, "Connect Slack"));
    fireEvent.click(button(flow(), "Step 2 of 3"));
    const form = flow().querySelector<HTMLFormElement>('form[aria-label="Set up Slack"]') as HTMLFormElement;
    const secrets = [...form.querySelectorAll<HTMLInputElement>('[data-slot="secret-field"] input')];
    expect(secrets).toHaveLength(2);
    expect(form.textContent).toContain(partLabel("signing_secret"));
    expect(form.textContent).toContain(partLabel("bot_token"));
    fireEvent.change(form.querySelector('input[name="bot_id"]') as HTMLInputElement, { target: { value: "U0BRAINBOT" } });
    fireEvent.input(secrets[0] as HTMLInputElement, { target: { value: SECRET_TYPED } });
    fireEvent.click(button(form, ACT_LABELS.save));
    expect(form.querySelector('[aria-label="Problems with bot_token"]')?.textContent).toContain("Paste bot_token too");
    expect(document.body.querySelector('[data-slot="confirm-dialog"]')).toBeNull();

    fireEvent.input(secrets[1] as HTMLInputElement, { target: { value: "xoxb-typed-in-0123" } });
    fireEvent.click(button(form, ACT_LABELS.save));
    fireEvent.click(button(dialog(), ACT_LABELS.save));
    await waitFor(() => {
      expect(sent.filter((one) => one.method === "PUT").map((one) => [one.path, one.body])).toEqual([
        [
          "/api/v1/channels/slack",
          {
            enabled: false,
            tenant: { bot_id: "U0BRAINBOT" },
            secret_parts: { signing_secret: SECRET_TYPED, bot_token: "xoxb-typed-in-0123" },
          },
        ],
      ]);
    });
    expect(document.body.innerHTML).not.toContain(SECRET_TYPED);
    expect(document.body.innerHTML).not.toContain("xoxb-typed-in-0123");
  });

  test("steps that branch show the chosen path, and its form asks only that path's fields", async () => {
    // What breaks if this is deleted: a company without Cloudflare is walked through Cloudflare's
    // steps, or the mailbox form asks for the Worker's secret and not the mailbox's.
    const mailboxFields = ["address", "imap_host", "imap_port", "imap_user", "receiver", "domains"];
    const branching = row({
      ...EMAIL,
      tenant_fields: mailboxFields,
      steps: [
        aStep("where", {
          choices: [
            { key: "mailbox", label: "No: read a mailbox" },
            { key: "cloudflare", label: "Yes: use Cloudflare Email Routing" },
          ],
        }),
        aStep("relay"),
        aStep("mailbox", { path: "mailbox" }),
        aStep("save_mailbox", { path: "mailbox", asks: [...mailboxFields, "secret"] }),
        aStep("worker", { path: "cloudflare", asks: ["events_address"] }),
        aStep("save", { path: "cloudflare", asks: ["address", "secret"] }),
      ],
    });
    const read = { ...emailAnswers(), "/api/v1/console/channels/email": branching };
    const { container, sent } = await consoleAt("/channels/email", read);
    fireEvent.click(button(container, "Connect Email"));
    expect(flow().textContent).toContain("Step 1 of 2");
    fireEvent.click(button(flow(), "No: read a mailbox"));
    expect(flow().textContent).toContain("Step 2 of 4");
    fireEvent.click(button(flow(), "Step 4 of 4"));
    const form = flow().querySelector<HTMLFormElement>('form[aria-label="Set up Email"]') as HTMLFormElement;
    const drawn = [...form.querySelectorAll<HTMLInputElement>("input[name]")].map((one) => one.name).filter((one) => one !== "enabled");
    expect(drawn).toEqual(mailboxFields);
    const values: Record<string, string> = {
      address: "ask@example.test",
      imap_host: "imap.example.test",
      imap_port: "993",
      imap_user: "ask@example.test",
      receiver: "mx.example.test",
      domains: "example.test",
    };
    for (const [name, value] of Object.entries(values)) {
      fireEvent.change(form.querySelector(`input[name="${name}"]`) as HTMLInputElement, { target: { value } });
    }
    fireEvent.input(form.querySelector('[data-slot="secret-field"] input') as HTMLInputElement, { target: { value: SECRET_TYPED } });
    fireEvent.click(button(form, ACT_LABELS.save));
    fireEvent.click(button(dialog(), ACT_LABELS.save));
    await waitFor(() => {
      expect(sent.filter((one) => one.method === "PUT").map((one) => one.body)).toEqual([
        { enabled: false, tenant: values, secret: SECRET_TYPED },
      ]);
    });

    fireEvent.click(button(flow(), "Step 1 of 4"));
    fireEvent.click(button(flow(), "Yes: use Cloudflare Email Routing"));
    fireEvent.click(button(flow(), "Step 4 of 4"));
    const other = flow().querySelectorAll<HTMLFormElement>('form[aria-label="Set up Email"]');
    const visible = [...other].find((one) => !one.closest("[hidden]"));
    const names = [...(visible?.querySelectorAll<HTMLInputElement>("input[name]") ?? [])].map((one) => one.name).filter((one) => one !== "enabled");
    expect(names).toEqual(["address"]);
  });

  test("a channel with no steps offers no connect button", async () => {
    // What breaks if this is deleted: every channel shows a Connect button that opens an empty flow.
    const { container } = await consoleAt("/channels/webhook", answers());
    expect([...container.querySelectorAll("button")].some((one) => one.textContent?.startsWith("Connect"))).toBe(false);
  });
});

describe("a person's own channels card", () => {
  test("a code is asked for, shown once with how long it lasts, and disconnecting is confirmed", async () => {
    // What breaks if this is deleted: the one flow a person uses to connect a chat has no test at
    // the screen, or disconnecting goes out on one press.
    const written = {
      channel: "webhook",
      code: CODE,
      expires_at: "2019-03-04T09:10:00Z",
      told: "Send this code, on its own, to the Brain on webhook within 10 minutes.",
    };
    const read = PAGES["/me"]?.answers ?? {};
    const idp = fakeIdentityProvider({
      api(url, init) {
        const path = new URL(url, CONSOLE_ORIGIN).pathname;
        if (init?.method !== undefined && init.method !== "GET") {
          return json(written);
        }
        return path in read ? json(read[path]) : null;
      },
    });
    const loaded = await loadConsole({ idp });
    await signIn(loaded);
    const { MyChannels } = await import("../src/components/MyChannels");
    const router = createMemoryRouter([{ path: "/x", element: <MyChannels /> }], { initialEntries: ["/x"] });
    const { container } = render(<RouterProvider router={router} />);
    await waitFor(() => {
      if (container.textContent?.includes(READING_MY_CHANNELS)) {
        throw new Error("still reading");
      }
    });
    const posted = (path: string) =>
      idp.calls.filter((call) => call.init?.method === "POST" && new URL(call.url, CONSOLE_ORIGIN).pathname === path);
    fireEvent.click(button(container, `${GET_CODE_LABEL}: webhook`));
    await waitFor(() => {
      expect(container.textContent).toContain(CODE);
    });
    expect(posted("/api/v1/me/channels/webhook/code")).toHaveLength(1);
    fireEvent.click(button(container, `${DISCONNECT_LABEL}: lark`));
    expect(posted("/api/v1/me/channels/lark/unbind")).toHaveLength(0);
    const confirm = [...container.querySelectorAll("section.confirm button")].at(-1) as HTMLButtonElement;
    fireEvent.click(confirm);
    await waitFor(() => {
      expect(posted("/api/v1/me/channels/lark/unbind")).toHaveLength(1);
    });
    await waitFor(() => {
      expect(container.textContent).not.toContain(CODE);
    });
  });
});
