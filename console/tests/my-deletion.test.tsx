/**
 * Asking for one's own data to be deleted, from My workspace, and the Retention screen's list of
 * the people who asked.
 *
 * Mounted on their own, for the reason `tests/my-workspace-page.test.tsx` gives. The failures worth
 * testing look like the page working: an ask sent with no second step, a second ask offered while
 * one waits, a card that offers to ask when the API offered nothing, and a list of what a deletion
 * does that leaves out what it does not reach.
 *
 * Task ids: M40.4.2.3
 */

import { fireEvent, render, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import {
  ASK_DELETION_LABEL,
  DELETION_CONSEQUENCE,
  KEEP_MY_DATA_LABEL,
  RETAINED_LABEL,
  ROTATES_LABEL,
} from "../src/components/MyDeletion";
import { MY_DELETION_API_PATH } from "../src/pages/myDeletionQuery";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";

const ORIGIN = "https://console.test";

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

const ROUTE = {
  order: [],
  reaches: [{ store: "rows", holds: "ROWS-SENTENCE" }],
  rotates_out: [{ store: "backup", holds: "BACKUP-SENTENCE" }],
  retained: [{ store: "ledger", holds: "LEDGER-SENTENCE" }],
};

function view(overrides: Record<string, unknown> = {}) {
  return {
    may_ask: true,
    asked_at: null,
    state: "none",
    told: "ASKING-DELETES-NOTHING",
    route: ROUTE,
    ...overrides,
  };
}

async function mount(answer: unknown) {
  const sent: { path: string; method: string }[] = [];
  const idp = fakeIdentityProvider({
    api(url, init) {
      const path = new URL(url, ORIGIN).pathname;
      const method = (init?.method ?? "GET").toUpperCase();
      if (path !== `/api/v1${MY_DELETION_API_PATH}`) return null;
      if (method === "POST") {
        sent.push({ path, method });
        return json(view({ state: "waiting", may_ask: false, asked_at: "2019-03-01T09:00:00Z" }));
      }
      return json(answer);
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { MyDeletionCard } = await import("../src/components/MyDeletion");
  const { container } = render(<MyDeletionCard />);
  return { container, sent };
}

function buttonNamed(root: ParentNode, name: string): HTMLButtonElement {
  const found = [...root.querySelectorAll("button")].find((one) => one.textContent?.trim() === name);
  if (!found) throw new Error(`no button ${name}`);
  return found;
}

describe("asking for my data to be deleted", () => {
  test("the card says what a deletion reaches, what only time removes and what is kept, before the ask", async () => {
    // What breaks if this is deleted: the ask is offered with the stores a deletion does not reach
    // left out, so the page promises more than the deletion does.
    const { container } = await mount(view());
    await waitFor(() => {
      expect(container.textContent).toContain("ROWS-SENTENCE");
    });
    expect(container.querySelector(`ul[aria-label="${ROTATES_LABEL}"]`)?.textContent).toBe("BACKUP-SENTENCE");
    expect(container.querySelector(`ul[aria-label="${RETAINED_LABEL}"]`)?.textContent).toBe("LEDGER-SENTENCE");
    expect(container.textContent).toContain("ASKING-DELETES-NOTHING");
  });

  test("the ask is confirmed first, says what will happen, and sends nothing until it is", async () => {
    // What breaks if this is deleted: one press starts the first step of an irreversible erasure,
    // or the confirmation does not say that nothing is deleted by asking.
    const { container, sent } = await mount(view());
    await waitFor(() => {
      expect(buttonNamed(container, ASK_DELETION_LABEL)).toBeTruthy();
    });
    fireEvent.click(buttonNamed(container, ASK_DELETION_LABEL));
    expect(container.textContent).toContain(DELETION_CONSEQUENCE);
    fireEvent.click(buttonNamed(container, KEEP_MY_DATA_LABEL));
    expect(sent).toEqual([]);

    fireEvent.click(buttonNamed(container, ASK_DELETION_LABEL));
    const confirm = [...container.querySelectorAll("button")].filter(
      (one) => one.textContent?.trim() === ASK_DELETION_LABEL,
    );
    fireEvent.click(confirm[confirm.length - 1] as HTMLButtonElement);
    await waitFor(() => {
      expect(sent).toEqual([{ path: `/api/v1${MY_DELETION_API_PATH}`, method: "POST" }]);
    });
  });

  test("an ask that is waiting is shown with its date and offers no second ask", async () => {
    // What breaks if this is deleted: pressing again queues a second ask, or the person cannot
    // tell that the first was taken.
    const { container } = await mount(
      view({ may_ask: false, state: "waiting", asked_at: "2019-03-01T09:00:00Z", told: "WAITING-TOLD" }),
    );
    await waitFor(() => {
      expect(container.textContent).toContain("WAITING-TOLD");
    });
    expect(container.textContent).toContain("Asked");
    expect([...container.querySelectorAll("button")]).toEqual([]);
  });

  test("when the API offers no ask the card offers none", async () => {
    // What breaks if this is deleted: the card offers an ask the API will refuse, or the switch
    // being off is drawn as an error.
    const { container } = await mount(view({ may_ask: false }));
    await waitFor(() => {
      expect(container.textContent).toContain("ROWS-SENTENCE");
    });
    expect([...container.querySelectorAll("button")]).toEqual([]);
  });
});
