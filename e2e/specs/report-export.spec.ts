/**
 * A report's export holds what its page draws for the person exporting, and nothing more.
 *
 * Every Report page builds its export in the browser from the tables it draws
 * (`console/src/pages/reports/reportParts.tsx`), so which rows the file may hold is decided by the
 * route that answered the page, and what this spec proves is the other half: the file carries the
 * page's rows, in the page's order, and no line about any row the page did not draw. Service
 * levels is the report exported here because its lanes are the product's own and are drawn on
 * every install, a fresh one included, so the export control is always there to press. The log's
 * export is written on the server and is proved by `brain.ops.acceptance_operations_console_5`.
 *
 * Task ids: M27.15.48
 */

import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";
import { checkPage, watch } from "../lib/checklist";
import { signInAsAdmin } from "../lib/signin";
import { openFromMenu } from "../pages/module";

const REPORTS = "Reports";
const LANES = "Every lane";
const EXPORT = "Export";

/** Words a file would need to speak about rows it does not hold. */
const ABOUT_THE_REST = /\b(?:hidden|withheld|not shown|more rows|of \d+)\b/i;

/** The rows of a CSV document, quoted fields and doubled quotes included. */
function csvRows(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;
  for (let at = 0; at < text.length; at += 1) {
    const one = text[at];
    if (quoted) {
      if (one === '"' && text[at + 1] === '"') {
        field += '"';
        at += 1;
      } else if (one === '"') {
        quoted = false;
      } else {
        field += one;
      }
    } else if (one === '"') {
      quoted = true;
    } else if (one === ",") {
      row.push(field);
      field = "";
    } else if (one === "\n" || one === "\r") {
      if (one === "\r" && text[at + 1] === "\n") {
        at += 1;
      }
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += one;
    }
  }
  if (field !== "" || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows;
}

test("a report's export holds the rows its page draws and nothing about any other", async ({ page }, info) => {
  const seen = watch(page);
  await signInAsAdmin(page);
  await openFromMenu(page, "/service-levels", REPORTS);
  const table = page.getByRole("table", { name: LANES });
  await expect(table, "Service levels draws its lanes").toBeVisible({ timeout: 30_000 });
  await checkPage(page, seen, "Reports: Service levels", info);
  const drawn = await table.locator("tbody tr").count();

  const saved = page.waitForEvent("download");
  await page.getByRole("button", { name: EXPORT }).click();
  const download = await saved;
  expect(download.suggestedFilename(), "the file is named for the report").toMatch(/^service-levels-\d+-days\.csv$/);
  const text = await readFile(await download.path(), "utf8");
  const [header, ...rows] = csvRows(text.replace(/^﻿/, ""));

  expect(header?.[0], "the file's first column is the page's first").toBe("Lane");
  expect(rows.length, "the file holds as many rows as the page draws").toBe(drawn);
  for (const row of rows) {
    const lane = row[0] ?? "";
    expect(lane, "every row in the file names a lane").not.toBe("");
    await expect(table.getByRole("row").filter({ hasText: lane }).first(), `the lane ${lane} is drawn on the page`).toBeVisible();
  }
  expect(text, "the file says nothing about rows it does not hold").not.toMatch(ABOUT_THE_REST);
});
