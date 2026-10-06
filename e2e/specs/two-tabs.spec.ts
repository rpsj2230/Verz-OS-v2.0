/**
 * Two console tabs on one session keep working (DEF-12).
 *
 * The console keeps its tokens in memory, per tab, and the identity provider keeps one session
 * for the browser. A second tab must sign in from that session without asking again, and neither
 * tab's sign-in may end the other's. Deleting this leaves the console README's known gap with no
 * test that would notice it closing or reopening.
 *
 * **And both tabs refresh the session (M27.15.13).** The browser's clock is moved past the access
 * token's lifetime, so each tab refreshes its own tokens with the identity provider on its next
 * request; both refreshes must be accepted and both tabs must stay signed in. The identity
 * provider rotates refresh tokens and refuses a reused one, which is how one tab's refresh used to
 * be able to sign the other out.
 *
 * Task ids: M27.15.13
 */

import { expect, test, type Page, type Response } from "@playwright/test";
import { checkPage, reset, watch } from "../lib/checklist";
import { signInAsAdmin } from "../lib/signin";
import { openFromMenu } from "../pages/module";

/** The menu group both pages are in, as the navigation API heads it. */
const PEOPLE = "People and access";

/** Past the realm's access token lifetime (300 seconds), so the next request must refresh. */
const PAST_THE_TOKEN = "06:00";

function isRefresh(response: Response): boolean {
  return (
    response.url().includes("/protocol/openid-connect/token") &&
    response.request().method() === "POST" &&
    (response.request().postData() ?? "").includes("grant_type=refresh_token")
  );
}

/** Every token refresh a tab makes, by status, from the moment this is called. */
function refreshesOf(page: Page): number[] {
  const seen: number[] = [];
  page.on("response", (response) => {
    if (isRefresh(response)) {
      seen.push(response.status());
    }
  });
  return seen;
}

/**
 * Open a page this tab has not loaded yet, so it has to ask the API, and wait until the tab has
 * refreshed. Counted from before the clock moved rather than awaited after the click, because a
 * timer the clock fires on its way forward may be what asks first.
 */
async function refreshedOpening(page: Page, seen: readonly number[], to: string): Promise<void> {
  await openFromMenu(page, to, PEOPLE);
  await expect.poll(() => seen.length, { timeout: 30_000, message: "the tab refreshed its tokens" }).toBeGreaterThan(0);
}

test("a second tab signs in from the first tab's session and both keep working", async ({ browser }, info) => {
  const context = await browser.newContext();
  // The page's clock runs as normal until it is moved forward below.
  await context.clock.install();
  const first = await context.newPage();
  const firstSeen = watch(first);
  await signInAsAdmin(first);
  await expect(first.locator('nav[aria-label="Sections"]')).toBeVisible({ timeout: 30_000 });

  const second = await context.newPage();
  const secondSeen = watch(second);
  await second.goto("/");
  await expect(second.locator('nav[aria-label="Sections"]'), "the second tab opens without a sign-in page").toBeVisible({
    timeout: 30_000,
  });
  await expect(second.locator("#username")).toHaveCount(0);

  for (const [page, seen, name] of [
    [first, firstSeen, "first tab"],
    [second, secondSeen, "second tab"],
    [first, firstSeen, "first tab again"],
  ] as const) {
    reset(seen);
    await openFromMenu(page, "/people", PEOPLE);
    await checkPage(page, seen, `${name}: People`, info);
  }

  await first.reload();
  await expect(first.locator('nav[aria-label="Sections"]'), "a reloaded tab signs in again by itself").toBeVisible({
    timeout: 30_000,
  });
  reset(secondSeen);
  await openFromMenu(second, "/sessions", PEOPLE);
  await checkPage(second, secondSeen, "second tab after the first reloaded", info);

  // Both tabs' access tokens expire; each refreshes, and neither refresh signs the other out. Each
  // opens a page it has not loaded since it last signed in: a page it already holds is drawn from
  // what it fetched before the clock moved, and nothing on it would need a token.
  const firstRefreshes = refreshesOf(first);
  const secondRefreshes = refreshesOf(second);
  await context.clock.fastForward(PAST_THE_TOKEN);
  reset(firstSeen);
  await refreshedOpening(first, firstRefreshes, "/sessions");
  expect(firstRefreshes.every((status) => status === 200), "the first tab's refreshes are accepted").toBe(true);
  await checkPage(first, firstSeen, "first tab after refreshing", info);
  reset(secondSeen);
  await refreshedOpening(second, secondRefreshes, "/sign-in-links");
  expect(secondRefreshes.every((status) => status === 200), "the second tab's refreshes are accepted").toBe(true);
  await checkPage(second, secondSeen, "second tab after refreshing", info);
  reset(firstSeen);
  await openFromMenu(first, "/people", PEOPLE);
  await checkPage(first, firstSeen, "first tab after the second refreshed", info);
  await expect(first.locator("#username"), "neither tab was sent back to sign in").toHaveCount(0);
  await expect(second.locator("#username")).toHaveCount(0);
  await context.close();
});
