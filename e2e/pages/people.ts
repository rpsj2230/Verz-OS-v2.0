/**
 * People and access: the furnished install's two people are listed by name.
 *
 * The wizard named the administrator and a different data steward, so a directory that lists one
 * of them and not the other has lost a principal the setup made.
 *
 * Task ids: M27.10.6
 */

import { expect } from "@playwright/test";
import { ADMIN, READER } from "../lib/people";
import { openFromMenu, type ModulePage } from "./module";

export const people: ModulePage = {
  group: "people",
  cases: async (page) => {
    await openFromMenu(page, "/people", "People and access");
    const main = page.locator("main#main");
    await expect(main.getByText(ADMIN.fullName).first(), "the administrator is listed").toBeVisible({ timeout: 20_000 });
    await expect(main.getByText(READER.fullName).first(), "the data steward is listed").toBeVisible();
  },
};
