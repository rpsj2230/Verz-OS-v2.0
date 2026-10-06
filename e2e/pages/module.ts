/**
 * What a page object is here: one per module group of the console's menu.
 *
 * The group is `brain.console.screens.ModuleGroup`, the stable key the navigation API serves
 * beside each heading. Every page in a group is held to `lib/checklist.ts` by `specs/modules.spec.ts`;
 * a page object adds what is true of its own module on a furnished install and of no other.
 *
 * **Opened from the menu, never by typing an address.** The console keeps its tokens in memory, so
 * a reload is a fresh sign-in; clicking the menu is also what a person does, and a menu entry that
 * points nowhere is one of the failures this finds.
 *
 * Task ids: M27.10.6
 */

import { expect, type Page } from "@playwright/test";

export interface ModulePage {
  /** The module group's key, as `GET /api/v1/console/navigation` serves it. */
  readonly group: string;
  /** This module's own cases, after every page in it has passed the checklist. */
  readonly cases: (page: Page) => Promise<void>;
}

/**
 * Open `to` from the console's menu or from a module's own tabs.
 *
 * The menu's groups fold, and a folded group keeps its links in the page but hidden, so a link
 * that is there and not visible is opened by unfolding the group named `heading` first, as a
 * person would. A link that stays hidden after that is a failure of the menu, not of the spec.
 */
export async function openFromMenu(page: Page, to: string, heading?: string): Promise<void> {
  const link = page.locator(`a[href="${to}"]`).first();
  await expect(link, `a link to ${to}`).toBeAttached({ timeout: 20_000 });
  if (!(await link.isVisible()) && heading !== undefined) {
    const group = page
      .locator('nav[aria-label="Sections"]')
      .getByRole("button", { name: heading, exact: true });
    if ((await group.getAttribute("aria-expanded")) !== "true") {
      await group.click();
    }
  }
  await expect(link, `the link to ${to} can be seen`).toBeVisible({ timeout: 10_000 });
  await link.click();
  await expect(page).toHaveURL((url) => url.pathname === to, { timeout: 20_000 });
}

/** The heading of the page at `to`, opened from the menu. */
export async function headingAt(page: Page, to: string): Promise<string> {
  await openFromMenu(page, to);
  const heading = page.locator("main#main").getByRole("heading", { level: 1 }).first();
  await expect(heading).toBeVisible({ timeout: 20_000 });
  return heading.innerText();
}

/** A module whose only cases are the checklist's, said once rather than nine times. */
export function checklistOnly(group: string): ModulePage {
  return { group, cases: async () => undefined };
}
