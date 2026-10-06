/**
 * What the Knowledge module asks the API for, how it reads the answers, and the words it draws them
 * in. No React.
 *
 * **The list is `GET /knowledge/documents`, the detail route's rule over many rows.** A row is every
 * version the reader may open (`brain.knowledge_lifecycle_routes.THE_LIST_IS_THE_DETAIL_ROUTES_RULE_OVER_MANY_ROWS`),
 * so every row links to a page that answers, and the search, the filters and the order are the
 * route's own (`brain.listing`). The filters offer only values on rows drawn, except the review
 * filter, whose two words are the product's own and are offered once any row is drawn.
 *
 * **A reader keeps only what was sent.** Each row is read field by field and a field the API left
 * out stays out, so a cell the reader may not be told is empty rather than "unknown", which would
 * say something was withheld. `total` never leaves the reader.
 *
 * **A person is a name on the page and an id only in Advanced.** The steward and a disclosed
 * verifier arrive with their display names; the page draws those, and the principal ids go to the
 * detail page's Advanced section with the document's own reference.
 *
 * Task ids: M27.15.40, M27.16.1, M7.6.1
 */

import type { FilterChoice, SortChoice } from "../../components/listing";
import { kindWord } from "../knowledgeQuery";

/** The module's heading, which the navigation, the list and every trail back to it share. */
export const KNOWLEDGE_HEADING = "Knowledge";

/** Where the Knowledge list lives in the console, at the screen's own key. */
export const LIBRARY_ADDRESS = "/library";

/** Where captured solutions are decided, a tab of the Knowledge entry. */
export const SOLUTIONS_ADDRESS = "/solutions";

/** Where corrections carrying the right answer are reviewed, a tab of the Knowledge entry. */
export const CORRECTIONS_ADDRESS = "/corrections";

/** Where the list and one document's history are asked for, under the API base. */
export const DOCUMENTS_API_PATH = "/knowledge/documents";
export const VERIFICATIONS_API_PATH = "/knowledge/verifications";

export function historyPath(itemId: string): string {
  return `/knowledge/items/${encodeURIComponent(itemId)}/history`;
}

/** Where one document's page is, and one view of it. The Dashboard is the bare address. */
export function documentAddress(itemId: string): string {
  return `${LIBRARY_ADDRESS}/${encodeURIComponent(itemId)}`;
}

export const VIEWS = ["dashboard", "profile", "about"] as const;
export type DocumentViewKey = (typeof VIEWS)[number];

export function viewAddress(itemId: string, view: DocumentViewKey): string {
  return view === "dashboard" ? documentAddress(itemId) : `${documentAddress(itemId)}/${view}`;
}

/** Which view an address opens. Anything else opens the Dashboard, saying nothing. */
export function viewFor(view: string | undefined): DocumentViewKey {
  return view === "profile" || view === "about" ? view : "dashboard";
}

// ------------------------------------------------------------------ one row
/**
 * One document as the list and the detail hold it. A field is present only when it was sent. A type
 * rather than an interface so a row is also a plain record, which is what a list filter reads.
 */
export type DocRow = {
  readonly itemId: string;
  readonly title: string;
  readonly kindLabel?: string;
  readonly level: string;
  readonly department?: string;
  readonly stewardId?: string;
  readonly stewardName?: string;
  readonly state: string;
  readonly verification: string;
  readonly verifiedByName?: string;
  readonly verifiedAt?: string;
  readonly reviewBy?: string;
  readonly due: boolean;
  readonly supersedes?: string;
  readonly addedAt?: string;
  readonly youSteward: boolean;
  readonly solves?: string;
  readonly promotion?: { readonly status: string; readonly expiresAt?: string };
};

type Fields = Readonly<Record<string, unknown>>;

function fieldsOf(value: unknown): Fields | null {
  // A cast at the boundary, where proving a structural match buys nothing: every field is read
  // back through `said` or a comparison below.
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Fields) : null;
}

function said(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}

function optional<K extends string>(key: K, value: string | undefined): Partial<Record<K, string>> {
  return value === undefined ? {} : ({ [key]: value } as Record<K, string>);
}

/** One document out of a body, or null when it names no document. */
export function readDocRow(value: unknown): DocRow | null {
  const fields = fieldsOf(value);
  const itemId = said(fields?.["item_id"]);
  if (fields === null || itemId === undefined) {
    return null;
  }
  const promotion = fieldsOf(fields["promotion"]);
  const status = said(promotion?.["status"]);
  return {
    itemId,
    title: said(fields["title"]) ?? itemId,
    level: said(fields["level"]) ?? "",
    state: said(fields["state"]) ?? "",
    verification: said(fields["verification"]) ?? "unverified",
    due: fields["due"] === true,
    youSteward: fields["you_steward"] === true,
    ...optional("kindLabel", said(fields["kind_label"])),
    ...optional("department", said(fields["department"])),
    ...optional("stewardId", said(fields["steward_id"])),
    ...optional("stewardName", said(fields["steward_name"])),
    ...optional("verifiedByName", said(fields["verified_by_name"])),
    ...optional("verifiedAt", said(fields["verified_at"])),
    ...optional("reviewBy", said(fields["review_by"])),
    ...optional("supersedes", said(fields["supersedes"])),
    ...optional("addedAt", said(fields["added_at"])),
    ...optional("solves", said(fields["solves"])),
    ...(status === undefined ? {} : { promotion: { status, ...optional("expiresAt", said(promotion?.["expires_at"])) } }),
  };
}

/** The rows out of a list body, once each, in the order they came. */
export function readDocRows(payload: unknown): readonly DocRow[] {
  const items = fieldsOf(payload)?.["items"];
  if (!Array.isArray(items)) {
    return [];
  }
  const seen = new Set<string>();
  const rows: DocRow[] = [];
  for (const one of items as readonly unknown[]) {
    const row = readDocRow(one);
    if (row !== null && !seen.has(row.itemId)) {
      seen.add(row.itemId);
      rows.push(row);
    }
  }
  return rows;
}

// ------------------------------------------------------------------ one document's page
export interface VersionRow {
  readonly itemId: string;
  readonly title: string;
  readonly state: string;
  readonly addedAt?: string;
  readonly readable: boolean;
}

export interface Offered {
  readonly verify: boolean;
  readonly newVersion: boolean;
  readonly propose: boolean;
  readonly handOver: boolean;
}

export interface DocumentPage {
  readonly document: DocRow;
  readonly versions: readonly VersionRow[];
  readonly offered: Offered;
  readonly promotionWaits?: string;
}

/** `DocumentDetailView` as this console holds it, or null when the body is not one. */
export function readDocumentPage(payload: unknown): DocumentPage | null {
  const fields = fieldsOf(payload);
  const document = readDocRow(fields?.["document"]);
  if (fields === null || document === null) {
    return null;
  }
  const versions = (Array.isArray(fields["versions"]) ? (fields["versions"] as readonly unknown[]) : []).flatMap((one) => {
    const version = fieldsOf(one);
    const itemId = said(version?.["item_id"]);
    if (version === null || itemId === undefined) {
      return [];
    }
    return [
      {
        itemId,
        title: said(version["title"]) ?? itemId,
        state: said(version["state"]) ?? "",
        readable: version["readable"] === true,
        ...optional("addedAt", said(version["added_at"])),
      },
    ];
  });
  const offered = fieldsOf(fields["offered"]);
  return {
    document,
    versions,
    offered: {
      verify: offered?.["verify"] === true,
      newVersion: offered?.["new_version"] === true,
      propose: offered?.["propose"] === true,
      handOver: offered?.["hand_over"] === true,
    },
    ...optional("promotionWaits", said(fields["promotion_waits"])),
  };
}

export interface HistoryRow {
  readonly itemId: string;
  readonly at: string;
  readonly event: string;
}

/** `HistoryView`'s events, oldest first as sent, and whether the read reached its bound. */
export function readHistory(payload: unknown): { readonly events: readonly HistoryRow[]; readonly truncated: boolean } {
  const fields = fieldsOf(payload);
  const events = (Array.isArray(fields?.["events"]) ? (fields["events"] as readonly unknown[]) : []).flatMap((one) => {
    const event = fieldsOf(one);
    const itemId = said(event?.["item_id"]);
    const at = said(event?.["at"]);
    const what = said(event?.["event"]);
    return itemId === undefined || at === undefined || what === undefined ? [] : [{ itemId, at, event: what }];
  });
  return { events, truncated: fields?.["truncated"] === true };
}

export interface TaskRow {
  readonly taskId: string;
  readonly itemId: string;
  readonly says: string;
  readonly closable: boolean;
  readonly kind: string;
}

/** `TasksView`'s tasks, as sent. */
export function readTasks(payload: unknown): readonly TaskRow[] {
  const items = fieldsOf(payload)?.["items"];
  return (Array.isArray(items) ? (items as readonly unknown[]) : []).flatMap((one) => {
    const task = fieldsOf(one);
    const taskId = said(task?.["task_id"]);
    const itemId = said(task?.["item_id"]);
    const says = said(task?.["says"]);
    return taskId === undefined || itemId === undefined || says === undefined
      ? []
      : [{ taskId, itemId, says, closable: task?.["closable"] === true, kind: said(task?.["kind"]) ?? "" }];
  });
}

// ------------------------------------------------------------------ the words
/** A state as a person reads it. `published` is the version answers are drawn from. */
export const STATE_WORDS: Readonly<Record<string, string>> = Object.freeze({
  published: "Current",
  superseded: "Superseded",
  archived: "Archived",
  draft: "Draft",
});

/** Who a document reaches, in a word for the column and the filter. */
export const LEVEL_WORDS: Readonly<Record<string, string>> = Object.freeze({
  company: "Whole company",
  department: "Department",
  personal: "Steward only",
});

/** The review filter's values, `brain.knowledge_lifecycle_routes.REVIEW_DUE` and `REVIEW_NOT_DUE`. */
export const REVIEW_VALUES: readonly string[] = Object.freeze(["due", "not_due"]);

/** The review filter's two words, the product's own and the same on every install. */
export const REVIEW_WORDS: Readonly<Record<string, string>> = Object.freeze({
  due: "Review due",
  not_due: "Not due",
});

/** What each ledger event is called in a history. */
export const EVENT_WORDS: Readonly<Record<string, string>> = Object.freeze({
  added: "Added",
  verified: "Verified",
  handed_over: "Handed to a new steward",
  replaced: "Replaced by a newer version",
  company_wide: "Made readable by the whole company",
  archived: "Archived",
  review_date: "Review date changed",
});

export function stateWords(state: string): string {
  return STATE_WORDS[state] ?? state;
}

export function levelWords(level: string): string {
  return LEVEL_WORDS[level] ?? level;
}

export function reviewWords(value: string): string {
  return REVIEW_WORDS[value] ?? value;
}

export function eventWords(event: string): string {
  return EVENT_WORDS[event] ?? event;
}

/** A stored instant as a day a person reads, in a fixed locale. */
export function dayWords(instant: string | undefined): string | undefined {
  if (instant === undefined) {
    return undefined;
  }
  const at = new Date(instant);
  return Number.isNaN(at.getTime())
    ? undefined
    : at.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

/** The verification badge in words, with a name and a day only when the API sent them. */
export function verifiedWords(row: DocRow): string {
  const named = row.verifiedByName === undefined ? "" : ` by ${row.verifiedByName}`;
  const day = dayWords(row.verifiedAt);
  const when = day === undefined ? "" : ` on ${day}`;
  switch (row.verification) {
    case "verified":
      return `Verified${named}${when}`;
    case "due":
      return `Due for review${named === "" ? "" : `, verified${named}`}${when}`;
    case "superseded":
      return "Replaced";
    default:
      return "Not verified";
  }
}

/** Where a request for the whole company has got to, in a sentence. */
export function promotionWords(row: DocRow): string | undefined {
  switch (row.promotion?.status) {
    case undefined:
      return undefined;
    case "waiting":
      return "Waiting on the Approvals screen";
    case "approved":
      return "Approved for the whole company";
    case "rejected":
      return "Not approved";
    default:
      return "Lapsed without a decision";
  }
}

// ------------------------------------------------------------------ the list's controls
/**
 * The filters the list route declares that the page offers. Each reads the raw row the route sent,
 * which is what `useListing` gathers the offered values from.
 */
export const DOCUMENT_FILTERS: readonly FilterChoice<Readonly<Record<string, unknown>>>[] = [
  {
    column: "department",
    label: "Department",
    everything: "All departments",
    read: (row) => said(row["department"]),
  },
  {
    column: "level",
    label: "Visible to",
    everything: "Everyone it reaches",
    read: (row) => said(row["level"]),
    describe: levelWords,
  },
  {
    column: "state",
    label: "State",
    everything: "Any state",
    read: (row) => said(row["state"]),
    describe: stateWords,
  },
  {
    // The kind each document was added as (M7.6.1), in the library's own words for it.
    column: "kind",
    label: "Kind",
    everything: "Every kind",
    read: (row) => said(row["kind"]),
    describe: kindWord,
  },
  {
    column: "review",
    label: "Review",
    everything: "Any review date",
    // Both words from the first row drawn, rather than the row's own: they are the product's closed
    // pair, so offering "Review due" before a due row has been drawn names nothing that exists, and
    // it is the filter SCREEN 7 puts first.
    read: () => REVIEW_VALUES,
    describe: reviewWords,
  },
];

export const DOCUMENT_SORTS: readonly SortChoice[] = [
  { value: "", label: "Title" },
  { value: "review_by", label: "Review date" },
  { value: "department", label: "Department" },
  { value: "steward", label: "Steward" },
  { value: "state", label: "State" },
];
