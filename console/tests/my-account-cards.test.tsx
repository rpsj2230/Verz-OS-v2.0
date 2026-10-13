/**
 * The account cards in My workspace: where the person is signed in, who read their record, what
 * agents made for them and what is kept about them.
 *
 * Mounted on their own, for the reason `tests/my-workspace-page.test.tsx` gives. The failures worth
 * testing look like the page working: a sign-out offered on the sign-in being used, one sent with no
 * second step, and a list of reads that carries what was shown.
 *
 * Task ids: M40.1.1.3, M40.4.2.4, M40.3.3.1, M40.4.2.1
 */

import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  END_DEVICE_CONSEQUENCE,
  END_DEVICE_LABEL,
  KEEP_DEVICE_LABEL,
  NO_READS,
} from "../src/components/MyAccountCards";
import { END_MY_DEVICE_API_PATH } from "../src/pages/myAccountQuery";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";

const ORIGIN = "https://console.test";

beforeAll(async () => {
  await import("../src/components/MyAccountCards");
}, 60_000);

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

const DEVICES = {
  devices: [
    {
      session_id: "s_here",
      channel: "console",
      second_factor: true,
      started_at: "2019-03-01T10:00:00Z",
      expires_at: "2019-03-01T18:00:00Z",
      is_this_one: true,
    },
    {
      session_id: "s_there",
      channel: "console",
      second_factor: false,
      started_at: "2019-03-01T09:00:00Z",
      expires_at: "2019-03-01T17:00:00Z",
      is_this_one: false,
    },
  ],
  more: false,
};

async function mount(
  which: "MyDevices" | "MyReads",
  onPost: (path: string, body: unknown) => Response = () => json({}),
  reads: unknown = { reads: [], more: false },
) {
  const sent: { path: string; body: unknown }[] = [];
  const idp = fakeIdentityProvider({
    api(url, init) {
      const path = new URL(url, ORIGIN).pathname;
      if ((init?.method ?? "GET").toUpperCase() === "POST") {
        const body = typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : null;
        sent.push({ path, body });
        return onPost(path, body);
      }
      if (path === "/api/v1/me/devices") return json(DEVICES);
      if (path === "/api/v1/me/reads") return json(reads);
      return null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const module = await import("../src/components/MyAccountCards");
  const Card = module[which];
  const { container } = render(<Card />);
  return { container, sent };
}

function buttonNamed(root: ParentNode, name: string): HTMLButtonElement {
  const found = [...root.querySelectorAll("button")].find(
    (one) => one.textContent?.trim() === name || one.getAttribute("aria-label") === name,
  );
  if (!found) throw new Error(`no button ${name}`);
  return found;
}

describe("where I am signed in", () => {
  test("the sign-in being used has no sign-out and the other is confirmed before anything is sent", async () => {
    // What breaks if this is deleted: a person signs themselves out from the page they are using,
    // or a sign-out goes with no second step, or one names a sign-in that is not the one chosen.
    const { container, sent } = await mount("MyDevices");
    await waitFor(() => {
      expect(container.textContent).toContain("until");
    });
    expect(container.querySelectorAll("button").length).toBe(1);
    fireEvent.click(buttonNamed(container, `${END_DEVICE_LABEL}: s_there`));
    expect(container.textContent).toContain(END_DEVICE_CONSEQUENCE);
    fireEvent.click(buttonNamed(container, KEEP_DEVICE_LABEL));
    expect(sent).toEqual([]);
    fireEvent.click(buttonNamed(container, `${END_DEVICE_LABEL}: s_there`));
    fireEvent.click(buttonNamed(container, END_DEVICE_LABEL));
    await waitFor(() => {
      expect(sent).toEqual([{ path: `/api/v1${END_MY_DEVICE_API_PATH}`, body: { session_id: "s_there" } }]);
    });
  });
});

describe("who has read my record", () => {
  test("a read is drawn as who, when, through which agent and what kind, and an empty list says so", async () => {
    // What breaks if this is deleted: a read that is drawn with something it was shown, or an
    // empty list that draws nothing and reads as a page that failed.
    const empty = await mount("MyReads");
    await waitFor(() => {
      expect(empty.container.textContent).toContain(NO_READS);
    });
    const some = await mount("MyReads", undefined, {
      reads: [
        { at: "2019-03-01T09:00:00Z", actor_id: "u_hr", agent_id: "a_hr", record_kind: "personnel" },
      ],
      more: false,
    });
    await waitFor(() => {
      expect(some.container.textContent).toContain("u_hr, through a_hr, personnel.");
    });
  });
});


describe("sharing a file with a colleague", () => {
  test("a share sends the colleague's id and nothing else, for the file chosen, and an empty box sends nothing", async () => {
    // What breaks if this is deleted: a share that names the wrong file, sends a name with
    // whitespace the API refuses, or goes with no colleague typed.
    const sent: { path: string; body: unknown }[] = [];
    const idp = fakeIdentityProvider({
      api(url, init) {
        const path = new URL(url, ORIGIN).pathname;
        if ((init?.method ?? "GET").toUpperCase() === "POST") {
          sent.push({ path, body: typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : null });
          return json({});
        }
        return path === "/api/v1/me/artifacts"
          ? json({
              artifacts: [
                {
                  artifact_id: "art_1",
                  kind: "report",
                  agent_id: "a_one",
                  produced_for: "u_me",
                  produced_at: "2019-03-01T09:00:00Z",
                  state: "current",
                  superseded_by: "",
                  run_id: "r",
                  agent_version: "1",
                  kept_as: "x",
                  kept_until: "",
                  kept_because: "kept",
                },
              ],
              more: false,
            })
          : null;
      },
    });
    const loaded = await loadConsole({ idp });
    await signIn(loaded);
    const { MyArtifacts } = await import("../src/components/MyAccountCards");
    const { container } = render(<MyArtifacts />);
    await waitFor(() => {
      expect(container.textContent).toContain("report by a_one");
    });
    const share = buttonNamed(container, "Share: art_1");
    expect(share.disabled).toBe(true);
    fireEvent.change(container.querySelector("input") as HTMLInputElement, { target: { value: "  u_friend " } });
    fireEvent.click(buttonNamed(container, "Share: art_1"));
    await waitFor(() => {
      expect(sent).toEqual([{ path: "/api/v1/me/artifacts/art_1/share", body: { colleague: "u_friend" } }]);
    });
  });
});

describe("asking for an agent", () => {
  test("an agent already asked for shows as asked and has no button, and asking sends nothing but the agent", async () => {
    // What breaks if this is deleted: a second ask offered for an agent already asked for, or an
    // ask that sends a body naming somebody.
    const sent: { path: string; body: unknown }[] = [];
    const idp = fakeIdentityProvider({
      api(url, init) {
        const path = new URL(url, ORIGIN).pathname;
        if ((init?.method ?? "GET").toUpperCase() === "POST") {
          sent.push({ path, body: typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : null });
          return json({});
        }
        return path === "/api/v1/me/agents/requestable"
          ? json({
              agents: [
                { agent_id: "a_new", display_name: "Quoting", asked: false },
                { agent_id: "a_old", display_name: "Billing", asked: true },
              ],
            })
          : null;
      },
    });
    const loaded = await loadConsole({ idp });
    await signIn(loaded);
    const { MyRequestableAgents } = await import("../src/components/MyAccountCards");
    const { container } = render(<MyRequestableAgents />);
    await waitFor(() => {
      expect(container.textContent).toContain("Quoting");
    });
    expect(container.querySelectorAll("button").length).toBe(1);
    expect(container.textContent).toContain("Asked");
    fireEvent.click(buttonNamed(container, "Ask for it: a_new"));
    await waitFor(() => {
      expect(sent).toEqual([{ path: "/api/v1/me/agents/a_new/request", body: null }]);
    });
  });
});
