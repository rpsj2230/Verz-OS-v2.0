/**
 * The menu the API serves this reader, read off the wire the console itself received.
 *
 * **The harness walks the served menu, not a copy of it.** `GET /api/v1/console/navigation` is
 * `brain.console.department_console.COMPANY_NAVIGATION` for an administrator, and a list kept here
 * would be the second copy the API was introduced to retire. The page-object registry is checked
 * against this, so a module added to the menu without a page object fails the run that first
 * serves it.
 *
 * Task ids: M27.10.6
 */

import type { Page, Response } from "@playwright/test";

export const NAVIGATION_PATH = "/api/v1/console/navigation";

export interface Tab {
  readonly key: string;
  readonly label: string;
  readonly to: string;
}

export interface Entry {
  readonly key: string;
  readonly label: string;
  readonly to: string;
  readonly tabs: readonly Tab[];
}

export interface Section {
  readonly group: string;
  readonly heading: string;
  readonly entries: readonly Entry[];
}

export interface Navigation {
  readonly console: string;
  readonly sections: readonly Section[];
}

function isNavigation(response: Response): boolean {
  return new URL(response.url()).pathname === NAVIGATION_PATH && response.request().method() === "GET";
}

/** Start listening before the console asks; await the result once it has. */
export function servedNavigation(page: Page): Promise<Navigation> {
  return page
    .waitForResponse(isNavigation, { timeout: 60_000 })
    .then(async (response) => (await response.json()) as Navigation);
}

/** Every address the menu opens: each entry, and each of its tabs. */
export function addressesOf(section: Section): readonly { readonly label: string; readonly to: string }[] {
  const found: { label: string; to: string }[] = [];
  for (const entry of section.entries) {
    found.push({ label: entry.label, to: entry.to });
    for (const tab of entry.tabs) {
      if (tab.to !== entry.to) {
        found.push({ label: `${entry.label}: ${tab.label}`, to: tab.to });
      }
    }
  }
  return found;
}
