/**
 * Every list page offers the management tools an enterprise console has, or says why it does not:
 * selection and bulk acts, export of what the reader may see, saved filters, column choice and a
 * detail drawer, and never a total, so that DENIED and ABSENT stay one thing.
 *
 * **What counts as a list is read from the page, not claimed.** Every page the console registers is
 * mounted through the real route table and shell with the stand-in API of `support/pageCases.ts`,
 * the same fixtures `screen-states` and `phone-width` use, and every `[data-slot='entity-table']` it
 * draws is a list. A table that is drawn gets each tool or a named reason:
 *
 * - **column choice**: a "Columns" menu, always, because it costs the table nothing.
 * - **export**: an "Export" button whose file holds exactly the rows drawn, in the columns shown. It is
 *   pressed here and the file read, because a button over columns with no text accessor exports a
 *   header and nothing under it.
 * - **selection**: the header box and a box per row, which exist whenever there is export, because
 *   exporting the selected rows is a bulk act over a selection that reads and changes nothing.
 * - **bulk acts that change something**: only where a route takes a set (`OFFERS_A_BULK_ACT`). Every
 *   other list is named in `NO_BULK_ACT` with why, and a list that has one may not also be excused.
 * - **detail drawer**: a control on every row that opens it, or the table says why not on itself
 *   (`withoutDetail`).
 * - **saved filters**: on every narrowing control a list has. A list answered whole has none, which is
 *   read from the page and not assumed, and the few narrowing forms that are not a list's own are named
 *   in `NARROWS_NOTHING_WORTH_SAVING`.
 *
 * **No tool may say how many rows were hidden.** What each list draws outside its rows is held to the
 * phrasings of a count of rows, pages, results or a selection, which `ui-rules.test.ts` holds the
 * component layer to as well. The reader's own tick count is the only number allowed, and it is absent
 * until they tick.
 *
 * Task ids: M27.16.3
 */

import { cleanup, fireEvent, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, test } from "vitest";
import { PAGES } from "./support/pageCases";
import { ASKS_NOTHING_ON_ARRIVAL } from "./support/screenStateRules";
import { COMPANY_CONSOLE, NAVIGATION_ADDRESS } from "./support/navigation";
import { mountIn } from "./support/screenStates";

const LISTED = Object.keys(PAGES).filter((pattern) => !(pattern in ASKS_NOTHING_ON_ARRIVAL));

// ------------------------------------------------------------------------------- the reasons

const READ_ONLY =
  "Nothing on this list is written from the console, so there is no act to do to many rows at once; " +
  "the selection exports.";
const ONE_ROW_AT_A_TIME =
  "Every write on this list is about one row and is confirmed on its own, because deciding or " +
  "changing several at once would change rows nobody read; the selection exports. See " +
  "`long-lists.test.tsx` for the same rule over the long lists.";
const AN_UNBINDING_IS_ONE_PERSONS_CHAT =
  "Unbinding stops a chat account being answered as its person, at once, and is recorded against " +
  "them; it is confirmed one person at a time so nobody's chat is taken away as a side effect of " +
  "somebody else's; the selection exports.";
const ONE_THING_IS_DRAWN =
  "This page is about one thing and the list is one of its sections, so there is no set of things to " +
  "act on together; the selection exports.";

/**
 * Lists whose export is the page's own and is more than the rows drawn, so the table carries none.
 * Checked: the page must draw an Export button of its own, and the table must not draw a second.
 */
const EXPORTS_ITSELF: Readonly<Record<string, string>> = {
  "/logs":
    "The log is exported by the server over the whole period asked for, and says when the file was cut " +
    "off, which is more than the rows drawn; a second button over the rows drawn would be two exports " +
    "of one list that disagree.",
};

/** A report page saves the tables it shows through its own Export, named for the report and the period. */
const A_REPORT_SAVES_ITS_OWN_TABLES =
  "The report's own Export saves the tables the page shows, named for the report and the period; a " +
  "second button over one table would be two exports of one list, and the browser case that reads the " +
  "report's file would find two buttons of one name.";
for (const pattern of ["/service-levels", "/quality", "/questions", "/adoption"]) {
  (EXPORTS_ITSELF as Record<string, string>)[pattern] = A_REPORT_SAVES_ITS_OWN_TABLES;
}

/** The pages that have a bulk act that changes something, which a route takes as a set. */
const OFFERS_A_BULK_ACT: ReadonlySet<string> = new Set(["/access_review", "/library", "/people", "/sessions"]);

/**
 * Why each other list page has no bulk act that changes anything, by the address it is mounted at.
 * Checked in both directions: an entry whose page now has a bulk act is refused, and so is a list page
 * with no entry.
 */
const NO_BULK_ACT: Readonly<Record<string, string>> = {
  "/access-requests": ONE_ROW_AT_A_TIME,
  "/adoption": READ_ONLY,
  "/agent-templates": ONE_ROW_AT_A_TIME,
  "/agents": ONE_ROW_AT_A_TIME,
  "/agents/drafts": ONE_ROW_AT_A_TIME,
  "/artifacts": READ_ONLY,
  "/audit": READ_ONLY,
  "/audit/subject/:kind/:id": READ_ONLY,
  "/audit/subject/:kind/:id/:view": READ_ONLY,
  "/automations": ONE_ROW_AT_A_TIME,
  "/capabilities": READ_ONLY,
  "/channels": ONE_ROW_AT_A_TIME,
  "/channels/:name": AN_UNBINDING_IS_ONE_PERSONS_CHAT,
  "/company/estate": READ_ONLY,
  "/company/activity": READ_ONLY,
  "/compliance": ONE_ROW_AT_A_TIME,
  "/compliance/:view": ONE_ROW_AT_A_TIME,
  "/connections": READ_ONLY,
  "/connectors": ONE_ROW_AT_A_TIME,
  "/credentials": ONE_ROW_AT_A_TIME,
  "/departments": ONE_ROW_AT_A_TIME,
  "/elevation": ONE_ROW_AT_A_TIME,
  "/errors": READ_ONLY,
  "/import-export": READ_ONLY,
  "/incidents": READ_ONLY,
  "/jobs": ONE_ROW_AT_A_TIME,
  "/jobs/:name": ONE_THING_IS_DRAWN,
  "/learning": ONE_ROW_AT_A_TIME,
  "/learning/:view": ONE_ROW_AT_A_TIME,
  "/limits": ONE_ROW_AT_A_TIME,
  "/logs": READ_ONLY,
  "/memory/:subject": ONE_ROW_AT_A_TIME,
  "/memory/:subject/:view": ONE_ROW_AT_A_TIME,
  "/notifications": ONE_ROW_AT_A_TIME,
  "/packs": ONE_ROW_AT_A_TIME,
  "/quality": READ_ONLY,
  "/questions": READ_ONLY,
  "/recovery": READ_ONLY,
  "/referrals": ONE_ROW_AT_A_TIME,
  "/requirement-checks": ONE_ROW_AT_A_TIME,
  "/retention": ONE_ROW_AT_A_TIME,
  "/retention/:view": ONE_ROW_AT_A_TIME,
  "/roles": ONE_ROW_AT_A_TIME,
  "/runs": READ_ONLY,
  "/scopes": ONE_ROW_AT_A_TIME,
  "/service-accounts": ONE_ROW_AT_A_TIME,
  "/service-levels": READ_ONLY,
  "/sign-in-links": ONE_ROW_AT_A_TIME,
  "/skills": ONE_ROW_AT_A_TIME,
  "/storage": READ_ONLY,
  "/subscribers": READ_ONLY,
  "/tools": READ_ONLY,
  "/webhooks": ONE_ROW_AT_A_TIME,
  "/webhooks/:id": ONE_THING_IS_DRAWN,
};

/**
 * The lists that draw a count beside the rows, and why it is not a count of rows somebody was not
 * shown. A count of a register everybody who can open the page reads whole hides nothing.
 */
const COUNTS_THAT_HIDE_NOTHING: Readonly<Record<string, string>> = {
  "/requirement-checks":
    "The register is the product's own list of requirements, the same on every install and for every " +
    "reader of this screen, so 1 of 2 recorded counts rows nobody was kept from: " +
    "brain.requirement_check_routes argues it and the page says so.",
};

// ----------------------------------------------------------------------------- what is read

/** Phrasings that are a count of rows, pages, results or a selection, as `ui-rules.test.ts` reads. */
const A_COUNT = [
  /(?:\d|\})\s+of\s+(?:\d|\{)/i,
  /\brows?\(s\)/i,
  /\b(?:\d+|\{[^}]*\})\s+(?:results?|matches|more|hidden|rows?)\b/i,
  /\bpage\s+\d/i,
  /\btotal\b/i,
];

/** What each page's walk found, kept for the tests that read the whole console at the end. */
const WITH_A_LIST = new Set<string>();
const WITH_A_BULK_ACT = new Set<string>();

/** Mount the page with its usual answers and hand back what it drew, once the page has settled. */
async function mountRead(pattern: string): Promise<{ root: HTMLElement; tables: HTMLElement[]; searches: HTMLElement[] }> {
  const page = PAGES[pattern];
  if (page === undefined) {
    throw new Error(`${pattern} has no page case.`);
  }
  const mounted = await mountIn(
    pattern,
    page.address,
    { kind: "answered", answers: page.answers },
    false,
    page.answers[NAVIGATION_ADDRESS] ?? COMPANY_CONSOLE,
  );
  return {
    root: mounted.root as HTMLElement,
    tables: [...mounted.root.querySelectorAll<HTMLElement>("[data-slot='entity-table']")],
    searches: [...mounted.root.querySelectorAll<HTMLElement>("form[role='search']")],
  };
}

function rowsOf(table: HTMLElement): HTMLElement[] {
  return [...table.querySelectorAll<HTMLElement>("tbody tr")];
}

/** Press the table's Export button and read the file it made. */
async function exported(table: HTMLElement): Promise<string> {
  let made: Blob | null = null;
  const create = URL.createObjectURL;
  const revoke = URL.revokeObjectURL;
  const click = HTMLAnchorElement.prototype.click;
  URL.createObjectURL = (blob: Blob | MediaSource) => {
    made = blob as Blob;
    return "blob:export";
  };
  URL.revokeObjectURL = () => {};
  HTMLAnchorElement.prototype.click = () => {};
  try {
    fireEvent.click(within(table).getByRole("button", { name: "Export" }));
  } finally {
    URL.createObjectURL = create;
    URL.revokeObjectURL = revoke;
    HTMLAnchorElement.prototype.click = click;
  }
  if (made === null) {
    throw new Error("Pressing Export made no file.");
  }
  return await (made as Blob).text();
}

beforeAll(async () => {
  // Every split page is transformed once, before anything is timed.
  await import("../src/pages/Records");
  await import("../src/pages/Agent");
  await import("../src/pages/Approvals");
  await import("../src/pages/People");
}, 120_000);

afterEach(() => {
  cleanup();
});

/**
 * Narrowing forms that are not a list's own, and why nothing in them is worth saving. Each is a single
 * choice that is one press away from any other value, so a saved question would be the form itself.
 */
const NARROWS_NOTHING_WORTH_SAVING: Readonly<Record<string, string>> = {
  "/company/consumption":
    "The one choice is how many days of spending to read, a single value one press away from any " +
    "other, so a saved question would be the control it was saved from.",
};

describe("every list the console draws", () => {
  test.each(LISTED)("%s offers every tool on every list it draws and says no number around it", async (pattern) => {
    // What breaks if this is deleted: a list page whose reader cannot hide a column, take the rows
    // they are looking at into a spreadsheet, tick rows, open one row without leaving the list, or keep
    // a search they type every day. The first four are built into the table and a page that passes no
    // export name loses the rest silently, which is how thirty tables had none. And "3 of 47" beside a
    // list is 44 facts about rows this reader was not shown.
    const { root, tables, searches } = await mountRead(pattern);
    for (const table of tables) {
      WITH_A_LIST.add(pattern);
      const rows = rowsOf(table);
      expect(rows.length, `${pattern} drew a table with no rows`).toBeGreaterThan(0);
      expect(within(table).queryByRole("button", { name: "Columns" }), `${pattern}: no column choice`).not.toBeNull();
      if (pattern in EXPORTS_ITSELF) {
        expect(within(table).queryByRole("button", { name: "Export" }), `${pattern}: two exports of one list`).toBeNull();
        expect(within(root).queryByRole("button", { name: "Export" }), `${pattern}: the page's own export is gone`).not.toBeNull();
      } else {
        expect(within(table).queryByRole("checkbox", { name: "Select every row shown" }), `${pattern}: no selection`).not.toBeNull();
        expect(within(table).queryByRole("button", { name: "Export" }), `${pattern}: no export`).not.toBeNull();
        const file = await exported(table);
        const lines = file.split("\r\n").filter((line) => line !== "");
        expect(lines[0]?.trim().length ?? 0, `${pattern}: the export has no columns`).toBeGreaterThan(0);
        expect(lines.length - 1, `${pattern}: the export is not the rows drawn`).toBe(rows.length);
      }
      const why = table.getAttribute("data-without-detail");
      if (why === null) {
        expect(table.querySelectorAll("[data-slot='row-details']").length, `${pattern}: a row has no detail control`).toBe(rows.length);
      } else {
        expect(why.split(" ").length, `${pattern} has no detail drawer and gives no reason`).toBeGreaterThan(5);
      }

      // No number about the rows, read over everything the list draws except the rows themselves.
      const around = (table.closest("section, [data-slot='section-card']") ?? table).cloneNode(true) as HTMLElement;
      around.querySelectorAll("tbody").forEach((one) => {
        one.remove();
      });
      const text = (around.textContent ?? "").replace(/\s+/g, " ");
      if (!(pattern in COUNTS_THAT_HIDE_NOTHING)) {
        for (const phrasing of A_COUNT) {
          expect(text, `${pattern}: ${String(phrasing)}`).not.toMatch(phrasing);
        }
      }

      // Tick a row and see whether the bar offers an act beside export and clear.
      const first = table.querySelector("tbody [role='checkbox']");
      expect(first === null, `${pattern}: ${first === null ? "no row box" : "a row box beside its own export"}`).toBe(pattern in EXPORTS_ITSELF);
      if (first !== null) {
        fireEvent.click(first);
        const bar = table.querySelector("[role='region'][aria-label='Bulk actions']");
        expect(bar, `${pattern}: ticking a row drew no bar`).not.toBeNull();
        const acts = [...(bar?.querySelectorAll("button") ?? [])].filter(
          (one) => !/^(Export selected|Clear the selection)$/.test((one.getAttribute("aria-label") ?? one.textContent ?? "").trim()),
        );
        if (acts.length > 0) {
          WITH_A_BULK_ACT.add(pattern);
        }
        fireEvent.click(first);
      }
    }
    if (!(pattern in NARROWS_NOTHING_WORTH_SAVING)) {
      for (const form of searches) {
        const label = form.getAttribute("aria-label") ?? "";
        expect(
          within(form).queryByRole("button", { name: /Saved filters/ }),
          `${pattern}: the "${label}" form cannot be saved`,
        ).not.toBeNull();
      }
    }
  }, 60_000);

  test("every list names why it has no bulk act that changes something, and none is excused that has one", () => {
    // What breaks if this is deleted: a list that could offer an act over a selection and does not, or
    // an excuse that outlives the act it excused. The set that has one is read from the pages above,
    // by ticking a row and looking at what the bulk bar offers beside export and clear.
    expect([...WITH_A_BULK_ACT].sort()).toEqual([...OFFERS_A_BULK_ACT].sort());
    const unexcused = [...WITH_A_LIST].filter((pattern) => !OFFERS_A_BULK_ACT.has(pattern) && NO_BULK_ACT[pattern] === undefined);
    expect(unexcused, "lists with no bulk act and no reason for having none").toEqual([]);
    for (const [pattern, reason] of Object.entries(NO_BULK_ACT)) {
      expect(WITH_A_LIST.has(pattern), `${pattern} is excused but draws no list`).toBe(true);
      expect(OFFERS_A_BULK_ACT.has(pattern), `${pattern} is excused and also has a bulk act`).toBe(false);
      expect(reason.split(" ").length, `${pattern}: the reason is not a reason`).toBeGreaterThan(8);
    }
    // The walk found the console's lists, rather than none.
    expect(WITH_A_LIST.size).toBeGreaterThan(40);
  });

  test("a page excused from the count rule still draws a count, so an excuse is never left behind", async () => {
    // What breaks if this is deleted: the count rule is switched off for a page by an entry that stays
    // after the count is gone, so the next count added there is waved through.
    for (const pattern of Object.keys(COUNTS_THAT_HIDE_NOTHING)) {
      const { tables } = await mountRead(pattern);
      const text = tables
        .map((table) => (table.closest("section, [data-slot='section-card']") ?? table).textContent ?? "")
        .join(" ")
        .replace(/\s+/g, " ");
      expect(A_COUNT.some((phrasing) => phrasing.test(text)), `${pattern} no longer draws a count`).toBe(true);
    }
  }, 60_000);

  test("the pages excused from saving a filter really do draw one choice and no more", async () => {
    // What breaks if this is deleted: "nothing worth saving" is claimed for a form that has a search
    // box and several choices, which would then have no saved filters and no real reason.
    for (const pattern of Object.keys(NARROWS_NOTHING_WORTH_SAVING)) {
      expect(PAGES[pattern], `${pattern} is excused but is not a page`).toBeDefined();
      const { searches } = await mountRead(pattern);
      expect(searches.length, `${pattern} draws ${String(searches.length)} narrowing forms`).toBe(1);
      const form = searches[0] as HTMLElement;
      expect(form.querySelectorAll("select").length).toBe(1);
      expect(form.querySelectorAll("input").length).toBe(0);
    }
  }, 60_000);
});
