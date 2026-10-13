/**
 * The settings card in My workspace: learning, where a person is reached, and quiet hours.
 *
 * Mounted on its own, for the reason `tests/my-workspace-page.test.tsx` gives. The failures worth
 * testing look like the page working: a switch that sends the state it already shows, a reach saved
 * in pieces, and a channel the person is not connected on offered as a choice.
 *
 * Task ids: M40.4.1.4, M40.5.2.1, M40.5.2.2, M40.5.2.3, M40.5.2.4
 */

import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { LEARNING_OFF_LABEL, SAVE_QUIET_LABEL, SAVE_REACH_LABEL } from "../src/components/MyPreferences";
import { LEARNING_API_PATH, QUIET_API_PATH, REACH_API_PATH } from "../src/pages/myPreferencesQuery";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";

const ORIGIN = "https://console.test";

beforeAll(async () => {
  await import("../src/components/MyPreferences");
}, 60_000);

const SAVED = {
  learning: { opted_out: false, cost: "COST-SENTENCE" },
  channels: [
    { channel: "slack", primary: false, chosen: false, notify: [], may_carry_an_approval: false },
  ],
  primary: null,
  approval_route: null,
  approval_choices: ["console"],
  notice_kinds: ["automation", "digest"],
  quiet: null,
  quiet_applies_to: ["automation", "digest"],
  approvals_are_never_held: "APPROVALS-SENTENCE",
  ignored: [],
};

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

async function mount() {
  const sent: { path: string; body: unknown }[] = [];
  const idp = fakeIdentityProvider({
    api(url, init) {
      const path = new URL(url, ORIGIN).pathname;
      if ((init?.method ?? "GET").toUpperCase() === "POST") {
        sent.push({ path, body: typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : null });
        return json(SAVED);
      }
      return path === "/api/v1/me/preferences" ? json(SAVED) : null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { MyPreferences } = await import("../src/components/MyPreferences");
  const { container } = render(<MyPreferences />);
  await waitFor(() => {
    expect(container.textContent).toContain("COST-SENTENCE");
  });
  return { container, sent };
}

function buttonNamed(root: ParentNode, name: string): HTMLButtonElement {
  const found = [...root.querySelectorAll("button")].find((one) => one.textContent?.trim() === name);
  if (!found) throw new Error(`no button ${name}`);
  return found;
}

describe("a person's own settings", () => {
  test("switching learning off sends the opposite of what is shown, with the cost beside it", async () => {
    // What breaks if this is deleted: a switch that sends the state it already shows, so pressing
    // it never turns learning off, or one that hides what switching it off costs.
    const { container, sent } = await mount();
    expect(container.textContent).toContain("Learning from you is on.");
    fireEvent.click(buttonNamed(container, LEARNING_OFF_LABEL));
    await waitFor(() => {
      expect(sent).toEqual([{ path: `/api/v1${LEARNING_API_PATH}`, body: { opted_out: true } }]);
    });
  });

  test("only the channels the person is connected on are offered, and the whole reach is sent at once", async () => {
    // What breaks if this is deleted: a channel nobody proved offered as primary, or a reach saved
    // in pieces that disagree with each other.
    const { container, sent } = await mount();
    const [primary, route] = [...container.querySelectorAll("select")];
    expect([...primary.options].map((one) => one.value)).toEqual(["", "slack"]);
    expect([...route.options].map((one) => one.value)).toEqual(["", "console"]);
    fireEvent.change(primary, { target: { value: "slack" } });
    fireEvent.change(route, { target: { value: "console" } });
    fireEvent.click(container.querySelector('input[type="checkbox"]') as HTMLInputElement);
    fireEvent.click(buttonNamed(container, SAVE_REACH_LABEL));
    await waitFor(() => {
      expect(sent).toEqual([
        {
          path: `/api/v1${REACH_API_PATH}`,
          body: {
            primary: "slack",
            approval_route: "console",
            notices: [{ channel: "slack", notify: ["automation"] }],
          },
        },
      ]);
    });
  });

  test("quiet hours are sent as two times and say an approval is never held", async () => {
    // What breaks if this is deleted: hours sent half-filled, or a page that reads as a promise
    // that nothing will interrupt the person, when an approval always will.
    const { container, sent } = await mount();
    expect(container.textContent).toContain("APPROVALS-SENTENCE");
    expect(buttonNamed(container, SAVE_QUIET_LABEL).disabled).toBe(true);
    const [from, until] = [...container.querySelectorAll('input[type="time"]')];
    fireEvent.change(from, { target: { value: "22:00" } });
    fireEvent.change(until, { target: { value: "07:00" } });
    fireEvent.click(buttonNamed(container, SAVE_QUIET_LABEL));
    await waitFor(() => {
      expect(sent).toEqual([{ path: `/api/v1${QUIET_API_PATH}`, body: { start: "22:00", end: "07:00" } }]);
    });
  });
});
