/**
 * The browser harness: a furnished install, a real Chromium, the realm every install imports.
 *
 * Three projects, in order. `codes` checks the one-time-code computation against RFC 6238 and
 * needs no stack. `furnish` runs the first-run wizard in the browser as an administrator with a
 * second factor, then links the data steward's account, which is what makes the install
 * "furnished". `console` holds every page of the served menu to the checklist and runs each
 * module's own cases, and depends on `furnish`.
 *
 * **One worker, in order.** Every spec signs in to one realm whose one-time codes are used once,
 * and the console specs read what `furnish` wrote; parallel workers would race both.
 *
 * **No trace and no video.** A trace records what was typed, which is a password and a code the
 * job minted for this run, and the report is uploaded where anybody who can read the repository
 * can download it. A screenshot on failure is kept: a password field draws as dots.
 *
 * Task ids: M27.10.6
 */

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./specs",
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 240_000,
  expect: { timeout: 15_000 },
  forbidOnly: true,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: process.env["E2E_BASE_URL"] ?? "http://localhost:8000",
    // The identity provider's certificate is signed by an authority this job made a minute ago.
    ignoreHTTPSErrors: true,
    trace: "off",
    video: "off",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "codes", testMatch: /totp\.spec\.ts/ },
    { name: "furnish", testMatch: /first-run\.spec\.ts/, use: { ...devices["Desktop Chrome"] } },
    {
      name: "console",
      testMatch: /(modules|reader|two-tabs|report-export)\.spec\.ts/,
      dependencies: ["furnish"],
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
