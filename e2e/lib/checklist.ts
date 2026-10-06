/**
 * The one checklist every console page is held to, before any module's own cases.
 *
 * Each one a failure a person would see and a unit test would not:
 *
 * 1. **The page draws a heading.** A route that renders nothing, or the shell's own fallback,
 *    has no level-one heading in `main`.
 * 2. **No request the page made was answered with a server fault.** A 5xx is the API failing,
 *    not the reader being refused, and refusals are the reader's business (and indistinguishable
 *    from absence by design), so a 4xx is recorded on the result rather than failing it.
 * 3. **Nothing was thrown in the page.** An uncaught exception is a screen half drawn.
 * 4. **Nothing internal is shown.** No task id, no API route and no internal constant anywhere on
 *    the page, menu and header included: `DEF-13` and M27.15.53.
 * 5. **A control that is not available yet says why, in plain words.** Every `data-unavailable`
 *    control's reason is a sentence naming no task, route or constant (M27.15.53).
 * 6. **Nothing is asked of anybody but the install.** Every request goes to the install or its
 *    identity provider; the console sends no telemetry and loads nothing from elsewhere (M27.15.82).
 * 7. **Nothing is refused by the page's content security policy** (M27.15.81).
 *
 * The checks are made on the page as the browser drew it, after the network went quiet, because
 * a list that loads after the heading is where a failure notice appears.
 *
 * Task ids: M27.10.6, M27.15.53, M27.15.81, M27.15.82
 */

import { expect, type Page, type TestInfo } from "@playwright/test";

/** A WBS task id as this repository writes one: M27.10.6, M32.2.2.1. */
export const TASK_ID = /\bM\d{1,2}(?:\.\d{1,3}){2,}\b/;

/** An API route written out where a person can read it. */
export const API_ROUTE = /\/api\/v1\//;

/**
 * An internal constant written out where a person can read it: three or more upper-case words
 * joined by underscores, the way this repository names its reason constants and settings.
 *
 * Except the settings in `OPERATOR_SETTINGS`, by their exact names.
 */
export const INTERNAL_CONSTANT = /\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+){2,}\b/g;

/**
 * Settings the server's environment file holds that a page may name, because naming one is telling
 * the person who runs the server what to type. The first run of the constant check found exactly
 * this on the Staff sources page, which says which two to set when the install runs no vault.
 *
 * Exact names rather than a prefix, so a leaked constant that happens to start the same way still
 * fails, and each is one the install guide's table of values defines
 * (`docs/install/configuration.md`), which a unit test holds it to.
 */
export const OPERATOR_SETTINGS: readonly string[] = ["BRAIN_VAULT_ADDRESS", "BRAIN_VAULT_TOKEN"];

/** The internal constants in a text, leaving out the settings an operator is told to type. */
export function internalConstants(text: string): string[] {
  return [...text.matchAll(INTERNAL_CONSTANT)].map((one) => one[0]).filter((one) => !OPERATOR_SETTINGS.includes(one));
}

/** The browser's own words when the page's content security policy refuses something. */
export const POLICY_REFUSAL = /Content Security Policy/i;

/**
 * The origins a console page may ask anything of: the install itself and its identity provider.
 * `E2E_BASE_URL` and `INSTALL_OIDC_ISSUER` are the job's own, the same two the browser is pointed at.
 */
export function installOrigins(): ReadonlySet<string> {
  const origins = new Set<string>([new URL(process.env["E2E_BASE_URL"] ?? "http://localhost:8000").origin]);
  const issuer = process.env["INSTALL_OIDC_ISSUER"];
  if (issuer) {
    origins.add(new URL(issuer).origin);
  }
  return origins;
}

/** The failure headings `console/src/ui/FailureNotice.tsx` draws for a request that failed. */
export const SERVER_FAILURE_HEADINGS: readonly string[] = ["The Brain could not be reached"];

export interface Watch {
  readonly faults: string[];
  readonly refusals: string[];
  readonly thrown: string[];
  /** Requests to an origin that is not the install's, by origin. */
  readonly elsewhere: string[];
  /** What the browser reported refusing under the page's content security policy. */
  readonly refusedByPolicy: string[];
  /** API requests sent and not yet answered. */
  inFlight: number;
}

/** How long the API must have been quiet before a page is judged: its lists have loaded. */
export const QUIET_MS = 500;

/**
 * Wait until no API request has been in flight for `QUIET_MS`, or `limitMs` has passed.
 *
 * Playwright's own `networkidle` describes the first load of a document and is already reached on
 * every page a single-page console navigates to afterwards, so it waits for nothing there. A list
 * that loads after the heading is where a failure notice or a server fault appears, so the page is
 * judged after the requests it started have been answered.
 */
export async function settle(page: Page, seen: Watch, limitMs = 20_000): Promise<void> {
  const until = Date.now() + limitMs;
  let quietSince = Date.now();
  while (Date.now() < until) {
    if (seen.inFlight > 0) {
      quietSince = Date.now();
    } else if (Date.now() - quietSince >= QUIET_MS) {
      return;
    }
    await page.waitForTimeout(100);
  }
}

/** Record every API answer and every uncaught exception on `page` from now on. */
export function watch(page: Page): Watch {
  const seen: Watch = { faults: [], refusals: [], thrown: [], elsewhere: [], refusedByPolicy: [], inFlight: 0 };
  const allowed = installOrigins();
  const isApi = (url: string): boolean => {
    const path = new URL(url).pathname;
    return path.startsWith("/api/") || path.startsWith("/setup/");
  };
  page.on("request", (request) => {
    const url = new URL(request.url());
    if ((url.protocol === "http:" || url.protocol === "https:") && !allowed.has(url.origin)) {
      seen.elsewhere.push(url.origin);
    }
    if (isApi(request.url())) {
      seen.inFlight += 1;
    }
  });
  const answered = (url: string): void => {
    if (isApi(url)) {
      seen.inFlight = Math.max(0, seen.inFlight - 1);
    }
  };
  page.on("requestfinished", (request) => answered(request.url()));
  page.on("requestfailed", (request) => answered(request.url()));
  page.on("response", (response) => {
    const path = new URL(response.url()).pathname;
    if (!path.startsWith("/api/") && !path.startsWith("/setup/")) {
      return;
    }
    const line = `${response.request().method()} ${path} ${String(response.status())}`;
    if (response.status() >= 500) {
      seen.faults.push(line);
    } else if (response.status() >= 400) {
      seen.refusals.push(line);
    }
  });
  page.on("pageerror", (error) => {
    seen.thrown.push(error.message);
  });
  page.on("console", (message) => {
    if (POLICY_REFUSAL.test(message.text())) {
      seen.refusedByPolicy.push(message.text());
    }
  });
  return seen;
}

/** Clear what was recorded, so each page is judged on its own requests. */
export function reset(seen: Watch): void {
  seen.faults.length = 0;
  seen.refusals.length = 0;
  seen.thrown.length = 0;
  seen.elsewhere.length = 0;
  seen.refusedByPolicy.length = 0;
}

/**
 * Every control the page draws as not available yet, with the sentence it gives for that.
 *
 * `UnavailableAction` (console/src/components/kit/parts.tsx) marks the control `data-unavailable`
 * and points `aria-describedby` at its reason, so the reason is read from where a screen reader
 * reads it rather than from the tooltip, which only exists while hovered.
 */
export async function unavailableReasons(page: Page): Promise<{ label: string; reason: string }[]> {
  return page.locator("[data-unavailable]").evaluateAll((controls) =>
    controls.map((control) => {
      const ids = (control.getAttribute("aria-describedby") ?? "").split(/\s+/).filter(Boolean);
      const reason = ids.map((id) => document.getElementById(id)?.textContent ?? "").join(" ").trim();
      return { label: (control.getAttribute("aria-label") ?? control.textContent ?? "").trim(), reason };
    }),
  );
}

/** A reason a person can read: a sentence of a few words, naming no task, route or constant. */
export function isPlainReason(reason: string): boolean {
  return (
    reason.split(/\s+/).length >= 4 &&
    !TASK_ID.test(reason) &&
    !API_ROUTE.test(reason) &&
    internalConstants(reason).length === 0
  );
}

/** Hold the page at `page.url()` to the checklist. `label` names it in every failure. */
export async function checkPage(page: Page, seen: Watch, label: string, info: TestInfo): Promise<void> {
  const main = page.locator("main#main");
  await expect(main.getByRole("heading", { level: 1 }).first(), `${label}: a heading`).toBeVisible({
    timeout: 20_000,
  });
  await settle(page, seen);
  // The whole page a person sees, the menu and header included, not only the page body.
  const text = await page.locator("body").innerText();
  expect(text, `${label}: no task id is shown`).not.toMatch(TASK_ID);
  expect(text, `${label}: no API route is shown`).not.toMatch(API_ROUTE);
  expect(internalConstants(text), `${label}: no internal constant is shown`).toEqual([]);
  const unexplained = (await unavailableReasons(page)).filter((one) => !isPlainReason(one.reason));
  expect(unexplained, `${label}: every control not available yet says why in plain words`).toEqual([]);
  expect([...new Set(seen.elsewhere)], `${label}: no request leaves the install`).toEqual([]);
  expect(seen.refusedByPolicy, `${label}: nothing refused by the content security policy`).toEqual([]);
  for (const heading of SERVER_FAILURE_HEADINGS) {
    await expect(main.getByText(heading, { exact: true }), `${label}: ${heading}`).toHaveCount(0);
  }
  expect(seen.faults, `${label}: no server fault`).toEqual([]);
  expect(seen.thrown, `${label}: nothing thrown`).toEqual([]);
  if (seen.refusals.length > 0) {
    info.annotations.push({ type: "refused", description: `${label}: ${seen.refusals.join(", ")}` });
  }
}
