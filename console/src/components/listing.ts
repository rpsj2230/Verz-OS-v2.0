/**
 * The console's half of `brain.listing`: what a list asks for, and which values a filter may offer.
 * No React.
 *
 * `docs/admin-console.md` asks that long lists page, search, filter and sort. The API now does all
 * four for every list route the console draws a long list from, over the rows the reader may see,
 * and this module is the one place the console spells a question to it. The split is `paging.ts`':
 * this decides what a request looks like and what a filter may offer, `useListing.ts` owns the
 * fetching, and `ListControls.tsx` draws the controls.
 *
 * **Every narrowing is a request.** A search box, a filter and an order each change the question
 * sent to the route, and the rows drawn are the route's answer to that question. Nothing here
 * filters or sorts rows in the browser, which `DataTable.tsx` argues is a statement about what
 * happened to arrive dressed as one about what exists.
 *
 * **A filter offers only values the reader was shown.** The choices under a filter are the values
 * carried by rows this page has already drawn, gathered as pages arrive and never read from
 * anywhere else, so no dropdown can name a department, a person or a state the reader was not
 * shown a row for. See `A_FILTER_OFFERS_ONLY_WHAT_WAS_SHOWN`. The cost is real and deliberate: a
 * value on a row the reader has not paged to yet is not offered until they have.
 *
 * **The cursor is sent back as it came and never kept in the address.** It is a position in one
 * reader's walk of one question, bound to both on the server, and a link carrying one would open
 * somebody else's walk part-way through: `auditQuery.ts` makes the same choice.
 *
 * **No number about the rows.** There is no total to render and no page number: "Show more" asks
 * for the next page and disappears when the API sends no cursor.
 *
 * Task ids: M27.8.6
 */

import { CURSOR_PARAMETER, FILTER_PARAMETER, FILTER_SEPARATOR, LIMIT_PARAMETER } from "./paging";

/** Written down because the obvious dropdown lists every department in the company. */
export const A_FILTER_OFFERS_ONLY_WHAT_WAS_SHOWN =
  "A filter offers the values carried by rows this page has already drawn, and nothing read from " +
  "anywhere else. A list of departments, people or states from any other source would name values " +
  "the reader was not shown a row for, which is the listing the rows were narrowed to avoid.";

/** The search parameter every list route declares. `brain.listing.SEARCH_PARAM`. */
export const SEARCH_PARAMETER = "q";

/** The order parameter every list route declares. `brain.listing.SORT_PARAM`. */
export const SORT_PARAMETER = "sort";

/** What an order puts before a column to walk it the other way. `brain.listing.DESCENDING`. */
export const DESCENDING = "-";

/** How many rows one page asks for. Below `brain.listing.MAX_PAGE_ROWS`; see the test. */
export const LIST_PAGE_SIZE = 50;

/** What a list is being asked: the words, one value per filtered column, and an order. */
export interface ListQuestion {
  readonly search: string;
  /** Column to value. An empty value is no filter on that column. */
  readonly filters: Readonly<Record<string, string>>;
  /** As the route spells it, or empty for the route's own order. */
  readonly sort: string;
}

export const NO_QUESTION: ListQuestion = Object.freeze({
  search: "",
  filters: Object.freeze({}),
  sort: "",
});

/** Whether a question narrows anything, which is what decides the empty sentence a page says. */
export function narrows(question: ListQuestion): boolean {
  return (
    question.search.trim() !== "" || Object.values(question.filters).some((value) => value !== "")
  );
}

/**
 * The whole request for one page, query string included.
 *
 * Only the five parameters `brain.listing.Listing.query` declares, plus whatever the route takes of
 * its own in `extra`. Filters are sent in column order, so one question is one address.
 */
export function listPath(
  path: string,
  question: ListQuestion,
  cursor: string | null,
  pageSize: number = LIST_PAGE_SIZE,
  extra: Readonly<Record<string, string>> = {},
): string {
  const query = new URLSearchParams();
  query.set(LIMIT_PARAMETER, String(pageSize));
  const search = question.search.trim();
  if (search !== "") {
    query.set(SEARCH_PARAMETER, search);
  }
  for (const column of Object.keys(question.filters).sort()) {
    const value = question.filters[column] ?? "";
    if (value !== "") {
      query.append(FILTER_PARAMETER, `${column}${FILTER_SEPARATOR}${value}`);
    }
  }
  if (question.sort !== "") {
    query.set(SORT_PARAMETER, question.sort);
  }
  for (const [name, value] of Object.entries(extra)) {
    query.set(name, value);
  }
  if (cursor !== null) {
    query.set(CURSOR_PARAMETER, cursor);
  }
  return `${path}?${query.toString()}`;
}

/** What a row says in one filtered column: one value, several, or none. */
export type Said = string | boolean | number | null | undefined | readonly string[];

/** One filter a page offers: the column the route filters, and how a row says its value. */
export interface FilterChoice<Row> {
  readonly column: string;
  readonly label: string;
  /** The first option, which is no filter. */
  readonly everything: string;
  readonly read: (row: Row) => Said;
  /** How a value is shown in the dropdown. The value sent is always the value itself. */
  readonly describe?: (value: string) => string;
}

/** One order a page offers, as the route spells it. */
export interface SortChoice {
  readonly value: string;
  readonly label: string;
}

/** A value as the route compares it: `brain.listing._texts`. */
function spelled(value: Said): readonly string[] {
  if (value === null || value === undefined) {
    return [];
  }
  if (typeof value === "boolean") {
    return [value ? "true" : "false"];
  }
  if (typeof value === "number") {
    return [String(value)];
  }
  if (typeof value === "string") {
    return value === "" ? [] : [value];
  }
  return value.filter((one) => one !== "");
}

/**
 * The values these rows carry in each filtered column, added to what was offered before.
 *
 * Only ever grows over one page's life, so a value stays offered after a filter hides the rows that
 * carried it: it was shown, and taking it away would leave a dropdown that cannot be set back.
 */
export function offeredFrom<Row>(
  previous: Readonly<Record<string, readonly string[]>>,
  rows: readonly Row[],
  choices: readonly FilterChoice<Row>[],
): Readonly<Record<string, readonly string[]>> {
  const offered: Record<string, readonly string[]> = {};
  for (const choice of choices) {
    const values = new Set(previous[choice.column] ?? []);
    for (const row of rows) {
      for (const value of spelled(choice.read(row))) {
        values.add(value);
      }
    }
    offered[choice.column] = [...values].sort((a, b) => a.localeCompare(b));
  }
  return offered;
}
