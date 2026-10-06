/** Home: the console opens on it. Task ids: M27.10.6 */

import { expect } from "@playwright/test";
import { type ModulePage } from "./module";

export const home: ModulePage = {
  group: "home",
  cases: async (page) => {
    await page.locator("main#main").waitFor();
    await expect(page.locator('nav[aria-label="Sections"]'), "the menu is drawn beside home").toBeVisible();
  },
};
