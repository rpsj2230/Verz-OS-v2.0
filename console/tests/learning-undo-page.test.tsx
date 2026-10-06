/**
 * The page a weekly learning digest links: opening it undoes nothing, pressing Undo posts the
 * memory's id and nothing else to the grant-free route, and a refusal says so.
 *
 * Mounted through the console's own route table, so the address the digest builds is the address
 * this page answers at.
 *
 * Task ids: M16.5.1
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  KEEP_IT,
  NOT_UNDONE_TITLE,
  UNDO_CONSEQUENCE,
  UNDO_HEADING,
  UNDO_LABEL,
} from "../src/pages/LearningUndo";
import { LEARNING_UNDO_API_PATH, UNDO_PAGE_PREFIX } from "../src/pages/learningUndoQuery";
import { routes } from "../src/pages/LearningUndo.route";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";

const CONSOLE_ORIGIN = "https://console.test";
const OPERATION = `/api/v1${LEARNING_UNDO_API_PATH}`;

beforeAll(async () => {
  await import("../src/pages/LearningUndo");
}, 60_000);

interface Sent {
  readonly method: string;
  readonly path: string;
  readonly body: unknown;
}

async function opened(
  answer: Response,
): Promise<{ container: HTMLElement; sent: Sent[] }> {
  const sent: Sent[] = [];
  const idp = fakeIdentityProvider({
    api(url, init) {
      const where = new URL(url, CONSOLE_ORIGIN).pathname;
      const method = (init?.method ?? "GET").toUpperCase();
      const body = typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : null;
      sent.push({ method, path: where, body });
      return method === "POST" && where === OPERATION ? answer : null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const router = createMemoryRouter([...routes], {
    initialEntries: [`${UNDO_PAGE_PREFIX}mem_abc123`],
  });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    expect(container.querySelector("h1")?.textContent).toBe(UNDO_HEADING);
  });
  return { container, sent };
}

function buttonNamed(root: ParentNode, name: string): HTMLButtonElement {
  const found = [...root.querySelectorAll("button")].find(
    (one) => one.textContent?.trim() === name,
  );
  if (!found) {
    throw new Error(`no button ${name}`);
  }
  return found;
}

function undoButton(container: HTMLElement): HTMLButtonElement {
  return buttonNamed(container, UNDO_LABEL);
}

function dialog(): HTMLElement {
  const found = document.body.querySelector<HTMLElement>('[role="alertdialog"], [role="dialog"]');
  if (!found) {
    throw new Error("no dialog");
  }
  return found;
}

function confirmUndo(container: HTMLElement): void {
  fireEvent.click(undoButton(container));
  fireEvent.click(buttonNamed(dialog(), UNDO_LABEL));
}

describe("the digest's undo page", () => {
  test("opening the link sends nothing, keeping it sends nothing, and confirming Undo posts that memory alone and shows what it did", async () => {
    // What breaks if this is deleted: a page that undoes on opening, so a chat unfurling the
    // digest's link undoes every learning in it, or one posting to a route its reader is refused.
    const { container, sent } = await opened(
      new Response(
        JSON.stringify({ memory_id: "mem_abc123", took_effect: true, told: "UNDONE-SENTENCE" }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    expect(sent.filter((one) => one.method === "POST")).toEqual([]);

    fireEvent.click(undoButton(container));
    expect(dialog().textContent).toContain(UNDO_CONSEQUENCE);
    fireEvent.click(buttonNamed(dialog(), KEEP_IT));
    expect(sent.filter((one) => one.method === "POST")).toEqual([]);

    confirmUndo(container);
    await waitFor(() => {
      expect(container.textContent).toContain("UNDONE-SENTENCE");
    });
    expect(sent.filter((one) => one.method === "POST").map((one) => [one.path, one.body])).toEqual([
      [OPERATION, { memory_id: "mem_abc123" }],
    ]);
  });

  test("a refusal is said under the page's own heading and nothing claims it was undone", async () => {
    // What breaks if this is deleted: a 404 for somebody else's memory drawn as a success.
    const { container } = await opened(
      new Response(JSON.stringify({ message: "not answerable", trace_id: "t" }), {
        status: 404,
        headers: { "content-type": "application/json" },
      }),
    );
    confirmUndo(container);
    await waitFor(() => {
      expect(container.textContent).toContain(NOT_UNDONE_TITLE);
    });
    expect(container.querySelector('p.note[role="status"]')).toBeNull();
    expect(undoButton(container).disabled).toBe(false);
  });
});
