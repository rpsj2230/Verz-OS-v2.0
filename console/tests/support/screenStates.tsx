/**
 * Mount any page the console registers in one of the states a request can leave it in, and read
 * back what the page said in that state.
 *
 * `docs/admin-console.md` holds every screen to four sentences: loading, empty, unreachable and
 * failed. `tests/screen-states.test.tsx` asks that of every route, and this is the part of it that
 * is not a rule: a stand-in API that can hold a request open for ever, refuse to be reached at
 * all, answer with a fault, or answer with a given body, and a reading of the page that a test
 * can compare between states.
 *
 * **The stand-in answers the page and never the sign-in or the menu.** The identity provider's
 * addresses go to `support/auth.ts` exactly as every other page test has them, and the shell's own
 * question, which console the reader is given, is answered with the console the page case names or
 * the company's. So a page in the unreachable state is a signed-in page inside its menu whose own
 * requests cannot be reached, which is the state a person meets, and not a console that never got
 * past the session guard or a shell with nothing in it. The shell's states are the shell's tests.
 *
 * **What a page said is read as sentences, not as one string.** A string comparison between two
 * states is satisfied by any difference at all, including the API's own message, which is the one
 * part of a failure the page did not write. Each element that holds text of its own gives one
 * sentence, whole, so a test can remove the API's words and ask what is left.
 *
 * **Two more ways to fail, both from the staging install on 2026-09-17.** A proxy's answer when
 * the application never ran, which has no body and no trace id (`bodiless`), and the 404 the API
 * gives a sign-in with no second factor, with and without its flag (`refused`). The first is what
 * drew "Something went wrong." with nothing to quote; the second is what drew "I could not find
 * that." for work the person holds.
 *
 * **The shell's own read of `/me` is answered like the menu's**, with a caller who needs no second
 * factor and without being recorded, for every page whose case does not read `/me` itself. The
 * shell asks on every page for the banner in `layout/SignInStrength.tsx`, and a page that asks for
 * nothing would otherwise be recorded asking. The one page that reads `/me` for itself, the
 * Overview, has its states applied to both reads, since the two cannot be told apart by address.
 *
 * Task ids: M27.8.3, M27.8.5
 */

import { createMemoryRouter, RouterProvider, type RouteObject } from "react-router-dom";
import { cleanup, render } from "@testing-library/react";
import { vi } from "vitest";
import { NOT_FOUND_MESSAGE } from "../../src/api/errors";
import { CALLBACK_PATH, SIGNED_OUT_PATH } from "../../src/auth/constants";
import { RETURN_PATH as STAFF_LIST_RETURN_PATH } from "../../src/setup/staffList";
import { FIRST_RUN_PATH } from "../../src/setup/wizard";
import { fakeIdentityProvider, ISSUER, loadConsole, signIn } from "./auth";
import { COMPANY_CONSOLE, NAVIGATION_ADDRESS } from "./navigation";
import { PAGES } from "./pageCases";

export const CONSOLE_ORIGIN = "https://console.test";

/** What the stand-in API does with every request the page makes. */
export type RequestState =
  | { readonly kind: "pending" }
  | { readonly kind: "unreachable" }
  | { readonly kind: "failed" }
  | { readonly kind: "bodiless" }
  | { readonly kind: "refused"; readonly secondFactorNeeded: boolean }
  | { readonly kind: "answered"; readonly answers: Readonly<Record<string, unknown>> };

/** The API's own sentence for a fault, which a page shows and did not write. */
export const API_SENTENCE = "FAULT-SENTINEL the API explained itself here";
/** The reference a failed answer carries. */
export const TRACE_SENTINEL = "trace-sentinel-0001";
/** The API's sentence on a 404 that says a sign-in with a second factor is needed. */
export const SECOND_FACTOR_SENTENCE =
  "SECOND-FACTOR-SENTINEL Administration and approvals need a sign-in with a second factor.";
/** Where the shell asks for the caller's own facts. */
export const ME_ADDRESS = "/api/v1/me";
/** The caller the shell is told about on a page that does not read `/me` itself. */
export const A_CALLER_WITH_NOTHING_WITHHELD = Object.freeze({
  principal_id: "u_reader",
  display_name: "A reader",
  assurance: "strong",
  channel: "web",
  ent_hash: "f".repeat(64),
  withheld_verbs: [],
  second_factor_needed: false,
});

/** One mounted page in one state. */
export interface Reading {
  /** Every sentence the page drew, whole and with its white space collapsed. */
  readonly sentences: ReadonlySet<string>;
  /** Every API path the page asked for, without its query, once each. */
  readonly asked: readonly string[];
  /** Paths asked for in an answered state that the case gave no answer for. */
  readonly unanswered: readonly string[];
  /** Every request the page sent, with its method and body. */
  readonly sent: readonly Sent[];
  readonly root: Element;
}

export interface Sent {
  readonly method: string;
  readonly path: string;
  readonly body: unknown;
}

/** Every leaf pattern in a route table, spelled from the root. */
export function patternsOf(routes: readonly RouteObject[], parent = ""): string[] {
  const found: string[] = [];
  for (const route of routes) {
    const own =
      route.index === true
        ? parent || "/"
        : route.path === undefined
          ? parent
          : route.path.startsWith("/")
            ? route.path
            : `${parent === "/" ? "" : parent}/${route.path}`;
    if (route.children && route.children.length > 0) {
      found.push(...patternsOf(route.children, own));
    } else {
      found.push(own);
    }
  }
  return found;
}

/** Patterns outside the session guard, which mount without anybody signed in. */
export const UNGUARDED: ReadonlySet<string> = new Set([
  CALLBACK_PATH,
  SIGNED_OUT_PATH,
  FIRST_RUN_PATH,
  STAFF_LIST_RETURN_PATH,
]);

export function collapse(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

/**
 * Every sentence under `root`: the whole text of each element that holds text of its own.
 *
 * An element with a text node of its own is where a sentence was written, so its whole text is
 * the sentence, including any `<code>` or `<strong>` inside it. The inner element is read as well,
 * which only ever adds a sentence that is also part of a longer one.
 */
export function sentencesOf(root: Element): Set<string> {
  const found = new Set<string>();
  const visit = (element: Element): void => {
    const ownText = [...element.childNodes].some(
      (node) => node.nodeType === Node.TEXT_NODE && collapse(node.textContent ?? "") !== "",
    );
    if (ownText) {
      found.add(collapse(element.textContent ?? ""));
    }
    for (const child of element.children) {
      visit(child);
    }
  };
  visit(root);
  return found;
}

/**
 * Wait until `read` gives the same answer three times running, ten milliseconds apart.
 *
 * Every answer the stand-in gives settles within the microtasks after its timer, so a page that
 * has not changed across three timers has drawn what it was given. A busier machine only lengthens
 * the wait, which is the safe direction. Four reads fifteen apart were measured first, and the
 * extra time was spent three hundred times per run for nothing a shorter window missed.
 */
export async function stable(read: () => string, timeoutMs = 15_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let last = "";
  let same = 0;
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 10));
    const now = read();
    if (now === last) {
      same += 1;
      if (same >= 3) {
        return;
      }
    } else {
      same = 0;
      last = now;
    }
  }
  throw new Error("The page never stopped changing.");
}

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "x-trace-id": TRACE_SENTINEL },
  });
}

export interface Mounted extends Reading {
  readonly container: HTMLElement;
  /** Read the page again, after the test has done something to it. */
  reread(): Promise<Reading>;
}

/**
 * Mount the whole console at `address`, with the API in `state`, and read the page once it has
 * stopped changing.
 *
 * `waitForAsking` is how a pending page is told apart from a page whose lazy module has not
 * arrived: both say "Loading.", and only the first has sent its request. A caller that knows the
 * page asks for something passes true, and the reading waits for the request before it waits for
 * the page to settle.
 */
export async function mountIn(
  pattern: string,
  address: string,
  state: RequestState,
  waitForAsking = false,
  navigation: unknown = COMPANY_CONSOLE,
): Promise<Mounted> {
  // One page at a time. A test reads a page in several states, and a second console mounted
  // beside the first would share its storage, where the sign-in loop guard counts attempts.
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
  const idp = fakeIdentityProvider();
  const asked: string[] = [];
  const unanswered: string[] = [];
  const sent: Sent[] = [];
  const readsMe = ME_ADDRESS in (PAGES[pattern]?.answers ?? {});
  const fetch = vi.fn(async (input: unknown, init?: RequestInit): Promise<Response> => {
    const url = String(input);
    if (url.startsWith(new URL(ISSUER).origin)) {
      return (await idp.fetch(input, init)) as Response;
    }
    const path = new URL(url, CONSOLE_ORIGIN).pathname;
    if (path === NAVIGATION_ADDRESS) {
      return json(state.kind === "answered" ? (state.answers[NAVIGATION_ADDRESS] ?? navigation) : navigation, 200);
    }
    if (path === ME_ADDRESS && !readsMe) {
      return json(A_CALLER_WITH_NOTHING_WITHHELD, 200);
    }
    const method = (init?.method ?? "GET").toUpperCase();
    const body: unknown = typeof init?.body === "string" && init.body !== "" ? JSON.parse(init.body) : null;
    asked.push(path);
    sent.push({ method, path, body });
    switch (state.kind) {
      case "pending":
        return await new Promise<Response>(() => undefined);
      case "unreachable":
        throw new TypeError("Failed to fetch");
      case "failed":
        return json({ message: API_SENTENCE, trace_id: TRACE_SENTINEL }, 500);
      case "bodiless":
        // What a reverse proxy sends when the application behind it did not answer at all.
        return new Response(null, { status: 502 });
      case "refused":
        return json(
          {
            message: state.secondFactorNeeded ? SECOND_FACTOR_SENTENCE : NOT_FOUND_MESSAGE,
            trace_id: TRACE_SENTINEL,
            problems: [],
            second_factor_needed: state.secondFactorNeeded,
          },
          404,
        );
      case "answered": {
        const key = method === "GET" ? path : `${method} ${path}`;
        if (!(key in state.answers)) {
          unanswered.push(key);
          return json({ message: API_SENTENCE, trace_id: TRACE_SENTINEL }, 500);
        }
        return json(state.answers[key], 200);
      }
    }
  });
  const loaded = await loadConsole({ idp: { ...idp, fetch }, path: address.split("?")[0] });
  if (!UNGUARDED.has(pattern)) {
    await signIn(loaded);
  }
  const { routes } = await import("../../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [address] });
  const { container } = render(<RouterProvider router={router} />);
  const root = (): Element => container.querySelector("main#main") ?? container;
  // A split page's module arrives after the first render, behind the shell's own "Loading.", so
  // nothing is read until the page has either sent a request or drawn its heading.
  const deadline = Date.now() + 15_000;
  while (waitForAsking ? asked.length === 0 : asked.length === 0 && root().querySelector("h1, .centred-panel") === null) {
    if (Date.now() > deadline) {
      throw new Error(`${pattern} never ${waitForAsking ? "asked the API for anything" : "arrived"}.`);
    }
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  const reread = async (): Promise<Reading> => {
    await stable(() => `${root().innerHTML}#${sent.length}`);
    return {
      sentences: sentencesOf(root()),
      asked: [...new Set(asked)],
      unanswered: [...unanswered],
      sent: [...sent],
      root: root(),
    };
  };
  const first = await reread();
  return { ...first, container, reread };
}
