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

/** Open a page and wait for the token refresh it has to make on the way. */
async function refreshedOpening(page: Page, to: string): Promise<number> {
  const refreshed = page.waitForResponse(isRefresh, { timeout: 30_000 });
  await openFromMenu(page, to, PEOPLE);
  return (await refreshed).status();
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

  // Both tabs' access tokens expire; each refreshes, and neither refresh signs the other out.
  await context.clock.fastForward(PAST_THE_TOKEN);
  reset(firstSeen);
  expect(await refreshedOpening(first, "/people"), "the first tab's refresh is accepted").toBe(200);
  await checkPage(first, firstSeen, "first tab after refreshing", info);
  reset(secondSeen);
  expect(await refreshedOpening(second, "/people"), "the second tab's refresh is accepted").toBe(200);
  await checkPage(second, secondSeen, "second tab after refreshing", info);
  reset(firstSeen);
  await openFromMenu(first, "/sessions", PEOPLE);
  await checkPage(first, firstSeen, "first tab after the second refreshed", info);
  await expect(first.locator("#username"), "neither tab was sent back to sign in").toHaveCount(0);
  await expect(second.locator("#username")).toHaveCount(0);
  await context.close();
});
