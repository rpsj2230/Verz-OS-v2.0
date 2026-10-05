/**
 * The one checklist every console page is held to, before any module's own cases.
 *
 * Four things, each one a failure a person would see and a unit test would not:
 *
 * 1. **The page draws a heading.** A route that renders nothing, or the shell's own fallback,
 *    has no level-one heading in `main`.
 * 2. **No request the page made was answered with a server fault.** A 5xx is the API failing,
 *    not the reader being refused, and refusals are the reader's business (and indistinguishable
 *    from absence by design), so a 4xx is recorded on the result rather than failing it.
 * 3. **Nothing was thrown in the page.** An uncaught exception is a screen half drawn.
 * 4. **Nothing internal is shown.** No task id, no API route: `DEF-13`, "no page shows a package
 *    code, task id, route or internal name".
 *
 * The checks are made on the page as the browser drew it, after the network went quiet, because
 * a list that loads after the heading is where a failure notice appears.
 *
 * Task ids: M27.10.6
 */

import { expect, type Page, type TestInfo } from "@playwright/test";

/** A WBS task id as this repository writes one: M27.10.6, M32.2.2.1. */
export const TASK_ID = /\bM\d{1,2}(?:\.\d{1,3}){2,}\b/;

/** An API route written out where a person can read it. */
export const API_ROUTE = /\/api\/v1\//;

/** The failure headings `console/src/ui/FailureNotice.tsx` draws for a request that failed. */
export const SERVER_FAILURE_HEADINGS: readonly string[] = ["The Brain could not be reached"];

export interface Watch {
  readonly faults: string[];
  readonly refusals: string[];
  readonly thrown: string[];
}

/** Record every API answer and every uncaught exception on `page` from now on. */
export function watch(page: Page): Watch {
  const seen: Watch = { faults: [], refusals: [], thrown: [] };
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
  return seen;
}

/** Clear what was recorded, so each page is judged on its own requests. */
export function reset(seen: Watch): void {
  seen.faults.length = 0;
  seen.refusals.length = 0;
  seen.thrown.length = 0;
}

/** Hold the page at `page.url()` to the checklist. `label` names it in every failure. */
export async function checkPage(page: Page, seen: Watch, label: string, info: TestInfo): Promise<void> {
  const main = page.locator("main#main");
  await expect(main.getByRole("heading", { level: 1 }).first(), `${label}: a heading`).toBeVisible({
    timeout: 20_000,
  });
  await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => undefined);
  const text = await main.innerText();
  expect(text, `${label}: no task id is shown`).not.toMatch(TASK_ID);
  expect(text, `${label}: no API route is shown`).not.toMatch(API_ROUTE);
  for (const heading of SERVER_FAILURE_HEADINGS) {
    await expect(main.getByText(heading, { exact: true }), `${label}: ${heading}`).toHaveCount(0);
  }
  expect(seen.faults, `${label}: no server fault`).toEqual([]);
  expect(seen.thrown, `${label}: nothing thrown`).toEqual([]);
  if (seen.refusals.length > 0) {
    info.annotations.push({ type: "refused", description: `${label}: ${seen.refusals.join(", ")}` });
  }
}
