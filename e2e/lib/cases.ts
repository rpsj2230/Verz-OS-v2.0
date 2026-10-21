/**
 * The cases every module's pages are proved by in the browser, the same ones for every module.
 *
 * `lib/checklist.ts` holds a page to what must be true of any page as drawn. These are the
 * situations a person meets and a unit test over fixtures cannot make: a narrow screen, an API
 * that answers slowly, one that answers with a fault, one that cannot be reached, a search that
 * finds nothing, and a keyboard. Each is made with the browser's own request interception on the
 * page's data and with nothing on the server changed, so a case needs no write and leaves nothing
 * behind. The module-specific writes (create, edit, retire) are not here: they change an install
 * the other specs read, and each is proved where its screen is.
 *
 * **Four different sentences, held apart.** `docs/admin-console.md` asks every screen to tell
 * loading, empty, unreachable and failed apart, and `console/tests/screen-states.test.tsx` holds
 * that in jsdom. Here the browser draws the real page: a delayed answer says it is loading, an
 * unreachable API says the Brain could not be reached, a fault says that did not work, and the
 * two are different headings.
 *
 * **What is intercepted is the page's data and not the shell's.** The shell reads who is signed in
 * and the menu, and failing those would test the shell on every page. They pass through.
 *
 * Task ids: M27.14.1, M27.14.2, M27.14.3, M27.14.4, M27.14.5, M27.14.6, M27.14.7, M27.14.8
 */

import { expect, type Page, type Route } from "@playwright/test";

/** What the shell reads for itself on every page, left alone by every case. */
const SHELL_PATHS: readonly string[] = ["/api/v1/me", "/api/v1/console/navigation"];

/** The pattern every page's data comes by. */
const DATA = "**/api/v1/**";

/** The headings a fault the API answered is drawn under (`console/src/ui/FailureNotice.tsx`). */
export const FAULT_HEADINGS: readonly string[] = ["That did not work", "Something did not work"];

/** The heading for a request that never reached the API. */
export const UNREACHABLE_HEADING = "The Brain could not be reached";

/** What a narrowed list says when a search matches nothing (`console/src/components/ListControls.tsx`). */
export const NOTHING_MATCHES = "Nothing here matches that search or filter.";

/** The control that clears a search and the filters (`console/src/components/kit/ListToolbar.tsx`). */
export const RESET_LABEL = "Clear search and filters";

/** The menu button a narrow screen opens the menu with (`console/src/layout/ConsoleSidebar.tsx`). */
export const MENU_BUTTON = "Menu";

/** One page of a module, as the served menu gives it. */
export interface Target {
  readonly to: string;
  readonly label: string;
  readonly heading: string;
  /** The menu entry the page sits under: its own address for an entry, or the entry's for a tab. */
  readonly entry: string;
}

const SIDEBAR = 'nav[aria-label="Sections"]';

/**
 * Open `target` as a person does: its entry in the menu, then its tab when it is one.
 *
 * The menu is looked for inside the sidebar and nowhere else, because a module's tabs link to the
 * entry's own address too and the first link in the document is then the tab. A group that is
 * folded is unfolded first. `narrow` opens the menu button first, which is the only way to the menu
 * at the width of a phone.
 */
export async function openTarget(page: Page, target: Target, narrow = false): Promise<void> {
  const link = page.locator(`${SIDEBAR} a[href="${target.entry}"]`).first();
  const group = page.locator(SIDEBAR).getByRole("button", { name: target.heading, exact: true });
  if (narrow && !(await group.isVisible())) {
    // On a phone the menu is a drawer behind its button, which is pressed only while it is shut.
    await page.getByRole("button", { name: MENU_BUTTON, exact: true }).click();
  }
  await expect(link, `${target.label}: the menu has an entry for it`).toBeAttached({ timeout: 20_000 });
  // The drawer slides in, and its groups are not there to be asked about until it has.
  await expect(group, `${target.label}: its group is in the menu`).toBeVisible({ timeout: 10_000 });
  for (let attempt = 0; attempt < 5 && !(await link.isVisible()); attempt += 1) {
    if ((await group.getAttribute("aria-expanded")) !== "true") {
      await group.click();
    }
    await page.waitForTimeout(300);
  }
  await expect(link, `${target.label}: the entry can be seen`).toBeVisible({ timeout: 10_000 });
  await link.click();
  await expect(page).toHaveURL((url) => url.pathname === target.entry, { timeout: 20_000 });
  if (target.to !== target.entry) {
    const tab = page.locator(`main#main a[href="${target.to}"]`).first();
    await expect(tab, `${target.label}: its tab is offered`).toBeVisible({ timeout: 20_000 });
    await tab.click();
    await expect(page).toHaveURL((url) => url.pathname === target.to, { timeout: 20_000 });
  }
}

function isShell(url: string): boolean {
  return SHELL_PATHS.includes(new URL(url).pathname);
}

/** Answer the page's data requests with `answer`, and the shell's with the real thing. */
async function intercepting(page: Page, answer: (route: Route) => Promise<void>): Promise<void> {
  await page.route(DATA, async (route) => {
    if (route.request().method() !== "GET" || isShell(route.request().url())) {
      await route.continue();
      return;
    }
    await answer(route);
  });
}

/** Stand on a page other than `target`, so that opening `target` asks for its data afresh. */
async function standElsewhere(page: Page, target: Target, others: readonly Target[]): Promise<void> {
  const away = others.find((one) => one.entry !== target.entry);
  if (away === undefined) {
    throw new Error("a module with one entry has nowhere to stand but on it");
  }
  await openTarget(page, away);
}

/** The main region of the page, which every case reads. */
function mainOf(page: Page) {
  return page.locator("main#main");
}

/**
 * A slow answer is said to be loading.
 *
 * The page's data is held for a few seconds before it is let through, and while it is held the
 * page says it is loading in words; once it is let through the page draws and the saying goes.
 */
export async function proveLoadingIsSaid(page: Page, target: Target, others: readonly Target[]): Promise<void> {
  await standElsewhere(page, target, others);
  // Let what the page we stand on asked for arrive first, so the only requests held are the target's.
  await page.waitForTimeout(1_500);
  let held = 0;
  await intercepting(page, async (route) => {
    held += 1;
    await new Promise((resolve) => setTimeout(resolve, 4_000));
    await route.continue().catch(() => undefined);
  });
  try {
    await openTarget(page, target);
    await expect(mainOf(page).getByText(/\bLoading\b/i).first(), `${target.label}: says it is loading while it waits`).toBeVisible({
      timeout: 3_500,
    });
    expect(held, `${target.label}: the page's data was held while it said so`).toBeGreaterThan(0);
  } finally {
    await page.unroute(DATA);
  }
  await expect(mainOf(page).getByText(/\bLoading\b/i), `${target.label}: stops saying so once it has drawn`).toHaveCount(0, {
    timeout: 20_000,
  });
}

/**
 * The pages that send no request when they are opened, and so have no failure to say.
 *
 * The same pages, for the same reason, as `ASKS_NOTHING_ON_ARRIVAL` in
 * `console/tests/support/screenStateRules.tsx`, where each is mounted against an API that fails
 * everything and fails the test if it sends a request, so the list cannot be added to to excuse a
 * page. Fields and records waits to be told which table, and Memory whose memory.
 */
export const ASKS_NOTHING_ON_OPENING: ReadonlySet<string> = new Set(["/classification", "/memory"]);

async function openingWith(
  page: Page,
  target: Target,
  others: readonly Target[],
  answer: (route: Route) => Promise<void>,
): Promise<boolean> {
  await standElsewhere(page, target, others);
  await intercepting(page, answer);
  try {
    await openTarget(page, target);
    await expect(mainOf(page).getByRole("heading", { level: 1 }).first()).toBeVisible({ timeout: 20_000 });
  } catch (error) {
    await page.unroute(DATA);
    throw error;
  }
  return !ASKS_NOTHING_ON_OPENING.has(target.to);
}

/** A fault the API answers is said, under a heading of its own, with a reference. */
export async function proveFailureIsSaid(page: Page, target: Target, others: readonly Target[]): Promise<boolean> {
  const asked = await openingWith(page, target, others, (route) =>
    route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ message: "A made-up fault.", trace_id: "e2e-fault" }) }),
  );
  try {
    if (asked) {
      const said = mainOf(page).getByText(new RegExp(`^(${FAULT_HEADINGS.join("|")})$`)).first();
      await expect(said, `${target.label}: a fault is said under a heading of its own`).toBeVisible({ timeout: 20_000 });
      await expect(mainOf(page).getByText(UNREACHABLE_HEADING, { exact: true }), `${target.label}: a fault is not an unreachable API`).toHaveCount(0);
    }
  } finally {
    await page.unroute(DATA);
  }
  return asked;
}

/** An API that cannot be reached is said so, which is not the same as a fault. */
export async function proveUnreachableIsSaid(page: Page, target: Target, others: readonly Target[]): Promise<boolean> {
  const asked = await openingWith(page, target, others, (route) => route.abort("failed"));
  try {
    if (asked) {
      await expect(
        mainOf(page).getByText(UNREACHABLE_HEADING, { exact: true }).first(),
        `${target.label}: an unreachable API is said so`,
      ).toBeVisible({ timeout: 20_000 });
    }
  } finally {
    await page.unroute(DATA);
  }
  return asked;
}

/**
 * A search that finds nothing is said, and clearing it brings the list back.
 *
 * Only a page that offers a search and holds rows to narrow is asked: a list with nothing in it
 * says it is empty, which is another sentence and another case. Returns whether the page offered
 * one, so a module can say how many of its pages were asked.
 */
export async function proveSearchNarrowsAndClears(page: Page, target: Target): Promise<boolean> {
  const search = mainOf(page).locator('[role="search"] input[type="search"]').first();
  const rows = mainOf(page).locator("table tbody tr");
  if ((await search.count()) === 0 || (await rows.count()) === 0) {
    return false;
  }
  await search.fill("zzzz-nothing-is-called-this-zzzz");
  await expect(mainOf(page).getByText(NOTHING_MATCHES).first(), `${target.label}: a search that finds nothing says so`).toBeVisible({
    timeout: 20_000,
  });
  await mainOf(page).getByRole("button", { name: RESET_LABEL }).first().click();
  await expect(mainOf(page).getByText(NOTHING_MATCHES), `${target.label}: clearing the search brings the list back`).toHaveCount(0, {
    timeout: 20_000,
  });
  return true;
}

/**
 * At the width of a phone every action is reachable and the page does not scroll sideways.
 *
 * The menu is behind a button, opened to reach the page, and the document is no wider than the
 * screen: a table that is too wide scrolls inside its card (M27.15 plan, "Responsive").
 */
export async function provePhoneWidth(page: Page, target: Target): Promise<void> {
  const before = page.viewportSize();
  await page.setViewportSize({ width: 375, height: 812 });
  try {
    await expect(
      page.getByRole("button", { name: MENU_BUTTON, exact: true }),
      `${target.label}: the menu has a button at this width`,
    ).toBeVisible({ timeout: 20_000 });
    await openTarget(page, target, true);
    await expect(mainOf(page).getByRole("heading", { level: 1 }).first(), `${target.label}: a heading at phone width`).toBeVisible({
      timeout: 20_000,
    });
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `${target.label}: the page does not scroll sideways at 375 pixels`).toBeLessThanOrEqual(1);
  } finally {
    if (before !== null) {
      await page.setViewportSize(before);
    }
  }
}

/** The first control a keyboard reaches is the way past the menu, and it works. */
export async function proveKeyboardSkipsTheMenu(page: Page): Promise<void> {
  const skip = page.locator("a.skip-link");
  await skip.focus();
  await expect(skip, "the skip link can be focused and is shown when it is").toBeVisible();
  await page.keyboard.press("Enter");
  expect(await page.evaluate(() => window.location.hash), "following it goes to the page's content").toBe("#main");
}
