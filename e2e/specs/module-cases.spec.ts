/**
 * Every module of the console proved in the browser by the same cases (M27.14.1 to M27.14.8).
 *
 * `modules.spec.ts` holds each page to the checklist as drawn; this makes the situations a person
 * meets (`lib/cases.ts`) and asks the same of every module: a slow answer is said to be loading, a
 * fault is said under its own heading, an unreachable API under another, a search that finds
 * nothing says so and clears, a narrow screen reaches every page without scrolling sideways, and a
 * keyboard gets past the menu. The module groups are the leaves' own: Home with People and access,
 * Agents and AI, Knowledge and data, Channels and notifications, Operations, Governance, Reports
 * and Platform.
 *
 * **Writes are not made here.** A create, an edit or a retirement changes an install the other
 * specs read in order, and each is proved on its own screen. What this proves is that every page
 * of every module behaves under the situations that need no write, on a real API and a real
 * sign-in, which a unit test over fixtures cannot see. Deleting this leaves the leaves with only
 * the checklist, which says a page draws and nothing about how it fails.
 *
 * Task ids: M27.14.1, M27.14.2, M27.14.3, M27.14.4, M27.14.5, M27.14.6, M27.14.7, M27.14.8
 */

import { expect, test, type Page } from "@playwright/test";
import { reset, watch, type Watch } from "../lib/checklist";
import {
  proveFailureIsSaid,
  proveKeyboardSkipsTheMenu,
  proveLoadingIsSaid,
  openTarget,
  provePhoneWidth,
  proveSearchNarrowsAndClears,
  proveUnreachableIsSaid,
  type Target,
} from "../lib/cases";
import { addressesOf, servedNavigation, type Navigation } from "../lib/navigation";
import { signInAsAdmin } from "../lib/signin";
import { MODULE_PAGES } from "../pages/index";

test.describe.configure({ mode: "serial" });

/** The leaf each module group is proved under. Home and People and access share the first. */
const LEAF: Readonly<Record<string, string>> = {
  home: "M27.14.1",
  people: "M27.14.1",
  agents: "M27.14.2",
  knowledge: "M27.14.3",
  channels: "M27.14.4",
  operations: "M27.14.5",
  governance: "M27.14.6",
  reports: "M27.14.7",
  platform: "M27.14.8",
};

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

test("every module group the menu serves is proved under a leaf", () => {
  const groups = navigation.sections.map((section) => section.group);
  expect(groups.filter((group) => LEAF[group] === undefined), "module groups with no leaf").toEqual([]);
  expect([...MODULE_PAGES.keys()].filter((group) => LEAF[group] === undefined), "page objects with no leaf").toEqual([]);
});

for (const group of MODULE_PAGES.keys()) {
  test(`${LEAF[group] ?? group}: the ${group} module's pages fail, load, search and fit a phone as every module's do`, async ({}, info) => {
    const section = navigation.sections.find((one) => one.group === group);
    expect(section, `the administrator's menu has the ${group} module`).toBeDefined();
    if (section === undefined) {
      return;
    }
    const entries = new Set(section.entries.map((entry) => entry.to));
    const targets: Target[] = addressesOf(section).map((one) => ({
      ...one,
      heading: section.heading,
      entry: entries.has(one.to) ? one.to : (section.entries.find((entry) => entry.tabs.some((tab) => tab.to === one.to))?.to ?? one.to),
    }));
    expect(targets.length, `the ${group} module has a page to prove`).toBeGreaterThan(0);
    const [first] = targets;
    expect(section.entries.length, `the ${group} module has more than one entry to stand on and prove`).toBeGreaterThan(1);
    const searched: string[] = [];
    const waiting: string[] = [];

    for (const target of targets) {
      reset(seen);
      await openTarget(page, target);
      await expect(page.locator("main#main").getByRole("heading", { level: 1 }).first()).toBeVisible({ timeout: 20_000 });
      if (await proveSearchNarrowsAndClears(page, target)) {
        searched.push(target.label);
      }
      const asking = await proveFailureIsSaid(page, target, targets);
      await proveUnreachableIsSaid(page, target, targets);
      if (!asking) {
        waiting.push(target.label);
      }
      if (target === first) {
        await proveLoadingIsSaid(page, target, targets);
      }
      reset(seen);
      await provePhoneWidth(page, target);
    }
    if (group === "home") {
      await proveKeyboardSkipsTheMenu(page);
    }
    info.annotations.push({ type: "asks nothing on opening", description: `${group}: ${waiting.join(", ") || "none"}` });
    info.annotations.push({ type: "searched", description: `${group}: ${searched.join(", ") || "no page held rows to search"}` });
  });
}
