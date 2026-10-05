/**
 * Two console tabs on one session keep working (DEF-12).
 *
 * The console keeps its tokens in memory, per tab, and the identity provider keeps one session
 * for the browser. A second tab must sign in from that session without asking again, and neither
 * tab's sign-in may end the other's. Deleting this leaves the console README's known gap with no
 * test that would notice it closing or reopening.
 */

import { expect, test } from "@playwright/test";
import { checkPage, reset, watch } from "../lib/checklist";
import { signInAsAdmin } from "../lib/signin";
import { openFromMenu } from "../pages/module";

/** The menu group both pages are in, as the navigation API heads it. */
const PEOPLE = "People and access";

test("a second tab signs in from the first tab's session and both keep working", async ({ browser }, info) => {
  const context = await browser.newContext();
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
  await context.close();
});
