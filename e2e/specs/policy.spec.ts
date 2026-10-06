/**
 * The console's style policy is stated, and a drawer opens and closes under it (M27.15.81).
 *
 * The console mounts no toaster, so its inline styles are the dialogs' and drawers' scroll lock,
 * written the moment one opens. This opens the "Link a sign-in" drawer, which is a dialog with a
 * scroll lock, and fails on anything the browser refuses under the policy the entry document
 * carries. Deleting this leaves the policy stated in a header and in a unit test, and nothing
 * showing the console still works under it.
 *
 * Task ids: M27.15.81
 */

import { expect, test } from "@playwright/test";
import { checkPage, reset, watch } from "../lib/checklist";
import { signInAsAdmin } from "../lib/signin";
import { openFromMenu } from "../pages/module";

test("the entry document states its style policy and a drawer opens and closes under it", async ({ browser }, info) => {
  const page = await browser.newPage();
  const seen = watch(page);
  const policies: string[] = [];
  page.on("response", (response) => {
    const install = new URL(process.env["E2E_BASE_URL"] ?? "http://localhost:8000").origin;
    if (response.request().resourceType() === "document" && new URL(response.url()).origin === install) {
      policies.push(response.headers()["content-security-policy"] ?? "");
    }
  });
  await signInAsAdmin(page);
  await expect(page.locator('nav[aria-label="Sections"]')).toBeVisible({ timeout: 30_000 });
  expect(policies.filter(Boolean), "the console's document carries its style policy").toContain(
    "style-src 'self' 'unsafe-inline'",
  );

  await openFromMenu(page, "/sessions", "People and access");
  await openFromMenu(page, "/sign-in-links");
  await checkPage(page, seen, "Sign-in links", info);
  reset(seen);

  await page.getByRole("button", { name: "Link a sign-in" }).first().click();
  const drawer = page.getByRole("dialog", { name: "Link a sign-in" });
  await expect(drawer, "the drawer opens").toBeVisible();
  expect(
    await page.evaluate(() => getComputedStyle(document.body).overflow),
    "the page behind the drawer stops scrolling, which is the inline style the policy keeps",
  ).toBe("hidden");
  await drawer.getByRole("button", { name: "Close" }).first().click();
  await expect(drawer, "the drawer closes").toBeHidden();
  expect(seen.refusedByPolicy, "nothing was refused under the policy").toEqual([]);
  await page.close();
});
