/**
 * Mount one console page on its own, signed in, against a stand-in API that answers by path and
 * method.
 *
 * `tests/live-runs-page.test.tsx` builds this inline for one GET. The Features, Scheduled jobs,
 * Prompts and Errors tests each need a GET and a POST to the same stand-in, and the answer to the
 * GET to change after the POST, so the harness is written once: `answers` maps `METHOD path` to a
 * function, and every call is recorded with its method and body.
 *
 * Task ids: none
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { render, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./auth";

export const CONSOLE_ORIGIN = "https://console.test";

/** A function answering one request, handed its parsed JSON body. */
export type Answer = (body: unknown, url: URL) => Response;

export interface Sent {
  readonly method: string;
  readonly path: string;
  readonly body: unknown;
}

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

export interface Mounted {
  readonly container: HTMLElement;
  readonly idp: FakeIdp;
  readonly sent: Sent[];
}

/**
 * Mount `element` at `path`, answering `METHOD /api/v1/...` keys from `answers`, and wait until the
 * page has an answer to draw.
 */
export async function mountPage(
  path: string,
  load: () => Promise<ReactElement>,
  answers: Record<string, Answer>,
): Promise<Mounted> {
  const sent: Sent[] = [];
  const idp = fakeIdentityProvider({
    api(url, init) {
      const parsed = new URL(url, CONSOLE_ORIGIN);
      const method = (init?.method ?? "GET").toUpperCase();
      const body: unknown = typeof init?.body === "string" && init.body !== "" ? JSON.parse(init.body) : null;
      const answer = answers[`${method} ${parsed.pathname}`];
      if (answer === undefined) {
        return null;
      }
      sent.push({ method, path: `${parsed.pathname}${parsed.search}`, body });
      return answer(body, parsed);
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const element = await load();
  const router = createMemoryRouter([{ path, element }], { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  await settled(container);
  return { container, idp, sent };
}

/** Wait until the page has left every loading sentence behind. */
export async function settled(container: HTMLElement): Promise<void> {
  await waitFor(() => {
    const text = container.textContent ?? "";
    if (container.querySelector("h1") === null || /Reading |Loading\./.test(text)) {
      throw new Error("the page has no answer yet");
    }
  });
}

/** The button whose accessible name starts with `label`. */
export function button(container: HTMLElement, label: string): HTMLButtonElement {
  const found = [...container.querySelectorAll("button")].find(
    (one) => (one.getAttribute("aria-label") ?? one.textContent ?? "").startsWith(label),
  );
  if (found === undefined) {
    throw new Error(`no button named ${label}`);
  }
  return found;
}
