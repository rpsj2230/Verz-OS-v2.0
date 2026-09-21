/**
 * Connect Lark on the Connectors screen: the steps and scopes are the API's, a test shows each
 * use's verdict with the missing scope named, and a save is confirmed and never shows the secret.
 *
 * Task ids: M11.9.4
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  CONNECT_LARK,
  SAVE_LARK,
  SCOPES_TO_ADD,
  SECRET_SUPPLIED,
  STAFF_SOURCES_LINK,
  TEST_CONNECTION,
} from "../src/components/ConnectLark";
import { guidePath, type LarkGuide, type LarkTested } from "../src/pages/larkConnectQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { backendModelFields } from "./support/python";

const ORIGIN = "https://console.test";
const SECRET = "LARK-SECRET-SENTINEL-77aa";
const ROUTES = "src/brain/lark_connect_routes.py";

beforeAll(async () => {
  await import("../src/components/ConnectLark");
}, 60_000);

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

function guide(chosen: string[]): LarkGuide {
  return {
    uses: [
      use("staff_list", "Staff list"),
      use("knowledge_wiki", "Knowledge from Wiki"),
      use("knowledge_base", "Knowledge from Base"),
      use("chat_channel", "Chat channel"),
    ],
    chosen,
    steps: [{ title: "Create the app", text: "Click Create Custom App." }],
    // The API decides the scopes; this stand-in says which uses it was asked about.
    scopes: chosen.map((one) => ({ name: `scope-for-${one}`, what: "reads", read_only: true })),
    platforms: ["larksuite.com", "feishu.cn"],
    platform: "larksuite.com",
    base: "",
    developer_console: "https://open.larksuite.com/app",
    events_address: "",
    channel_note: "CHANNEL-NOTE",
    knowledge_note: "KNOWLEDGE-NOTE",
    test_note: "TEST-NOTE",
    staff_sources_screen: "/staff_sources",
    vault_told: "",
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

const TESTED: LarkTested = {
  accepted: true,
  told: "Lark accepted the App ID and App Secret.",
  uses: [
    {
      name: "staff_list",
      label: "Staff list",
      verdict: "missing_scope",
      told: "Missing scope: contact:user.email:readonly.",
      missing: ["contact:user.email:readonly"],
    },
  ],
};

async function mount(): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(raw, init) {
      const url = new URL(raw, ORIGIN);
      if (url.pathname === "/api/v1/connectors/lark-app" && init?.method !== "POST") {
        const asked = url.searchParams.get("uses");
        return json(guide(asked === null || asked === "none" ? [] : asked.split(",")));
      }
      if (url.pathname === "/api/v1/connectors/lark-app/test") {
        return json(TESTED);
      }
      if (url.pathname === "/api/v1/connectors/lark-app" && init?.method === "POST") {
        return json({ switched_on: ["staff_list"], told: "SAVED", staff_sources_screen: "/staff_sources" });
      }
      return null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { ConnectLark } = await import("../src/components/ConnectLark");
  const router = createMemoryRouter([{ path: "/connectors", element: <ConnectLark /> }], {
    initialEntries: ["/connectors"],
  });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.textContent?.includes("Create Custom App")) {
      throw new Error("still reading");
    }
  });
  return { container, idp };
}

function posts(idp: FakeIdp): { path: string; body: Record<string, unknown> }[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST" && new URL(call.url, ORIGIN).pathname.startsWith("/api/"))
    .map((call) => ({
      path: new URL(call.url, ORIGIN).pathname,
      body: JSON.parse(String(call.init?.body)) as Record<string, unknown>,
    }));
}

function button(scope: ParentNode, name: string): HTMLButtonElement {
  const found = [...scope.querySelectorAll("button")].find((one) => one.textContent === name);
  if (!found) {
    throw new Error(`no button ${name}`);
  }
  return found as HTMLButtonElement;
}

function checkbox(container: HTMLElement, label: string): HTMLInputElement {
  const found = [...container.querySelectorAll("label")].find((one) => one.textContent?.includes(label));
  const box = found?.querySelector("input");
  if (!box) {
    throw new Error(`no checkbox ${label}`);
  }
  return box;
}

describe("Connect Lark", () => {
  test("every field the API sends about the guide is a field this console types", () => {
    // What breaks if this is deleted: a field added to the guide arrives and nothing draws it.
    expect(backendModelFields(ROUTES, "LarkView").sort()).toEqual(Object.keys(guide([])).sort());
  });

  test("the guide asks the API for the uses chosen, and none spelled as none", () => {
    // What breaks if this is deleted: unticking every use shows whatever is switched on instead.
    expect(guidePath(null, "")).toBe("/connectors/lark-app");
    expect(guidePath([], "")).toBe("/connectors/lark-app?uses=none");
    expect(guidePath(["staff_list", "knowledge_wiki"], "feishu.cn")).toBe(
      "/connectors/lark-app?uses=staff_list%2Cknowledge_wiki&platform=feishu.cn",
    );
  });

  test("choosing a use draws the scopes the API answers for it, and keeps what was typed", async () => {
    // What breaks if this is deleted: the scope list stops following the choice, or a choice
    // wipes the App ID somebody had already pasted.
    const { container } = await mount();
    expect(container.textContent).toContain(CONNECT_LARK);
    // A blank form cannot be sent: both buttons wait for an App ID and an App Secret.
    expect(button(container, TEST_CONNECTION).disabled).toBe(true);
    expect(button(container, SAVE_LARK).disabled).toBe(true);
    fireEvent.change(container.querySelector("#connect-lark-app_id") as HTMLInputElement, {
      target: { value: "cli_abcdef" },
    });
    fireEvent.click(checkbox(container, "Knowledge from Wiki"));
    await waitFor(() => {
      expect(container.querySelector(`[aria-label='${SCOPES_TO_ADD}']`)?.textContent).toContain(
        "scope-for-knowledge_wiki",
      );
    });
    expect((container.querySelector("#connect-lark-app_id") as HTMLInputElement).value).toBe("cli_abcdef");
  });

  test("a test sends the credential and draws each use's verdict with the missing scope named", async () => {
    // What breaks if this is deleted: the person is told a use failed without being told which
    // scope to add.
    const { container, idp } = await mount();
    fireEvent.click(checkbox(container, "Staff list"));
    await waitFor(() => {
      expect(container.textContent).toContain("scope-for-staff_list");
    });
    fireEvent.change(container.querySelector("#connect-lark-app_id") as HTMLInputElement, {
      target: { value: "cli_abcdef" },
    });
    fireEvent.change(container.querySelector("#connect-lark-app_secret") as HTMLInputElement, {
      target: { value: SECRET },
    });
    fireEvent.click(button(container, TEST_CONNECTION));
    await waitFor(() => {
      expect(container.textContent).toContain("Missing scope");
    });
    expect(container.querySelector("[aria-label='Scopes to add for Staff list']")?.textContent).toBe(
      "contact:user.email:readonly",
    );
    const sent = posts(idp);
    expect(sent.map((one) => one.path)).toEqual(["/api/v1/connectors/lark-app/test"]);
    expect(sent[0]?.body).toMatchObject({ app_id: "cli_abcdef", app_secret: SECRET, uses: ["staff_list"] });
  });

  test("a save is confirmed without showing the secret, clears it, and links to Staff sources", async () => {
    // What breaks if this is deleted: the secret can be drawn on the confirmation or left in the
    // page after it was kept, or the staff list is switched on with nowhere to see its runs.
    const { container, idp } = await mount();
    fireEvent.click(checkbox(container, "Staff list"));
    await waitFor(() => {
      expect(container.textContent).toContain("scope-for-staff_list");
    });
    fireEvent.change(container.querySelector("#connect-lark-app_id") as HTMLInputElement, {
      target: { value: "cli_abcdef" },
    });
    fireEvent.change(container.querySelector("#connect-lark-app_secret") as HTMLInputElement, {
      target: { value: SECRET },
    });
    fireEvent.click(button(container, SAVE_LARK));
    const confirm = container.querySelector(".confirm") as HTMLElement;
    expect(confirm.textContent).toContain(SECRET_SUPPLIED);
    expect(confirm.textContent).not.toContain(SECRET);
    expect(posts(idp)).toEqual([]);
    fireEvent.click(button(confirm, SAVE_LARK));
    await waitFor(() => {
      expect(container.textContent).toContain(STAFF_SOURCES_LINK);
    });
    expect(posts(idp).map((one) => one.path)).toEqual(["/api/v1/connectors/lark-app"]);
    expect(container.innerHTML).not.toContain(SECRET);
  });
});
