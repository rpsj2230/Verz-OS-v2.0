/**
 * The register of console pages states only what the console's source shows.
 *
 * `docs/console-pages.json` says, for each primary page, whether it is built on the shared parts.
 * That is a claim about source, so it is held against the source here: the page file the route
 * table draws for the address, and the files it reaches inside `src/pages/`, import one of the
 * kit's page-shaping parts. The register's other two facts (a drawn screen, a walk-through) are
 * not in the source and are held by `tests/unit/test_console_pages.py`. Together they are what
 * lets `/build/pages` say which pages are rebuilt without anybody's word for it (M27.16.1,
 * M27.16.4, M27.16.5).
 *
 * Task ids: M27.16.1, M27.16.4, M27.16.5
 */

import { describe, expect, test } from "vitest";
import { importsKitPart, pageClosure, pageFiles, PAGE_SHAPING_PARTS } from "./support/pageKit";
import { readRepoFile } from "./support/repo";

interface Row {
  readonly address: string;
  readonly name: string;
  readonly on_the_shared_parts: boolean;
}

const rows = (JSON.parse(readRepoFile("docs/console-pages.json")) as { pages: Row[] }).pages;

describe("the register's statement that a page is built on the shared parts is true of the source", () => {
  test("every page the register lists is drawn by a page file, and that file reaches a kit page part exactly when the row says so", () => {
    // What breaks if this is deleted: a row that says a page is on the shared parts when its source
    // never imports them, or the reverse, so /build/pages counts pages rebuilt on somebody's word.
    const files = pageFiles();
    const wrong: string[] = [];
    for (const row of rows) {
      const entry = files.get(row.address);
      if (entry === undefined) {
        wrong.push(`${row.address}: no page file is drawn at this address`);
        continue;
      }
      const reaches = pageClosure(entry).some((file) => importsKitPart(file));
      if (reaches !== row.on_the_shared_parts) {
        wrong.push(`${row.address}: the row says ${String(row.on_the_shared_parts)} and the source says ${String(reaches)}`);
      }
    }
    expect(wrong).toEqual([]);
  });

  test("the register lists the pages, and the three parts that give a page its shape are the ones counted", () => {
    // What breaks if this is deleted: the other test holds for a register of no rows, and for a
    // list of parts emptied to make every page pass.
    expect(rows.length).toBeGreaterThan(30);
    expect([...PAGE_SHAPING_PARTS]).toEqual(["PageHeader", "ListPage", "DetailPage"]);
  });

  test("a page's closure stays inside the pages folder, so a shared component cannot make a page rebuilt", () => {
    // What breaks if this is deleted: following every import answers yes for every page (nearly
    // every component reaches the kit somewhere), so the first test passes for pages that were
    // never rebuilt. Held on a page whose imports certainly leave the folder.
    const closure = pageClosure("src/pages/People.tsx");
    expect(closure.length).toBeGreaterThan(1);
    expect(closure.filter((file) => !file.startsWith("src/pages/"))).toEqual([]);
  });

  test("a page that imports only a card from the kit is not built on the shared parts", () => {
    // What breaks if this is deleted: a helper that answered yes for any import from the kit would
    // pass the first test for every page and say nothing, since nearly every file borrows a piece.
    expect(importsKitPart("src/components/kit/ConfirmDialog.tsx", ["SectionCard"])).toBe(false);
    expect(importsKitPart("src/pages/agents/AgentDetailPage.tsx", ["DetailPage"])).toBe(true);
    expect(importsKitPart("src/pages/agents/AgentDetailPage.tsx", ["NoSuchPart"])).toBe(false);
  });
});
