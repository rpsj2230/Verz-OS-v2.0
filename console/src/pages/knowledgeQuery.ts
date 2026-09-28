/**
 * What the Knowledge screen asks the API for, what a library row is, and how the page narrows
 * the rows it already holds. No React.
 *
 * The split is `skillsQuery.ts`' and `governQuery.ts`': this decides what may be asked and what
 * a row is, the page renders it, so what the screen does about a fact the API cannot send is
 * testable without mounting a table.
 *
 * **This screen is SCREEN 7 of `docs/screens.html`, and the API answers three of its eight
 * columns.** The design's library lists Item, Dept, Type, Visible to, Owner, Verified, Review due
 * and Used 30d. `brain.console.govern_estate.library_rows` decides this screen and its row is an
 * item's reference, its kind and its visibility level: the department and the owner are the two
 * halves of the visibility predicate it refuses to put on a row, the title and the verification
 * are more than the existence plane this screen is registered on, and nothing records how often a
 * document is retrieved. The kind is the design's Type, one word from a closed list (M7.6.1). `brain.estate_routes` sends `only_existence_and_reach_are_shown` and
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
 * **Adding a document is asked of the API too** (M7.6.3). The options say which kinds this person
 * may choose, which departments they may add to and which types and sizes the door takes; the page
 * posts the file raw with those words in the address and its name in a header, and shows the
 * API's own sentence when it is refused. Nothing here decides who may add what.
 *
 * Task ids: M27.7.20, M27.8.6, M7.6.1, M7.6.3
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
  "SCREEN 7 draws Dept, Owner, Verified, Review due and Used 30d beside every item, and " +
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
  {
    column: "kind",
    label: "Type",
    everything: "Every type",
    read: (row) => row.kind ?? "",
    describe: (value) => kindWord(value),
  },
];

/** The orders this screen offers. The levels' own names sort widest first. */
export const LIBRARY_SORTS: readonly SortChoice[] = [
  { value: "", label: "By reference" },
  { value: "level", label: "Widest first" },
  { value: "kind", label: "By type" },
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

// ------------------------------------------------------------------ the kind (M7.6.1)

/**
 * What each kind is called, keyed by the word the API stores. A copy of
 * `brain.knowledge.kinds.KIND_LABELS`, held to `KnowledgeKind`'s members by a test that reads the
 * Python, because a library row carries the stored word and a reader of the library may not be
 * somebody the upload options are offered to.
 */
export const KIND_WORDS: Readonly<Record<string, string>> = Object.freeze({
  sop: "SOP",
  policy: "Policy",
  faq: "FAQ",
  pricing_note: "Pricing note",
  service_information: "Service information",
  service_package: "Service package",
  brand_guidelines: "Brand guidelines",
  company_rule: "Company rule",
  best_practice: "Best practice",
  template: "Template",
  training_material: "Training material",
  approved_solution: "Approved solution",
});

/** What a row with no kind says: an item added before kinds were recorded, or by a connector. */
export const KIND_NOT_RECORDED = "not recorded";

/** One row's kind, in words. */
export function kindWord(kind: string | null | undefined): string {
  if (kind === null || kind === undefined || kind === "") {
    return KIND_NOT_RECORDED;
  }
  return KIND_WORDS[kind] ?? kind;
}

// ------------------------------------------------------------------ adding a document (M7.6.3)

/** Where the API says what this person may add and where. */
export const UPLOAD_OPTIONS_API_PATH = "/knowledge/uploads/options";

/** Where a document is added. */
export const UPLOADS_API_PATH = "/knowledge/uploads";

/** The two places an upload may be put. Company-wide is not one: it is a promotion. */
export const UPLOAD_LEVELS = ["department", "personal"] as const;
export type UploadLevel = (typeof UPLOAD_LEVELS)[number];

export interface KindChoice {
  readonly value: string;
  readonly label: string;
}

export interface TypeChoice {
  readonly mediaType: string;
  readonly extensions: readonly string[];
  readonly maxBytes: number;
}

/** `brain.knowledge_routes.UploadOptionsView`, as this console holds it. */
export interface UploadOptions {
  readonly kinds: readonly KindChoice[];
  readonly departments: readonly string[];
  readonly personal: boolean;
  readonly types: readonly TypeChoice[];
  readonly foundBy: string;
  readonly checkedBy: string;
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((one): one is string => typeof one === "string") : [];
}

/**
 * Read `brain.knowledge_routes.UploadOptionsView` out of a response body, or null when it is not
 * one. Null rather than a default, because an empty set of kinds would draw a form nobody can
 * submit and look like a page that works.
 */
export function readUploadOptions(payload: unknown): UploadOptions | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as Record<string, unknown>;
  if (!Array.isArray(body.kinds) || !Array.isArray(body.types)) {
    return null;
  }
  const kinds = body.kinds.flatMap((one: unknown) => {
    const kind = one as { value?: unknown; label?: unknown } | null;
    return typeof kind?.value === "string" && typeof kind.label === "string"
      ? [{ value: kind.value, label: kind.label }]
      : [];
  });
  const types = body.types.flatMap((one: unknown) => {
    const type = one as { media_type?: unknown; extensions?: unknown; max_bytes?: unknown } | null;
    return typeof type?.media_type === "string" && typeof type.max_bytes === "number"
      ? [{ mediaType: type.media_type, extensions: strings(type.extensions), maxBytes: type.max_bytes }]
      : [];
  });
  if (kinds.length === 0 || types.length === 0) {
    return null;
  }
  return {
    kinds,
    departments: strings(body.departments),
    personal: body.personal === true,
    types,
    foundBy: typeof body.found_by === "string" ? body.found_by : "",
    checkedBy: typeof body.checked_by === "string" ? body.checked_by : "",
  };
}

/**
 * The type a chosen file is declared as, from its extension, or null when this path reads none of
 * that kind. The extension is a claim like any other and the API checks it against the bytes; it
 * is used here because a browser reports no type at all for a Markdown file on most systems.
 */
export function typeOf(fileName: string, types: readonly TypeChoice[]): TypeChoice | null {
  const lower = fileName.toLowerCase();
  return types.find((one) => one.extensions.some((extension) => lower.endsWith(extension))) ?? null;
}

/** The accept list for the file input, from the extensions the API offers. */
export function acceptOf(types: readonly TypeChoice[]): string {
  return types.flatMap((one) => one.extensions).join(",");
}

/** The address a document is posted to: closed-list words and a department slug, never a name. */
export function uploadPath(kind: string, level: UploadLevel, department: string): string {
  const query = new URLSearchParams({ kind, level, department: level === "department" ? department : "" });
  return `${UPLOADS_API_PATH}?${query.toString()}`;
}

/** `brain.knowledge_routes.UploadedView`, as this console holds it. */
export interface Uploaded {
  readonly itemId: string;
  readonly title: string;
  readonly kind: string;
  readonly level: string;
  readonly department: string | null;
  readonly passages: number;
  readonly foundBy: string;
}

/** Read `brain.knowledge_routes.UploadedView`, or null when the body is not one. */
export function readUploaded(payload: unknown): Uploaded | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as Record<string, unknown>;
  if (typeof body.item_id !== "string" || typeof body.title !== "string" || typeof body.kind !== "string") {
    return null;
  }
  return {
    itemId: body.item_id,
    title: body.title,
    kind: body.kind,
    level: typeof body.level === "string" ? body.level : "",
    department: typeof body.department === "string" ? body.department : null,
    passages: typeof body.passages === "number" ? body.passages : 0,
    foundBy: typeof body.found_by === "string" ? body.found_by : "",
  };
}

/** What the page says once a document is added. About the uploader's own document, and no other. */
export function addedSentence(added: Uploaded): string {
  const where =
    added.level === "department" && added.department !== null
      ? `visible to the ${added.department} department`
      : "visible to you only";
  const passages = added.passages === 1 ? "1 passage" : `${String(added.passages)} passages`;
  return `Added "${added.title}" as ${kindWord(added.kind)}, ${where}, in ${passages}. It is found by ${added.foundBy}.`;
}
