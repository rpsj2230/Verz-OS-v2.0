/**
 * Referred to me on the page kit: what has been referred to the reader, named by who asked, and the
 * one act of marking each handled, sent only from its confirmation.
 *
 * Task ids: M24.2.2, M27.16.1
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { render, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { HANDLED_LABEL, HANDLING, NOTHING_REFERRED, READING_REFERRALS } from "../src/pages/Referrals";
import { handledApiPath, type Referral } from "../src/pages/referralsQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { installRadixStubs } from "./support/radix";
import { chooseInMenu, confirmWith } from "./support/rowMenu";

const CONSOLE_ORIGIN = "https://console.test";
const REFERRALS_OPERATION = "/api/v1/me/referrals";
const OPEN_ID = "11111111-1111-4111-8111-111111111111";
const ASKER = "u_asker_5d1e";
const PEOPLE = { [ASKER]: "Aisha Asker", u_me: "Me Myself" };

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/Referrals");
}, 60_000);

function referral(overrides: Partial<Referral> = {}): Referral {
  return {
    referral_id: OPEN_ID,
    topic: "grievance",
    label: "Grievances",
    asked_by: ASKER,
    asked_at: "2019-03-04T09:00:00Z",
    handled_at: null,
    handled_by: null,
    ...overrides,
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

async function mount(referrals: Referral[]): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  let handled = false;
  const idp = fakeIdentityProvider({
    api(url, init) {
      const path = new URL(url, CONSOLE_ORIGIN).pathname;
      if (init?.method === "POST") {
        handled = true;
      }
      if (path === REFERRALS_OPERATION || init?.method === "POST") {
        const now = handled ? referrals.map((one) => ({ ...one, handled_at: "2019-03-05T10:00:00Z", handled_by: "u_me" })) : referrals;
        return json({ referrals: now, people: PEOPLE });
      }
      return null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { Referrals } = await import("../src/pages/Referrals");
  const router = createMemoryRouter([{ path: "/referrals", element: <Referrals /> }], { initialEntries: ["/referrals"] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if ((container.textContent ?? "").includes(READING_REFERRALS) || container.querySelector("h1") === null) {
      throw new Error("still reading");
    }
  });
  return { container, idp };
}

function posts(idp: FakeIdp): string[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST" && new URL(call.url, CONSOLE_ORIGIN).pathname.startsWith("/api/"))
    .map((call) => new URL(call.url, CONSOLE_ORIGIN).pathname);
}

describe("what has been referred to me", () => {
  test("nothing referred is said in a sentence, not drawn as an empty table", async () => {
    // What breaks if this is deleted: an empty table that reads as a list somebody emptied.
    const { container } = await mount([]);
    expect(container.textContent).toContain(NOTHING_REFERRED);
    expect(container.querySelector("table")).toBeNull();
  });

  test("each referral names its topic, who asked by name and when, and nothing of what was asked", async () => {
    // What breaks if this is deleted: a principal id where the reader needs a person to contact, or
    // a column for the question, which was never kept.
    const { container } = await mount([referral(), referral({ referral_id: "r2", handled_at: "2019-03-05T10:00:00Z", handled_by: "u_me" })]);
    const table = container.querySelector("table") as HTMLElement;
    expect(within(table).getAllByText("Aisha Asker")).toHaveLength(2);
    expect(table.textContent).not.toContain(ASKER);
    expect(table.textContent).toContain("Me Myself");
    const headings = [...table.querySelectorAll("thead th")].map((one) => one.textContent);
    expect(headings.join(" ")).not.toMatch(/question|said|wrote/i);
    expect(screen.getAllByRole("button", { name: /^Actions for the Grievances referral/ })).toHaveLength(1);
  });

  test("marking one handled is confirmed, then sent to that referral, and the list says so", async () => {
    // What breaks if this is deleted: a mark sent from the menu with no confirmation, or sent to
    // another referral.
    const { container, idp } = await mount([referral()]);
    await chooseInMenu(screen.getByRole("button", { name: /^Actions for the Grievances referral/ }), HANDLED_LABEL);
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("Mark the Grievances referral from Aisha Asker");
    expect(dialog.textContent).toContain(HANDLING);
    expect(posts(idp)).toEqual([]);
    await confirmWith(HANDLED_LABEL);

    await waitFor(() => {
      expect(container.textContent).toContain("is marked handled.");
    });
    expect(posts(idp)).toEqual([`/api/v1${handledApiPath(OPEN_ID)}`]);
  });
});
