/**
 * Furnishing the install: the first run, in the browser, by an administrator with a second factor.
 *
 * Everything after this spec reads what it wrote, so it is the `furnish` project the others
 * depend on. Deleting it leaves every console spec signing in to an install nobody set up, which
 * shows the first-run page on every address and fails all of them for one cause.
 *
 * What it proves on its own: the setup code the job minted beside the install's instant is the
 * code the wizard accepts (`brain.firstrun.derived_enrolment`), the wizard's own screens appoint
 * the person who signed in, and the realm asked that person for a one-time code.
 */

import { expect, test } from "@playwright/test";
import { ADMIN, READER, setupCode } from "../lib/people";
import { answerSignIn } from "../lib/signin";

const COMPANY = "Harness Company";

/** Fill one wizard field by the id `console/src/pages/FirstRun.tsx` gives it. */
function field(screen: string, question: string): string {
  return `#first-run-${screen}-${question}`;
}

test("the first administrator sets the install up in the browser with a second factor", async ({ page, request }) => {
  await page.goto("/first-run");
  await page.getByRole("button", { name: "Sign in to begin" }).click();
  const token = await answerSignIn(page, ADMIN, ADMIN.codeSecret);

  const next = (): Promise<void> => page.getByRole("button", { name: "Continue" }).click();
  await page.locator(field("setup_code", "setup_code")).fill(setupCode());
  await next();
  await page.locator(field("company", "company_name")).fill(COMPANY);
  await page.locator(field("company", "web_address")).fill(new URL(page.url()).origin);
  await next();
  await page.locator(field("administrator", "full_name")).fill(ADMIN.fullName);
  await page.locator(field("administrator", "work_address")).fill(ADMIN.email);
  await next();
  await page.locator(field("data_steward", "steward_full_name")).fill(READER.fullName);
  await page.locator(field("data_steward", "steward_work_address")).fill(READER.email);
  await page.locator(field("data_steward", "steward_is_administrator")).selectOption("no");
  await next();
  await page.locator(field("staff_source", "staff_source")).selectOption("spreadsheet");
  await next();
  await page.locator(field("model_provider", "model_profile")).selectOption("local");
  await next();
  await page.getByRole("button", { name: "Skip this screen" }).click();
  await page.getByRole("button", { name: "Set up this system" }).click();

  const opened = page.getByRole("button", { name: "Open the console" });
  const menu = page.locator('nav[aria-label="Sections"]');
  await expect(opened.or(menu), "the wizard finished").toBeVisible({ timeout: 60_000 });
  if (await opened.isVisible()) {
    await opened.click();
  }
  await expect(menu, "the console opens for the new administrator").toBeVisible({ timeout: 30_000 });

  // The steward the wizard named is a person with no sign-in yet. Linking the reader's account to
  // them is what lets the console specs sign in as somebody who is not an administrator.
  const auth = { Authorization: `Bearer ${token}` };
  const directory = await request.get("/api/v1/govern/directory", { headers: auth });
  expect(directory.status(), "the directory answers the administrator").toBe(200);
  const listed = (await directory.json()) as { items: { principal_id: string; display_name: string }[] };
  const steward = listed.items.find((one) => one.display_name === READER.fullName);
  expect(steward, "the data steward is in the directory").toBeDefined();
  const linked = await request.post("/api/v1/sign-ins", {
    headers: auth,
    data: { subject: READER.subject, principal_id: steward?.principal_id ?? "" },
  });
  expect(linked.status(), "the reader's account is linked to the steward").toBe(200);
  expect(((await linked.json()) as { outcome: string }).outcome).toMatch(/^(bound|already_bound)$/);
});
