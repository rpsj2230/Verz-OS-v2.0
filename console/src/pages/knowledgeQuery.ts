/**
 * What the Knowledge screen asks the API for, what a library row is, and how the page narrows
 * the rows it already holds. No React.
 *
 * The split is `skillsQuery.ts`' and `governQuery.ts`': this decides what may be asked and what
 * a row is, the page renders it, so what the screen does about a fact the API cannot send is
 * testable without mounting a table.
 *
 * **This screen is SCREEN 7 of `docs/screens.html`, and the API answers two of its eight
 * columns.** The design's library lists Item, Dept, Type, Visible to, Owner, Verified, Review due
 * and Used 30d. `brain.console.govern_estate.library_rows` decides this screen and its row is an
 * item's reference and its visibility level: the department and the owner are the two halves of
 * the visibility predicate it refuses to put on a row, the title and the verification are more
 * than the existence plane this screen is registered on, and nothing records a document type or
 * how often one is retrieved. `brain.estate_routes` sends `only_existence_and_reach_are_shown` and
 * `freshness_and_use_are_not_measured` to say so, and the page says it in words. See
 * `A_COLUMN_NOTHING_SENDS_IS_A_SENTENCE_AND_NEVER_A_BLANK_COLUMN`.
 *
 * **The search, the level filter, the order and "Show more" are requests to the route**
 * (`brain.listing`), and the route runs them over the items the reader may know exist without ever
 * narrowing what it loads, which is what keeps `truncated` from becoming a statement about how many
 * documents match: `brain.estate_routes.A_FILTER_ON_THE_SERVER_TURNS_A_TRUNCATION_FLAG_INTO_A_COUNT`.
 * Filtering by department is not offered, because a row carries no department to match.
 *
 * **The counts on this page are of rows the reader was shown**, never of a company total. A
 * count of what was shown is not a count of what was hidden, which is
 * `brain.knowledge.quality.A_COUNT_OF_WHAT_WAS_SHOWN_IS_NOT_A_COUNT_OF_WHAT_WAS_HIDDEN`, and
 * nothing here has a total to set one beside: `total` stops at `readKnowledgePage`.
 *
 * **Nothing here decides who may see what.** The request is identical for every caller and the
 * API answers from grants this browser never receives. Served by `brain.console.govern_estate`.
 *
 * Task ids: M27.7.20, M27.8.6
 */

import type { components } from "../api/schema";
import type { FilterChoice, SortChoice } from "../components/listing";

/** One item on the library, as `brain.estate_routes.LibraryRowView` sends it. */
export type LibraryRow = components["schemas"]["LibraryRowView"];

/** The three visibility levels, widest first, which is the order the design's column reads in. */
export const LEVELS = ["company", "department", "personal"] as const;
export type Level = (typeof LEVELS)[number];

/** Written down because an absent column is the first thing a reader of SCREEN 7 asks about. */
export const A_COLUMN_NOTHING_SENDS_IS_A_SENTENCE_AND_NEVER_A_BLANK_COLUMN =
  "SCREEN 7 draws Dept, Type, Owner, Verified, Review due and Used 30d beside every item, and " +
  "the API sends none of them. A column drawn empty on every row reads as a library nobody owns, " +
  "nobody has verified and nobody uses, which is a stronger claim than the truth. So the columns " +
  "are absent and the page says once, in words, which facts are missing and why.";

/** Where the API keeps this screen. */
export const KNOWLEDGE_API_PATH = "/govern/library";

/** The console address, at the screen's own key in `brain.console.screens`. */
export const KNOWLEDGE_PATH = "/library";

/** The filters the library route declares that this screen offers, over values on rows drawn. */
export const LIBRARY_FILTERS: readonly FilterChoice<LibraryRow>[] = [
  { column: "level", label: "Visible to", everything: "Every level", read: (row) => row.level },
];

/** The orders this screen offers. The levels' own names sort widest first. */
export const LIBRARY_SORTS: readonly SortChoice[] = [
  { value: "", label: "By reference" },
  { value: "level", label: "Widest first" },
];

/** One page of the library, as this console holds it. */
export interface KnowledgePage {
  readonly items: readonly LibraryRow[];
  /** The load came back full. Never how much more there is. */
  readonly truncated: boolean;
  /** The departments the rows may be grouped by, or null when this reader may not be shown them. */
  readonly departments: readonly string[] | null;
  /** The page was read from a copy that is behind, in the API's own sentence, or null. */
  readonly staleness: string | null;
  readonly onlyExistenceAndReachAreShown: boolean;
  readonly freshnessAndUseAreNotMeasured: boolean;
}

const NOTHING: KnowledgePage = Object.freeze({
  items: [],
  truncated: false,
  departments: null,
  staleness: null,
  // True on an unreadable body as well as on a real one, because both facts are true of this
  // installation, and a page that dropped the sentences when a body came back in an unexpected
  // shape would drop them exactly when it understood least.
  onlyExistenceAndReachAreShown: true,
  freshnessAndUseAreNotMeasured: true,
});

/**
 * Read `brain.estate_routes.LibraryPage` out of a response body.
 *
 * **`total` and `next_cursor` stop here**, as `readSkillsPage` stops them: not an agreement not
 * to render a total but no path from the payload to a renderer. An unreadable body is an empty
 * page rather than a throw, for that function's reason.
 */
export function readKnowledgePage(payload: unknown): KnowledgePage {
  if (typeof payload !== "object" || payload === null) {
    return NOTHING;
  }
  const body = payload as {
    items?: unknown;
    truncated?: unknown;
    departments?: unknown;
    staleness?: unknown;
    only_existence_and_reach_are_shown?: unknown;
    freshness_and_use_are_not_measured?: unknown;
  };
  if (!Array.isArray(body.items)) {
    return NOTHING;
  }
  const staleness = body.staleness as { message?: unknown } | null | undefined;
  return {
    items: body.items as LibraryRow[],
    truncated: body.truncated === true,
    departments: Array.isArray(body.departments) ? (body.departments as string[]) : null,
    staleness: typeof staleness?.message === "string" ? staleness.message : null,
    onlyExistenceAndReachAreShown: body.only_existence_and_reach_are_shown !== false,
    freshnessAndUseAreNotMeasured: body.freshness_and_use_are_not_measured !== false,
  };
}

/** How many of the rows shown sit at one level. A count of what is on the page and nothing else. */
export function atLevel(rows: readonly LibraryRow[], level: Level): number {
  return rows.filter((row) => row.level === level).length;
}
