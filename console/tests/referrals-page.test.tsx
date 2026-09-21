/**
 * The Referred to me screen: the caller's own referrals, whether each is handled, and marking one.
 *
 * Mounted directly on a memory router at its own address, for the reason
 * `tests/sessions-page.test.tsx` gives. The failures worth testing are the ones that look like the
 * screen working: a referral marked handled on the first press, a handled one still offering the
 * button, and an empty list drawn as a blank table rather than said.
 *
 * Task ids: M24.2.2
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { HANDLED_LABEL, HANDLING, NOTHING_REFERRED, READING_REFERRALS } from "../src/pages/Referrals";
import { handledApiPath, referralState, type Referral } from "../src/pages/referralsQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";

const CONSOLE_ORIGIN = "https://console.test";
const REFERRALS_OPERATION = "/api/v1/me/referrals";
const OPEN_ID = "11111111-1111-4111-8111-111111111111";

beforeAll(async () => {
  await import("../src/pages/Referrals");
}, 60_000);

function referral(overrides: Partial<Referral> = {}): Referral {
  return {
    referral_id: OPEN_ID,
    topic: "grievance",
    label: "Grievances",
    asked_by: "u_asker",
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
  const idp = fakeIdentityProvider({
    api(url, init) {
      const path = new URL(url, CONSOLE_ORIGIN).pathname;
      if (init?.method === "POST") {
        return json({ referrals: referrals.map((one) => ({ ...one, handled_at: "2019-03-05T10:00:00Z", handled_by: "u_me" })) });
      }
      if (path === REFERRALS_OPERATION) {
        return json({ referrals });
      }
      return null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { Referrals } = await import("../src/pages/Referrals");
  const router = createMemoryRouter([{ path: "/referrals", element: <Referrals /> }], {
    initialEntries: ["/referrals"],
  });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (container.textContent?.includes(READING_REFERRALS) || !container.querySelector(".card")) {
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
    // What breaks if this is deleted: a person named for a topic sees a blank panel and cannot tell
    // an empty list from one still loading.
    const { container } = await mount([]);
    expect(container.textContent).toContain(NOTHING_REFERRED);
    expect(container.querySelector("table")).toBeNull();
  });

  test("each referral names its topic, who asked and when, and nothing of what was asked", async () => {
    // What breaks if this is deleted: a column added for the question, which does not exist and
    // would read as something withheld.
    const { container } = await mount([referral(), referral({ referral_id: "r-2", handled_at: "2019-03-04T12:00:00Z", handled_by: "u_me" })]);
    const rows = [...container.querySelectorAll("table[aria-label='Questions referred to you'] tbody tr")];
    expect(rows).toHaveLength(2);
    expect(rows[0]?.textContent).toContain("Grievances");
    expect(rows[0]?.textContent).toContain("u_asker");
    expect(rows[0]?.textContent).toContain("Not handled yet.");
    expect(rows[1]?.textContent).toContain("by u_me");
    expect(rows[1]?.querySelector("button")).toBeNull();
    const headings = [...container.querySelectorAll("thead th")].map((one) => one.textContent);
    expect(headings).toEqual(["Topic", "Asked by", "Asked", "Where it stands", "Control"]);
  });

  test("marking one handled is confirmed, then sent to that referral, and the list is read again", async () => {
    // What breaks if this is deleted: a referral marked handled on the first press, which cannot be
    // reopened, or the mark sent for a different referral than the row pressed.
    const { container, idp } = await mount([referral()]);
    fireEvent.click(container.querySelector("tbody button") as HTMLButtonElement);
    const confirmation = container.querySelector(".confirm")?.textContent ?? "";
    expect(confirmation).toContain("Mark the Grievances referral from u_asker");
    expect(confirmation).toContain(HANDLING);
    expect(posts(idp)).toEqual([]);

    fireEvent.click(
      [...container.querySelectorAll(".confirm button")].find((one) => one.textContent === HANDLED_LABEL) as HTMLButtonElement,
    );
    await waitFor(() => {
      expect(posts(idp)).toEqual([`/api/v1${handledApiPath(OPEN_ID)}`]);
    });
    await waitFor(() => {
      expect(container.textContent).toContain("is marked handled.");
    });
  });

  test("a handled referral says who handled it and when", () => {
    expect(referralState(referral({ handled_at: "2019-03-04T12:00:00Z", handled_by: "u_me" }), () => "THEN")).toBe(
      "Handled at THEN by u_me.",
    );
    expect(referralState(referral(), () => "THEN")).toBe("Not handled yet.");
  });
});
