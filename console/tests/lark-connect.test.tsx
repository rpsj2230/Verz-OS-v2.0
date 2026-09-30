/**
 * Connect Lark as a flow of screens, and Lark once it is connected.
 *
 * The flow: one step at a time with its picture, Back and Next keeping what was typed (the App
 * Secret included, which lives in its own field), the permissions pasted once from the API's text,
 * a test that sends somebody back to the step to redo with its picture, and the place kept when the
 * dialog is closed while the secret is not. The connected state: once anything is switched on the
 * Connectors screen shows Lark's card and offers adding a use, never Connect Lark again.
 *
 * The steps, the scopes and the verdicts are the API's; the stand-in here says which uses and
 * which App ID it was asked about, so a test can tell the console asked again when it should.
 *
 * Task ids: M11.9.4, M10.2.1, M27.11.9
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, test, vi } from "vitest";
import { FLAGGED } from "../src/components/kit";
import {
  guidePath,
  LARK_FLOW,
  skippedPages,
  skippedWords,
  type LarkGuide,
  type LarkStep,
  type LarkTested,
} from "../src/pages/larkConnectQuery";
import { SKIPPED_LABEL } from "../src/pages/connectors/WikiSpaces";
import { ACT_LABELS } from "../src/pages/connectors/connectorActions";
import { LARK_HEADING, switchOffLabel } from "../src/pages/connectors/LarkCard";
import {
  COPY_ALL,
  COPIED,
  goTo,
  LARK_EVENTS,
  SAVE_CHANNEL,
  SAVE_LARK,
  SECRET_SUPPLIED,
  TEST_CONNECTION,
  type LarkPlace,
} from "../src/pages/connectors/LarkFlow";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { backendModelFields } from "./support/python";
import { installRadixStubs } from "./support/radix";

const ORIGIN = "https://console.test";
const SECRET = "LARK-SECRET-SENTINEL-77aa";
const ENCRYPT_KEY = "LARK-ENCRYPT-SENTINEL-19bd";
const VERIFY_TOKEN = "LARK-VERIFY-SENTINEL-c04e";
const APP_ID = "cli_abcdef12";
const ROUTES = "src/brain/lark_connect_routes.py";
const EVENTS = {
  address: "https://brain.example.test/api/v1/channels/lark/events",
  switched_on: true,
  last_received: "2019-03-04T09:00:00Z",
  last_refused: null,
  refused_because: null,
  last_reply: "2019-03-04T09:00:02Z",
  reply_outcome: "sent",
  told: "Events are arriving. The last reply was sent.",
};

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/connectors/LarkFlow");
  await import("../src/pages/Connectors");
}, 60_000);

let clipboard: string[] = [];

/**
 * The flow's memory as the flow under test sees it. Signing in resets the module registry, so the
 * copy imported at the top of this file is not the one a flow mounted afterwards writes to.
 */
async function memory(): Promise<typeof import("../src/components/kit/flowMemory")> {
  return import("../src/components/kit/flowMemory");
}

beforeEach(() => {
  clipboard = [];
  GUIDE_EXTRA = {};
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: {
      writeText: vi.fn((text: string) => {
        clipboard.push(text);
        return Promise.resolve();
      }),
    },
  });
});

afterEach(async () => {
  (await memory()).forgetFlow(LARK_FLOW);
});

// ------------------------------------------------------------------------------ the answers

function use(name: string, label: string, on = false) {
  return {
    name,
    label,
    what: `${label}-WHAT`,
    scopes: [],
    switched_on: on,
    key_held: on ? true : null,
    status: on ? `${label}-ON` : "Not switched on.",
    may_switch_on: true,
  };
}

/** One step as the API sends it, its picture marking the menu entry named after it. */
function step(key: string, title: string, link = ""): LarkStep {
  return {
    key,
    title,
    text: `${title}-TEXT`,
    sketch: {
      place: "Lark developer console",
      heading: title,
      menu: ["Credentials & Basic Info", "Permissions & Scopes", "Version Management & Release"],
      menu_mark: key === "permissions" ? "Permissions & Scopes" : "",
      tabs: [],
      tab_mark: "",
      lines: [{ kind: "item", label: `${key}-ROW`, value: "", mark: true }],
      button: key === "permissions" ? "Batch import" : "",
    },
    link,
    link_label: link === "" ? "" : `Open ${title}`,
    asks: [],
    copy_text: "",
    copy_label: "",
  };
}

/** The steps the API builds for these uses, with the app's own pages once the App ID is known. */
function steps(chosen: readonly string[], appId: string): LarkStep[] {
  const page = (where: string) => (appId === "" ? "https://open.larksuite.com/app" : `https://open.larksuite.com/app/${appId}/${where}`);
  const found = [
    step("choose", "Choose what the Lark app is for"),
    step("create", "Create the app in Lark", "https://open.larksuite.com/app"),
    step("credentials", "Paste the App ID and App Secret", page("baseinfo")),
    step("permissions", "Add the permissions", page("auth")),
  ];
  if (chosen.includes("chat_channel")) {
    found.push(step("events_keys", "Copy the chat channel's two keys, then save it here", page("event")));
    found.push(step("events_address", "Point Lark's events at this install", page("event")));
  }
  found.push(step("release", "Release a version and have it approved", page("version")));
  found.push(step("test", "Test, then save"));
  if (chosen.includes("knowledge_wiki")) {
    found.push(step("wiki_spaces", "Say who may read each wiki space"));
  }
  if (chosen.includes("knowledge_base")) {
    found.push(step("base_access", "Grant each table to the people who may read it"));
  }
  return found;
}

function importText(chosen: readonly string[]): string {
  return JSON.stringify({ scopes: { tenant: chosen.map((one) => `scope-for-${one}`), user: [] } }, null, 2);
}

function guide(chosen: readonly string[], over: Partial<LarkGuide> = {}, appId = ""): LarkGuide {
  const on = over.uses === undefined ? [] : over.uses.filter((one) => one.switched_on).map((one) => one.name);
  return {
    uses: [
      use("staff_list", "Staff list", on.includes("staff_list")),
      use("knowledge_wiki", "Knowledge from Wiki", on.includes("knowledge_wiki")),
      use("knowledge_base", "Knowledge from Base", on.includes("knowledge_base")),
      use("chat_channel", "Chat channel", on.includes("chat_channel")),
    ],
    chosen: [...chosen],
    connected: false,
    app_id: appId,
    steps: steps(chosen, appId),
    // The API decides the scopes; this stand-in says which uses it was asked about.
    scopes: chosen.map((one) => ({ name: `scope-for-${one}`, what: "reads", read_only: true })),
    scope_import: importText(chosen),
    platforms: ["larksuite.com", "feishu.cn"],
    platform: "larksuite.com",
    base: "",
    developer_console: "https://open.larksuite.com/app",
    events_address: chosen.includes("chat_channel") ? EVENTS.address : "",
    channel_note: "CHANNEL-NOTE",
    events: chosen.includes("chat_channel") ? EVENTS : null,
    knowledge_note: "KNOWLEDGE-NOTE",
    test_note: "TEST-NOTE",
    staff_sources_screen: "/staff_sources",
    vault_told: "",
    last_test: null,
    switch_off_note: "SWITCH-OFF-NOTE",
    staff_off_note: "STAFF-OFF-NOTE",
    ...over,
  };
}

const TESTED: LarkTested = {
  accepted: true,
  told: "Lark accepted the App ID and App Secret.",
  redo: [],
  uses: [
    {
      name: "staff_list",
      label: "Staff list",
      verdict: "missing_scope",
      told: "Missing scope: contact:user.email:readonly.",
      missing: ["contact:user.email:readonly"],
      redo: ["permissions", "release"],
    },
  ],
};

/** A wiki test that saw one space, which the declaring step then offers. */
const WIKI_TESTED: LarkTested = {
  accepted: true,
  told: "Lark accepted the App ID and App Secret.",
  redo: [],
  uses: [
    {
      name: "knowledge_wiki",
      label: "Knowledge from Wiki",
      verdict: "working",
      told: "Working.",
      missing: [],
      redo: [],
      spaces: [{ space_id: "7000000000000000001", name: "Handbook" }],
    },
  ],
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

/** The stand-in API: the guide for the uses and App ID asked about, a test, a save, a switch off. */
/** Fields the stand-in guide carries beyond `guide()`'s, for a field the API adds later. */
let GUIDE_EXTRA: Readonly<Record<string, unknown>> = {};

function larkApi(connected: LarkGuide | null = null) {
  return (raw: string, init?: RequestInit): Response | null => {
    const url = new URL(raw, ORIGIN);
    if (url.pathname === "/api/v1/connectors/lark-app" && init?.method !== "POST") {
      if (connected !== null && url.searchParams.get("uses") === null) {
        return json(connected);
      }
      const asked = url.searchParams.get("uses");
      return json({
        ...guide(asked === null || asked === "none" ? [] : asked.split(","), {}, url.searchParams.get("app_id") ?? ""),
        ...GUIDE_EXTRA,
      });
    }
    if (url.pathname === "/api/v1/connectors/lark-app/test") {
      const sent = JSON.parse(String(init?.body)) as { uses: string[] };
      return json(sent.uses.includes("knowledge_wiki") ? WIKI_TESTED : TESTED);
    }
    if (url.pathname === "/api/v1/connectors/lark-app/wiki-spaces" && init?.method === "POST") {
      return json({ declared: ["7000000000000000001"], told: "SPACES-DECLARED" });
    }
    if (url.pathname === "/api/v1/connectors/lark-app/wiki-spaces") {
      return json({ spaces: [], may_declare: true, told: "SPACES-TOLD" });
    }
    if (url.pathname === "/api/v1/govern/departments") {
      return json({ items: [{ slug: "finance", name: "Finance", teams: [], members: [], lead: null, shapeable: false }] });
    }
    if (url.pathname === "/api/v1/connectors/lark-app/switch-off") {
      return json({ switched_off: ["knowledge_wiki"], told: "SWITCHED-OFF" });
    }
    if (url.pathname === "/api/v1/connectors/lark-app" && init?.method === "POST") {
      return json({ switched_on: ["staff_list"], told: "SAVED", staff_sources_screen: "/staff_sources" });
    }
    return null;
  };
}

// ------------------------------------------------------------------------------ mounting

interface Flow {
  readonly idp: FakeIdp;
  readonly done: string[];
  readonly unmount: () => void;
}

async function openFlow(start?: { at?: string; add?: string[] }): Promise<Flow> {
  const idp = fakeIdentityProvider({ api: larkApi() });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  return mountFlow(idp, start);
}

async function mountFlow(idp: FakeIdp, start?: { at?: string; add?: string[] }): Promise<Flow> {
  const { LarkFlow } = await import("../src/pages/connectors/LarkFlow");
  const done: string[] = [];
  const router = createMemoryRouter(
    [
      {
        path: "/connectors",
        element: (
          <LarkFlow
            start={start}
            onClose={() => undefined}
            onDone={(told) => {
              done.push(told);
            }}
          />
        ),
      },
    ],
    { initialEntries: ["/connectors"] },
  );
  const { unmount } = render(<RouterProvider router={router} />);
  await screen.findByText(/^Step \d+ of \d+$/);
  return { idp, done, unmount };
}

function posts(idp: FakeIdp): { path: string; body: Record<string, unknown> }[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST" && new URL(call.url, ORIGIN).pathname.startsWith("/api/"))
    .map((call) => ({
      path: new URL(call.url, ORIGIN).pathname,
      body: JSON.parse(String(call.init?.body)) as Record<string, unknown>,
    }));
}

function guideAsks(idp: FakeIdp): URL[] {
  return idp.calls
    .map((call) => new URL(call.url, ORIGIN))
    .filter((url) => url.pathname === "/api/v1/connectors/lark-app" && url.search !== "");
}

function stepLine(): string {
  return screen.getByText(/^Step \d+ of \d+$/).textContent ?? "";
}

function next(): void {
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
}

function back(): void {
  fireEvent.click(screen.getByRole("button", { name: "Back" }));
}

function field(id: string): HTMLInputElement {
  const found = document.getElementById(id);
  if (!(found instanceof HTMLInputElement)) {
    throw new Error(`no field ${id}`);
  }
  return found;
}

function type(id: string, value: string): void {
  // The secret fields are the kit's masked field, which hears an input event rather than a change.
  fireEvent.input(field(id), { target: { value } });
  fireEvent.change(field(id), { target: { value } });
}

async function tick(label: string): Promise<void> {
  const box = screen.getByRole("checkbox", { name: new RegExp(label) });
  fireEvent.click(box);
  await waitFor(() => {
    expect((screen.getByRole("checkbox", { name: new RegExp(label) }) as HTMLInputElement).checked).toBe(true);
  });
}

/** From the first step to the test step with the staff list chosen and the credentials typed. */
async function toTheTest(): Promise<Flow> {
  const flow = await openFlow();
  await tick("Staff list");
  next();
  next();
  type("connect-lark-app_id", APP_ID);
  type("connect-lark-app_secret", SECRET);
  next();
  await waitFor(() => {
    expect(screen.getByRole("heading", { name: "Add the permissions" })).toBeTruthy();
  });
  next();
  next();
  await waitFor(() => {
    expect(stepLine()).toBe("Step 6 of 6");
  });
  return flow;
}

// ------------------------------------------------------------------------------ the tests

describe("what the flow agrees with the API about", () => {
  test("every field the API sends about the guide and a step is a field this console types", () => {
    // What breaks if this is deleted: a field added to the guide or a step arrives and nothing draws it.
    expect(backendModelFields(ROUTES, "LarkView").sort()).toEqual(Object.keys(guide([])).sort());
    expect(backendModelFields("src/brain/guide_views.py", "GuideStepView").sort()).toEqual(Object.keys(step("x", "X")).sort());
    expect(backendModelFields("src/brain/guide_views.py", "SketchView").sort()).toEqual(Object.keys(step("x", "X").sketch).sort());
  });

  test("the guide is asked for the uses chosen, none spelled as none, and the App ID once typed", () => {
    // What breaks if this is deleted: unticking every use shows whatever is switched on instead, or
    // the steps never learn the App ID their links are built from.
    expect(guidePath(null, "")).toBe("/connectors/lark-app");
    expect(guidePath([], "")).toBe("/connectors/lark-app?uses=none");
    expect(guidePath(["staff_list", "knowledge_wiki"], "feishu.cn", ` ${APP_ID} `)).toBe(
      `/connectors/lark-app?uses=staff_list%2Cknowledge_wiki&platform=feishu.cn&app_id=${APP_ID}`,
    );
  });
});

describe("the flow", () => {
  test("shows one step at a time with its picture, and Back and Next keep what was typed", async () => {
    // What breaks if this is deleted: the steps collapse back into one long list, a step loses its
    // picture, or pressing Next and Back empties the App Secret somebody pasted.
    const { idp } = await openFlow();
    expect(stepLine()).toBe("Step 1 of 6");
    expect(screen.getByRole("img", { name: /A picture of the screen/ })).toBeTruthy();
    await tick("Staff list");
    next();
    expect(screen.getByRole("heading", { name: "Create the app in Lark" })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Open Create the app in Lark/ }).getAttribute("target")).toBe("_blank");
    next();
    type("connect-lark-app_id", APP_ID);
    type("connect-lark-app_secret", SECRET);
    next();
    await waitFor(() => {
      expect(stepLine()).toBe("Step 4 of 6");
    });
    // The App ID left its field when Next was pressed, and the steps now open the app's own pages.
    await waitFor(() => {
      expect(guideAsks(idp).some((url) => url.searchParams.get("app_id") === APP_ID)).toBe(true);
    });
    await waitFor(() => {
      expect(screen.getByRole("link", { name: /Open Add the permissions/ }).getAttribute("href")).toBe(
        `https://open.larksuite.com/app/${APP_ID}/auth`,
      );
    });
    expect(field("connect-lark-app_id").closest("[hidden]")).not.toBeNull();
    back();
    expect(stepLine()).toBe("Step 3 of 6");
    expect(field("connect-lark-app_id").value).toBe(APP_ID);
    expect(field("connect-lark-app_secret").value).toBe(SECRET);
    expect(field("connect-lark-app_id").closest("[hidden]")).toBeNull();
  });

  test("copy all puts the API's permissions text on the clipboard, and the one-by-one list stays", async () => {
    // What breaks if this is deleted: the administrator adds each permission by hand again, or the
    // pasted text drifts from the list the test checks.
    await openFlow({ at: "choose", add: ["staff_list", "knowledge_wiki"] });
    await waitFor(() => {
      expect(stepLine()).toBe("Step 1 of 7");
    });
    fireEvent.click(screen.getByRole("button", { name: /Step 4 of 7/ }));
    fireEvent.click(screen.getByRole("button", { name: COPY_ALL }));
    await waitFor(() => {
      expect(screen.getByText(COPIED)).toBeTruthy();
    });
    expect(clipboard).toEqual([importText(["staff_list", "knowledge_wiki"])]);
    const list = screen.getByRole("list", { name: "Permissions to add" });
    expect(within(list).getAllByRole("listitem").map((one) => one.querySelector("code")?.textContent)).toEqual([
      "scope-for-staff_list",
      "scope-for-knowledge_wiki",
    ]);
  });

  test("a missing permission sends the administrator to the permissions step with its picture, then the release", async () => {
    // What breaks if this is deleted: the test says a use failed and leaves the person to work out
    // which screen in Lark to go back to, or never says a permission needs a new version released.
    const { idp } = await toTheTest();
    fireEvent.click(screen.getByRole("button", { name: TEST_CONNECTION }));
    await waitFor(() => {
      expect(screen.getByRole("region", { name: "Test results" })).toBeTruthy();
    });
    expect(posts(idp).map((one) => one.path)).toEqual(["/api/v1/connectors/lark-app/test"]);
    expect(posts(idp)[0]?.body).toMatchObject({ app_id: APP_ID, app_secret: SECRET, uses: ["staff_list"] });
    const results = screen.getByRole("region", { name: "Test results" });
    expect(within(results).getByRole("list", { name: "Permissions to add for Staff list" }).textContent).toBe(
      "contact:user.email:readonly",
    );
    const redo = within(results).getByRole("list", { name: "Steps to go back to" });
    expect(within(redo).getAllByRole("img").length).toBe(2);
    expect(within(redo).getByRole("button", { name: goTo(4) })).toBeTruthy();
    expect(within(redo).getByRole("button", { name: goTo(5) })).toBeTruthy();
    expect(screen.getByRole("button", { name: new RegExp(`Step 4 of 6: Add the permissions. ${FLAGGED}`) })).toBeTruthy();
    fireEvent.click(within(redo).getByRole("button", { name: goTo(4) }));
    expect(stepLine()).toBe("Step 4 of 6");
    expect(screen.getByRole("heading", { name: "Add the permissions" })).toBeTruthy();
  });

  test("closing keeps the step and the App ID, and never the App Secret", async () => {
    // What breaks if this is deleted: somebody who closes the dialog to work in Lark starts again
    // from the first step, or the secret outlives the dialog it was typed into.
    const flow = await openFlow();
    await tick("Staff list");
    next();
    next();
    type("connect-lark-app_id", APP_ID);
    type("connect-lark-app_secret", SECRET);
    flow.unmount();
    const kept = (await memory()).recallFlow<LarkPlace>(LARK_FLOW);
    expect(kept).toMatchObject({ at: "credentials", uses: ["staff_list"], appId: APP_ID });
    expect(JSON.stringify(kept)).not.toContain(SECRET);
    await mountFlow(flow.idp);
    expect(stepLine()).toBe("Step 3 of 6");
    expect(field("connect-lark-app_id").value).toBe(APP_ID);
    expect(field("connect-lark-app_secret").value).toBe("");
  });

  test("a save is confirmed without the secret, sends it once, and forgets the place", async () => {
    // What breaks if this is deleted: the secret can be drawn on the confirmation or left in the
    // page after it was kept, or a finished flow reopens half way.
    const { idp, done } = await toTheTest();
    fireEvent.click(screen.getByRole("button", { name: SAVE_LARK }));
    const confirm = await screen.findByRole("alertdialog");
    expect(confirm.textContent).toContain(SECRET_SUPPLIED);
    expect(confirm.textContent).not.toContain(SECRET);
    expect(posts(idp)).toEqual([]);
    await act(async () => {
      fireEvent.click(within(confirm).getByRole("button", { name: SAVE_LARK }));
    });
    await waitFor(() => {
      expect(done).toEqual(["SAVED"]);
    });
    expect(posts(idp).map((one) => one.path)).toEqual(["/api/v1/connectors/lark-app"]);
    expect(posts(idp)[0]?.body).toMatchObject({ app_secret: SECRET, uses: ["staff_list"] });
    expect(field("connect-lark-app_secret").value).toBe("");
    expect((await memory()).recallFlow(LARK_FLOW)).toBeUndefined();
  });

  test("the chat channel is saved early with only itself, and its keys stay for the final save", async () => {
    // What breaks if this is deleted: Lark checks the events address before the install can answer,
    // or the early save empties the keys the final save needs.
    const { idp } = await openFlow({ at: "choose", add: ["chat_channel"] });
    await waitFor(() => {
      expect(stepLine()).toBe("Step 1 of 8");
    });
    fireEvent.click(screen.getByRole("button", { name: /Step 3 of 8/ }));
    type("connect-lark-app_id", APP_ID);
    type("connect-lark-app_secret", SECRET);
    fireEvent.click(screen.getByRole("button", { name: /Step 5 of 8/ }));
    type("connect-lark-encrypt_key", ENCRYPT_KEY);
    type("connect-lark-verification_token", VERIFY_TOKEN);
    fireEvent.click(screen.getByRole("button", { name: SAVE_CHANNEL }));
    const confirm = await screen.findByRole("alertdialog");
    expect(confirm.textContent).not.toContain(ENCRYPT_KEY);
    await act(async () => {
      fireEvent.click(within(confirm).getByRole("button", { name: SAVE_CHANNEL }));
    });
    await waitFor(() => {
      expect(posts(idp).map((one) => one.path)).toEqual(["/api/v1/connectors/lark-app"]);
    });
    expect(posts(idp)[0]?.body).toMatchObject({
      uses: ["chat_channel"],
      encrypt_key: ENCRYPT_KEY,
      verification_token: VERIFY_TOKEN,
    });
    expect(field("connect-lark-encrypt_key").value).toBe(ENCRYPT_KEY);
    next();
    const events = screen.getByRole("region", { name: LARK_EVENTS });
    expect(within(events).getByRole("status").textContent).toBe(EVENTS.told);
    expect(document.body.textContent).toContain(EVENTS.address);
  });
});

describe("Lark once it is connected", () => {
  const WIKI_ON: LarkGuide = guide(["knowledge_wiki"], {
    connected: true,
    uses: [use("staff_list", "Staff list"), use("knowledge_wiki", "Knowledge from Wiki", true), use("knowledge_base", "Knowledge from Base"), use("chat_channel", "Chat channel")],
    last_test: {
      at: "2019-03-04T09:00:00Z",
      accepted: true,
      uses: [{ name: "knowledge_wiki", label: "Knowledge from Wiki", verdict: "working" }],
    },
    app_id: APP_ID,
  });

  const LIST = {
    items: [
      {
        name: "lark_wiki",
        label: "Lark Wiki",
        status: "connected",
        health: null,
        department: null,
        last_read_at: null,
        connected_at: null,
        declaration_changed: false,
        connect_from: "lark",
        may_manage: false,
      },
    ],
    next_cursor: null,
    total: null,
  };

  async function connectorsPage(lark: LarkGuide): Promise<FakeIdp> {
    const api = larkApi(lark);
    const idp = fakeIdentityProvider({
      api(raw, init) {
        const pathname = new URL(raw, ORIGIN).pathname;
        if (pathname === "/api/v1/console/connectors") {
          return json(LIST);
        }
        if (pathname === "/api/v1/connectors" && init?.method !== "POST") {
          return json({
            connectors: [],
            unread: "",
            connecting: "",
            confirm_connect: "",
            confirm_disconnect: "",
            copy_policy: [],
            budget_unread: "",
            may_connect: true,
            vault: "ready",
            vault_told: "",
            connectable: [],
            not_connectable: [],
            evidence: [],
            key_max_chars: 1000,
            key_blank: "",
          });
        }
        return api(raw, init);
      },
    });
    const loaded = await loadConsole({ idp });
    await signIn(loaded);
    const { routes } = await import("../src/App");
    const router = createMemoryRouter(routes, { initialEntries: ["/connectors"] });
    render(<RouterProvider router={router} />);
    await screen.findByRole("heading", { level: 1 });
    return idp;
  }

  test("the card replaces Connect Lark, says what is on and when it was tested, and offers adding a use", async () => {
    // What breaks if this is deleted: the owner's finding comes back, Connect Lark offered and
    // opening the setup again after Lark was connected.
    await connectorsPage(WIKI_ON);
    const card = await screen.findByRole("region", { name: LARK_HEADING });
    expect(within(card).getByRole("list", { name: "Switched on" }).textContent).toContain("Knowledge from Wiki");
    expect(card.textContent).toContain("Knowledge from Wiki: Working");
    expect(screen.queryByRole("button", { name: ACT_LABELS.connectLark })).toBeNull();
    expect(screen.getByRole("button", { name: ACT_LABELS.addLarkUse })).toBeTruthy();
  });

  test("with nothing switched on there is no card and Connect Lark is offered", async () => {
    // What breaks if this is deleted: a fresh install has no way into the flow, or draws an empty card.
    await connectorsPage(guide([]));
    await screen.findByRole("button", { name: ACT_LABELS.connectLark });
    expect(screen.queryByRole("region", { name: LARK_HEADING })).toBeNull();
  });

  test("switching a use off is confirmed in the API's words and sends only that use", async () => {
    // What breaks if this is deleted: Disconnect is one press, or switches off more than was chosen.
    const idp = await connectorsPage(WIKI_ON);
    const card = await screen.findByRole("region", { name: LARK_HEADING });
    const trigger = within(card).getByRole("button", { name: "Manage Lark" });
    trigger.focus();
    await act(async () => {
      fireEvent.keyDown(trigger, { key: "Enter" });
    });
    const menu = await screen.findByRole("menu");
    await act(async () => {
      fireEvent.click(within(menu).getByRole("menuitem", { name: switchOffLabel("Knowledge from Wiki") }));
    });
    const confirm = await screen.findByRole("alertdialog");
    expect(confirm.textContent).toContain("SWITCH-OFF-NOTE");
    expect(posts(idp)).toEqual([]);
    await act(async () => {
      fireEvent.click(within(confirm).getByRole("button", { name: "Switch off" }));
    });
    await waitFor(() => {
      expect(posts(idp)).toEqual([{ path: "/api/v1/connectors/lark-app/switch-off", body: { uses: ["knowledge_wiki"] } }]);
    });
  });
});

describe("the knowledge steps", () => {
  test("the wiki's step offers the spaces the test saw and declares the one given a reach, confirmed", async () => {
    // What breaks if this is deleted: a wiki is switched on and no space is ever declared, so the
    // Brain answers from none, or a space is declared at a reach nobody confirmed.
    const { idp } = await openFlow({ at: "choose", add: ["knowledge_wiki"] });
    await waitFor(() => {
      expect(stepLine()).toBe("Step 1 of 7");
    });
    fireEvent.click(screen.getByRole("button", { name: /Step 3 of 7/ }));
    type("connect-lark-app_id", APP_ID);
    type("connect-lark-app_secret", SECRET);
    fireEvent.click(screen.getByRole("button", { name: /Step 6 of 7/ }));
    fireEvent.click(screen.getByRole("button", { name: TEST_CONNECTION }));
    await waitFor(() => {
      expect(screen.getByRole("region", { name: "Test results" })).toBeTruthy();
    });
    fireEvent.click(screen.getByRole("button", { name: /Step 7 of 7/ }));
    const handbook = await screen.findByLabelText("Handbook");
    fireEvent.change(handbook, { target: { value: "company" } });
    fireEvent.click(screen.getByRole("button", { name: "Save the spaces" }));
    const confirm = await screen.findByRole("alertdialog");
    expect(confirm.textContent).toContain("Handbook");
    expect(posts(idp).map((one) => one.path)).toEqual(["/api/v1/connectors/lark-app/test"]);
    await act(async () => {
      fireEvent.click(within(confirm).getByRole("button", { name: "Save the spaces" }));
    });
    await waitFor(() => {
      expect(posts(idp).map((one) => one.path)).toContain("/api/v1/connectors/lark-app/wiki-spaces");
    });
    expect(posts(idp).find((one) => one.path.endsWith("/wiki-spaces"))?.body).toEqual({
      spaces: [{ space: "7000000000000000001", reach: "company", department: "" }],
    });
    await screen.findByText("SPACES-DECLARED");
  });

  test("the Base's last step says its tables are granted per table and links to where", async () => {
    // What breaks if this is deleted: a Base is indexed and the administrator is never told that
    // nobody reads a table until they are granted it, or where to grant it.
    await openFlow({ at: "choose", add: ["knowledge_base"] });
    await waitFor(() => {
      expect(stepLine()).toBe("Step 1 of 7");
    });
    fireEvent.click(screen.getByRole("button", { name: /Step 7 of 7/ }));
    expect(screen.getByRole("heading", { name: "Grant each table to the people who may read it" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open Capabilities" }).getAttribute("href")).toBe("/capabilities");
    expect(screen.getByRole("link", { name: "Open People" }).getAttribute("href")).toBe("/people");
  });
});

describe("wiki pages a question matched and did not read", () => {
  const NOTE = "SKIPPED-NOTE: restricted in Lark, settings unreadable, or the space undeclared.";

  async function wikiStep(): Promise<void> {
    await openFlow({ at: "choose", add: ["knowledge_wiki"] });
    await waitFor(() => {
      expect(stepLine()).toBe("Step 1 of 7");
    });
    fireEvent.click(screen.getByRole("button", { name: /Step 7 of 7/ }));
    await screen.findByRole("heading", { name: "Say who may read each wiki space" });
  }

  test("an administrator is told how many matched pages were not read, and why, and no page by name", async () => {
    // What breaks if this is deleted: an administrator never learns that questions are meeting
    // pages the Brain may not read, which looks exactly like a wiki with nothing on the subject.
    GUIDE_EXTRA = { wiki_pages_skipped: 12, wiki_pages_skipped_note: NOTE };
    await wikiStep();
    const skipped = await screen.findByRole("region", { name: SKIPPED_LABEL });
    expect(skipped.textContent).toBe(`${skippedWords(12)}${NOTE}`);
    expect(skippedWords(12)).toBe("12 wiki pages questions matched were not read.");
    expect(skippedWords(1)).toBe("1 wiki page a question matched was not read.");
  });

  test("nothing is shown when the API sends no count, or nought", async () => {
    // What breaks if this is deleted: a reader the API sends no count to is shown a line anyway,
    // or a zero is drawn as if something had been withheld.
    GUIDE_EXTRA = { wiki_pages_skipped: null, wiki_pages_skipped_note: NOTE };
    await wikiStep();
    expect(screen.queryByRole("region", { name: SKIPPED_LABEL })).toBeNull();
    expect(document.body.textContent).not.toContain("SKIPPED-NOTE");
    expect(skippedPages({ ...guide([]), wiki_pages_skipped: 0, wiki_pages_skipped_note: NOTE } as LarkGuide)).toBeNull();
    expect(skippedPages(guide([]))).toBeNull();
  });
});
