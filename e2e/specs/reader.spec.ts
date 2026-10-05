/**
 * A person who is not an administrator, signing in with a password alone.
 *
 * The realm asks for a one-time code only of an account that has one, so the reader is never
 * shown the code page; the console then gives them their own menu, which can only be narrower
 * than the administrator's. Deleting this leaves the harness proving the console for exactly one
 * kind of person, the one who can see everything, which is the person for whom no permission bug
 * is visible.
 */

import { expect, test } from "@playwright/test";
import { checkPage, reset, watch } from "../lib/checklist";
import { addressesOf, servedNavigation } from "../lib/navigation";
import { READER } from "../lib/people";
import { signInAsAdmin, signInWithPassword } from "../lib/signin";
import { openFromMenu } from "../pages/module";

test("the reader signs in with a password alone and is served no page the administrator is not", async ({ browser }, info) => {
  const admin = await browser.newPage();
  const adminMenu = servedNavigation(admin);
  await signInAsAdmin(admin);
  const everything = new Set((await adminMenu).sections.flatMap((section) => addressesOf(section).map((one) => one.to)));
  await admin.close();

  const page = await browser.newPage();
  const seen = watch(page);
  const served = servedNavigation(page);
  await signInWithPassword(page, READER);
  await expect(page.locator("#otp"), "no one-time code is asked of an account without one").toHaveCount(0);
  const menu = await served;
  const theirs = menu.sections.flatMap((section) => addressesOf(section));
  expect(theirs.filter((one) => !everything.has(one.to)), "pages served to the reader alone").toEqual([]);
  for (const address of theirs) {
    reset(seen);
    await openFromMenu(page, address.to);
    await checkPage(page, seen, `reader: ${address.label} (${address.to})`, info);
  }
  await page.close();
});
