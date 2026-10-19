/**
 * Every module of the console, every page of each, against the furnished install.
 *
 * The administrator's served menu is walked page by page and each page is held to
 * `lib/checklist.ts`, then each module's page object runs its own cases. Deleting this spec
 * deletes the only check that the console's pages draw against a real API and a real sign-in:
 * the console's unit tests render against fixtures and cannot see a route that 500s, a menu
 * entry pointing nowhere, or a task id printed on a page.
 */

import { expect, test, type Page } from "@playwright/test";
import { checkPage, consoleFontRequests, fontsStayOnTheInstall, reset, watch, type Watch } from "../lib/checklist";
import { addressesOf, servedNavigation, type Navigation } from "../lib/navigation";
import { signInAsAdmin } from "../lib/signin";
import { openFromMenu } from "../pages/module";
import { MODULE_PAGES } from "../pages/index";

test.describe.configure({ mode: "serial" });

let page: Page;
let seen: Watch;
let navigation: Navigation;

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage();
  seen = watch(page);
  const served = servedNavigation(page);
  await signInAsAdmin(page);
  navigation = await served;
});

test.afterAll(async () => {
  await page.close();
});

test("every module the menu serves has a page object", () => {
  const groups = navigation.sections.map((section) => section.group);
  expect(groups.length, "the administrator is served a menu").toBeGreaterThan(0);
  expect(groups.filter((group) => !MODULE_PAGES.has(group)), "modules with no page object").toEqual([]);
});

for (const [group, module] of MODULE_PAGES) {
  test(`every page in the ${group} module passes the checklist, and the module's own cases pass`, async ({}, info) => {
    const section = navigation.sections.find((one) => one.group === group);
    expect(section, `the administrator's menu has the ${group} module`).toBeDefined();
    for (const address of section ? addressesOf(section) : []) {
      reset(seen);
      await openFromMenu(page, address.to, section?.heading);
      await checkPage(page, seen, `${address.label} (${address.to})`, info);
    }
    reset(seen);
    await module.cases(page);
  });
}

test("every font the console drew was fetched from the install, and the console did draw some", () => {
  // Deleting this leaves "no request leaves the install" judged page by page after `reset`, which
  // never sees the font request: it is made once, by the first page that draws with the font, and
  // that page's list is cleared before it is judged. The count is asserted too, so a console that
  // loaded no font at all (and so asked no host for one) is not read as a pass.
  expect(consoleFontRequests(seen).length, "the console's pages loaded at least one font").toBeGreaterThan(0);
  expect(fontsStayOnTheInstall(seen), "no console font was fetched from another host").toEqual([]);
});
