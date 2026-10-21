/**
 * The browser cases excuse only the pages the console's own tests have already shown ask nothing.
 *
 * `e2e/lib/cases.ts` makes a page's data fail and asserts the page says so, except for the pages
 * that send no request on opening. That exemption is a second copy of
 * `ASKS_NOTHING_ON_ARRIVAL`, which is checked (each page there is mounted against an API that
 * fails everything and fails the test if it sends a request), so the copy is held to the original
 * from here: a page cannot be excused in the browser by adding it to the list in one place only.
 *
 * Task ids: M27.14.1, M27.14.2, M27.14.3, M27.14.4, M27.14.5, M27.14.6, M27.14.7, M27.14.8
 */

import { describe, expect, test } from "vitest";
import { readRepoFile } from "./support/repo";
import { ASKS_NOTHING_ON_ARRIVAL } from "./support/screenStateRules";

function excusedInTheBrowser(): string[] {
  const source = readRepoFile("e2e/lib/cases.ts");
  const found = /ASKS_NOTHING_ON_OPENING: ReadonlySet<string> = new Set\(\[([^\]]*)\]\)/.exec(source);
  if (found === null) {
    throw new Error("e2e/lib/cases.ts no longer declares ASKS_NOTHING_ON_OPENING as a set of addresses");
  }
  return [...(found[1] as string).matchAll(/"([^"]+)"/g)].map((one) => one[1] as string);
}

describe("the pages the browser cases excuse", () => {
  test("every one is a page the console's own tests have shown asks nothing on arrival", () => {
    // What breaks if this is deleted: a page that does ask is added to the browser's list to make a
    // case pass, and the failure sentence it should say is never held in the browser again.
    const excused = excusedInTheBrowser();
    expect(excused.length).toBeGreaterThan(0);
    expect(excused.filter((address) => !(address in ASKS_NOTHING_ON_ARRIVAL))).toEqual([]);
  });

  test("a page that is not on the list is one the cases hold to saying its failure", () => {
    // What breaks if this is deleted: the check above passes for a list that is empty or that
    // matches any address, which would excuse every page or none.
    const excused = excusedInTheBrowser();
    expect(excused).not.toContain("/people");
    expect(excused).not.toContain("/");
  });
});
