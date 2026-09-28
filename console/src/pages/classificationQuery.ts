/**
 * What the classification screen asks the API for, what a column's row is, and what may be
 * proposed about one. No React.
 *
 * The split is `matrixQuery.ts`'s and `recordsQuery.ts`'s, and the reason is the same: this
 * decides what may be asked and what may be sent, `Classification.tsx` renders it, and the
 * case that is always wrong is what an editor does about a field it must not send. That
 * cannot be tested through a component that mounts a form library and a table.
 *
 * **This screen is where somebody widens access by accident, and the defence is that it
 * never decides.** A classification says the cost is confidential and the sell price is not.
 * Every judgement about what a proposed rule would do comes back from
 * `POST /api/v1/classifications/{entity}/columns/{column}/review` as an answer: which
 * changes it makes, whether it widens, and which columns a caller short of one column would
 * newly reach. Nothing here recomputes any of it. See
 * `A_WIDENING_IS_NAMED_BY_THE_API_AND_NEVER_WORKED_OUT_HERE`.
 *
 * **Two path segments and no body key for either.** The entity and the column are the
 * address, exactly as the rung is on the matrix screen, and `brain.classification_routes.
 * ColumnEdit` forbids both keys. `submittedEdit` builds its body from three named keys
 * rather than from whatever the form handed back, so a `column` appearing in form state has
 * nowhere to travel. The route refuses one anyway; this is the half that stops the console
 * asking.
 *
 * **A built-in classification is reviewed and never saved; an uploaded table is marked and
 * applied.** See `A_REVIEW_IS_NOT_A_SAVE` and `A_MARK_IS_APPLIED_AND_LEDGERED`. The shipped
 * price list is a constant in the API's process, so its editor says a change is a source edit
 * and a deploy. A price list somebody uploaded (`PUT /api/v1/classifications/{entity}/table`)
 * is stored, and a mark on one of its columns is reviewed and then applied, as two requests.
 *
 * **The epoch reaches the screen, since the API's epoch moves with a derivation.** It did not
 * until 2026-09-28: `ColumnRule.as_field_rule` dropped `derived_from`, so dropping a
 * derivation left the epoch identical while changing what everybody short of a column sees,
 * and this module read no epoch at all rather than show a reason to believe nothing had
 * changed. The route now compiles the derivation in, so the epoch is the digest the answer
 * cache is keyed on, and a person applying a mark can see it move.
 *
 * **The columns of the grid are a fixed list and are deliberately sorted by nothing here.**
 * The API answers them in its own sorted order, which is a property of the classification
 * rather than of the caller, so the order carries nothing. What is fixed here is which
 * fields of a column's rule are shown, and `tests/classification-page.test.tsx` holds that
 * list against `brain.classification_routes.ColumnView` so a field added there cannot arrive
 * and be dropped in silence.
 *
 * Task ids: M7.5.3, M7.7.3
 */

import type { RJSFSchema, UiSchema } from "@rjsf/utils";
import type { ReactNode } from "react";
import { chipCell, valueCell } from "../components/cells";
import type { GridColumn } from "../components/DataTable";
import type { components } from "../api/schema";

/** One classified column, as `brain.classification_routes.ColumnView` sends it. */
export type ColumnRow = components["schemas"]["ColumnView"];

/** What a review answered, as `brain.classification_routes.ReviewView` sends it. */
export type ReviewBody = components["schemas"]["ReviewView"];

/**
 * Written down because working out whether a change widens access is a small function, it
 * looks like a helper, and it is the one piece of arithmetic this console must never own.
 */
export const A_WIDENING_IS_NAMED_BY_THE_API_AND_NEVER_WORKED_OUT_HERE =
  "Whether a proposed rule lets more people see more is decided by the API, from the " +
  "classification that stands and the one proposed, and arrives as an answer. The closure " +
  "that decides it is the same one that withholds a column at request time, so a copy of " +
  "it here would be a second answer to what a person may see, held in the one place an " +
  "attacker can edit and drifting the first time the real one changed. This module reads " +
  "`widens` and `exposed` and renders them; it computes neither and cannot.";

/**
 * Written down because a screen with a form on it reads as a screen that saves, and this
 * one does not.
 */
export const A_REVIEW_IS_NOT_A_SAVE =
  "A review says what a proposed rule would do and stores nothing. For a built-in " +
  "classification, a constant compiled into the API's own process, applying a change is a " +
  "source edit and a deploy, and the console says so on the screen, because an editor that " +
  "let somebody believe otherwise would be worse than no editor: they would stop checking.";

/**
 * Written down because an uploaded table's editor does save, and it has to say so as plainly
 * as the built-in one says it does not.
 */
export const A_MARK_IS_APPLIED_AND_LEDGERED =
  "An uploaded table's column is changed by applying a mark, which is its own request, sent " +
  "only after the same mark was reviewed. The API stores the whole classification in one " +
  "statement and writes an audit entry naming the person, and its answer carries the review " +
  "again, so the widening is named in the response that made it.";

/**
 * Written down because hiding the editor is presentation and looks exactly like enforcement.
 */
export const AN_EDITOR_DRAWN_OR_HIDDEN_ASKS_THE_SAME_QUESTION =
  "`editable` comes from the API, on the response, recomputed for every request. It " +
  "decides whether an edit control is drawn and it decides nothing else: the request this " +
  "screen makes is identical whichever way it reads, and every review is refused or " +
  "answered by the route. A console that skipped a request because the flag was false " +
  "would be enforcing a rule in the copy an attacker edits, and one that trusted the flag " +
  "to mean a review will be answered would be holding a permission model with no way to " +
  "know it had gone stale.";

/**
 * Written down because the columns of a classification are the obvious thing to count, and
 * because counting them here is how the rule gets copied onto a screen where it matters.
 */
export const A_CLASSIFICATION_SCREEN_STILL_CARRIES_NO_COUNT =
  "No number of columns reaches this screen, and the reason is not that this collection " +
  "is filtered, because it is not: every caller who may read a classification is answered " +
  "all of it. It is that this console keeps one rule about counts rather than one per " +
  "endpoint, and a screen that counted here would be the worked example somebody copies " +
  "onto a screen where the collection is filtered. The columns a review would expose are " +
  "named rather than counted, which is the opposite operation: naming is what the person " +
  "reading it has to do something about.";

/**
 * Written down because a console that does not know which entities exist looks unfinished,
 * and the fix somebody reaches for is a list.
 */
export const THE_CONSOLE_DOES_NOT_KNOW_WHAT_IS_CLASSIFIED =
  "There is no route that lists the classified entities and this screen does not ask for " +
  "one. A list of them is a map of what this company keeps and treats as sensitive, handed " +
  "over for the price of one capability, which is the enumeration the records screen " +
  "refuses one level down. So a person names an entity, and an entity nothing classifies " +
  "is answered exactly as one they may not read.";

/** Where the API keeps a classification. */
export const CLASSIFICATION_API_PATH = "/classifications";

/** Where the API answers one column's review. Encoded, because both travel in the address. */
export function reviewApiPath(entity: string, column: string): string {
  return (
    `${CLASSIFICATION_API_PATH}/${encodeURIComponent(entity)}` +
    `/columns/${encodeURIComponent(column)}/review`
  );
}

/**
 * The whole request this screen makes for one classification, query string included.
 *
 * There is none, and that is the property rather than an omission. The route declares no
 * query parameter at all, and FastAPI discards a parameter no signature names without a
 * word and answers 200, so a console sending one would get the same answer while believing
 * it had asked something narrower. `tests/classification-page.test.tsx` reads the declared
 * parameters out of the API's own document and asserts both halves: the route declares
 * none, and this sends none.
 */
export function classificationApiPath(entity: string): string {
  return `${CLASSIFICATION_API_PATH}/${encodeURIComponent(entity)}`;
}

/** The console address for the classification screen. */
export const CLASSIFICATION_PATH = "/classification";

/**
 * The console address for one entity's classification, and for one column's editor.
 *
 * Built from a constant prefix and encoded segments, for the reason `rungAddress` gives:
 * GHSA-wrjc-x8rr-h8h6 is an open redirect through a backslash reaching `useNavigate`, it
 * covers every react-router this project can install, and the defence is that the address
 * starts with a literal path segment.
 */
export function classificationAddress(entity: string): string {
  return `${CLASSIFICATION_PATH}/${encodeURIComponent(entity)}`;
}

export function columnAddress(entity: string, column: string): string {
  return `${classificationAddress(entity)}/${encodeURIComponent(column)}`;
}

/** One classification, as this console holds it. */
export interface ClassificationPage {
  readonly entity: string;
  readonly columns: readonly ColumnRow[];
  /** Whether this caller may have a change reviewed. Presentation only. */
  readonly editable: boolean;
  /** Whether this is an uploaded table's classification, so a mark can be applied. */
  readonly stored: boolean;
  readonly title: string;
  readonly keyColumn: string;
  /** The digest the answer cache is keyed on, moved by any change to a rule. */
  readonly epoch: string;
}

const NOTHING: ClassificationPage = Object.freeze({
  entity: "",
  columns: [],
  editable: false,
  stored: false,
  title: "",
  keyColumn: "",
  epoch: "",
});

/**
 * Read `brain.classification_routes.ClassificationView` out of a response body.
 *
 * The epoch is read, and it discloses nothing: it is a digest over rules this response
 * already carries in full. See the module docstring for why it now reaches the screen.
 *
 * An unreadable body yields an empty classification rather than throwing, which is
 * `readMatrixPage`'s choice and not `readPage`'s, and for its reason: the shape is fixed by
 * a response model in this repository, so a body that is not a classification is a console
 * built against a different API and there is no sentence worth composing about it.
 */
export function readClassification(payload: unknown): ClassificationPage {
  if (typeof payload !== "object" || payload === null) {
    return NOTHING;
  }
  const body = payload as {
    entity?: unknown;
    columns?: unknown;
    editable?: unknown;
    stored?: unknown;
    title?: unknown;
    key_column?: unknown;
    epoch?: unknown;
  };
  if (!Array.isArray(body.columns) || typeof body.entity !== "string") {
    return NOTHING;
  }
  return {
    entity: body.entity,
    columns: body.columns as ColumnRow[],
    editable: body.editable === true,
    stored: body.stored === true,
    title: typeof body.title === "string" ? body.title : "",
    keyColumn: typeof body.key_column === "string" ? body.key_column : "",
    epoch: typeof body.epoch === "string" ? body.epoch : "",
  };
}

/** What one review said, as this console holds it. */
export interface Review {
  /** Why the proposed classification would not construct, in the API's words, or empty. */
  readonly wouldNotLoad: string;
  /** What the API said changed, in its own words. Never translated here. */
  readonly changes: readonly string[];
  /** Whether the API called it a widening. Never recomputed. */
  readonly widens: boolean;
  /** The columns the API said a caller short of one column would newly reach. */
  readonly exposed: readonly string[];
  /** The epoch of the classification that stands, and of the proposed one. */
  readonly epochNow: string;
  readonly epochAfter: string;
}

const UNREAD: Review = Object.freeze({
  wouldNotLoad: "",
  changes: [],
  widens: false,
  exposed: [],
  epochNow: "",
  epochAfter: "",
});

/**
 * Read `brain.classification_routes.ReviewView` out of a response body.
 *
 * Both epochs are read. They differ for any change to a rule, a dropped derivation included,
 * and they are shown as the digests they are rather than as a verdict: whether the change
 * widens is `widens`, which the API decided.
 *
 * `widens` defaults to false only for a body that is not a review at all, and the caller
 * treats an unreadable body as no answer rather than as a safe one: see `Classification.tsx`.
 */
export function readReview(payload: unknown): Review {
  if (typeof payload !== "object" || payload === null) {
    return UNREAD;
  }
  const body = payload as {
    would_not_load?: unknown;
    changes?: unknown;
    widens?: unknown;
    exposed?: unknown;
    epoch_now?: unknown;
    epoch_after?: unknown;
  };
  return {
    epochNow: typeof body.epoch_now === "string" ? body.epoch_now : "",
    epochAfter: typeof body.epoch_after === "string" ? body.epoch_after : "",
    wouldNotLoad: typeof body.would_not_load === "string" ? body.would_not_load : "",
    changes: Array.isArray(body.changes)
      ? body.changes.filter((word): word is string => typeof word === "string")
      : [],
    widens: body.widens === true,
    exposed: Array.isArray(body.exposed)
      ? body.exposed.filter((name): name is string => typeof name === "string")
      : [],
  };
}

/** The column with this name among the ones on the page, or null. */
export function columnByName(columns: readonly ColumnRow[], name: string): ColumnRow | null {
  return columns.find((column) => column.column === name) ?? null;
}

/**
 * How each field of a column's rule is rendered.
 *
 * A list rather than four column definitions, so that "every field the API sends about a
 * classified column reaches the screen" is a property a test can hold against
 * `brain.classification_routes.ColumnView`. The field this protects against is
 * `derived_from`: a derivation reads as bookkeeping and decides what a caller short of one
 * column sees, so it is exactly the field somebody leaves out of a grid.
 *
 * `chip` says the value is a short word from a closed vocabulary, and only the sensitivity
 * level is one. It carries no colour and no severity, so nothing here can decide that
 * `restricted` is alarming and `public` is reassuring; the API's own word is shown.
 */
export const CLASSIFICATION_COLUMNS: readonly {
  readonly name: keyof ColumnRow;
  readonly as: "value" | "chip" | "names";
}[] = [
  { name: "column", as: "value" },
  { name: "access", as: "chip" },
  { name: "classification", as: "chip" },
  { name: "required_capability", as: "value" },
  { name: "derived_from", as: "names" },
];

/**
 * The id of the column carrying the edit control.
 *
 * Not a field of `ColumnView`, and named here so the test comparing the grid's columns with
 * the model's fields can account for exactly one that is not one.
 */
export const EDIT_COLUMN = "edit";

/** What the edit column's cell is given: the column's name, and a renderer from the page. */
export type EditCell = (column: string) => ReactNode;

/**
 * A list of sibling column names, one per line.
 *
 * Declared beside the columns that use it, as `matrixQuery.ts` declares its scope cell. One
 * name per line rather than joined with commas, because a comma list reads as prose and
 * these are identifiers; and an empty derivation renders as nothing rather than as the word
 * "none", because a column that reconstructs from nothing is the ordinary case and a word
 * for it would be this console naming a state the payload does not carry.
 */
function namesCell(context: { getValue: () => unknown }) {
  const value = context.getValue();
  if (!Array.isArray(value)) {
    return null;
  }
  const names = value.filter((name): name is string => typeof name === "string" && name !== "");
  return names.length === 0 ? null : names.join("\n");
}

/**
 * The grid's columns, given whether this caller may have a change reviewed.
 *
 * The only difference the flag makes is whether the edit column exists. Nothing about the
 * request changes, nothing about the other columns changes, and no row is withheld: see
 * `AN_EDITOR_DRAWN_OR_HIDDEN_ASKS_THE_SAME_QUESTION`.
 *
 * The header is the API's own field name, unchanged, for the reason `recordsQuery.ts` gives:
 * the API owns the vocabulary, and a console renaming `required_capability` to "Who can see
 * it" would show a phrase no grant table, no policy row and no support conversation uses.
 *
 * No column carries `meta.filterLabel`. This route declares no query parameter at all, and a
 * filter box whose parameter no route declares is discarded by FastAPI without a word,
 * leaving a person reading every column as the matching ones.
 */
export function classificationColumns(
  editable: boolean,
  editCell: EditCell,
): GridColumn<ColumnRow>[] {
  const columns: GridColumn<ColumnRow>[] = CLASSIFICATION_COLUMNS.map((column) => ({
    id: column.name,
    header: column.name,
    // `accessorFn` rather than `accessorKey`, for the reason the records grid gives: a key
    // is a path expression to the table library, so a field named `a.b` would silently read
    // a nested object that is not there.
    accessorFn: (row: ColumnRow) => row[column.name],
    cell:
      column.as === "chip" ? chipCell : column.as === "names" ? namesCell : valueCell,
  }));
  if (!editable) {
    return columns;
  }
  return [
    ...columns,
    {
      id: EDIT_COLUMN,
      header: EDIT_COLUMN,
      accessorFn: (row: ColumnRow) => row.column,
      cell: (context: { getValue: () => unknown }) => {
        const name = context.getValue();
        return typeof name === "string" && name !== "" ? editCell(name) : null;
      },
    },
  ];
}

/**
 * The bounds and the vocabulary `POST .../columns/{column}/review` declares, copied here so
 * the form can refuse a value without spending a request.
 *
 * Copies, and therefore checked against the originals rather than against each other: the
 * test reads the request body schema out of the generated OpenAPI document, which is
 * produced from `brain.app.create_app` and carries the pattern
 * `brain.core.entitlement.CAPABILITY_RE` itself, and it reads the four sensitivity words out
 * of `brain.core.field_policy.Classification` as well.
 */
export const CAPABILITY_PATTERN = "^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*|\\.\\*)*$";
export const MIN_CAPABILITY_LENGTH = 3;
export const MAX_CAPABILITY_LENGTH = 200;
export const MAX_DERIVED_FROM = 64;

/**
 * The four sensitivity levels, in the order `CLASSIFICATION_ORDER` puts them in.
 *
 * The order is not cosmetic and it is not this console's: `brain.core.field_policy` writes
 * the order out rather than relying on declaration order, because every downstream consumer
 * is a comparison. A select offering them in another order would invite somebody to read the
 * list as unordered, which is the one thing these four words are not.
 */
export const CLASSIFICATION_WORDS = ["public", "internal", "confidential", "restricted"] as const;

/** The three fields a column's rule may propose, in the order the form shows them. */
export const EDITABLE_FIELDS = ["required_capability", "classification", "derived_from"] as const;

/**
 * The sibling columns a rule may name as its inputs.
 *
 * The classification's own columns, minus the one being edited. The subtraction is the
 * point: `ColumnRule` refuses a column declared as derived from itself, because such a rule
 * would make the closure withhold the column in order to protect it, and a form offering the
 * option would be offering a proposal the API can only answer with a refusal. Sorted, so the
 * options do not carry the order the API happened to answer in.
 */
export function derivationOptions(
  columns: readonly ColumnRow[],
  editing: string,
): string[] {
  return columns
    .map((column) => column.column)
    .filter((name) => name !== editing)
    .sort();
}

/**
 * The form one column's rule is proposed through.
 *
 * **A schema written here, from the route's own request model, and not one the API sent.**
 * The same honesty `RECORDS_QUERY_SCHEMA` and `RUNG_EDIT_SCHEMA` state about themselves: no
 * route returns a JSON Schema, so `formShape` is exercised over a document this console
 * assembled. What makes it more than a hand-written form is that every bound in it is the
 * route's bound and is checked against the route's own description.
 *
 * Built per entity rather than frozen at module level, because the derivation options are
 * that classification's own column names and they arrive on the response. `SchemaForm`
 * memoises on the schema's identity and the ajv validator recompiles whenever it changes, so
 * the caller memoises this on the column list rather than rebuilding it per render.
 *
 * There is no `entity` and no `column`, and both are absent for the reason
 * `brain.classification_routes` gives: they are path segments, a value that arrives twice is
 * a value two readers disagree about, and `ColumnEdit` forbids both keys as well.
 *
 * **A document with one column has nothing to derive from, and the schema says so rather than
 * failing to compile.** JSON Schema refuses an `enum` with no members, so the form built for such a
 * document answered every submission with "schema is invalid" and the ajv path of the refusal,
 * which says nothing a person can act on. `tests/validated-before-write.test.tsx` submitted the
 * review blank on a one-column fixture and read that sentence back. With no other column the
 * derivation list is held to no items instead, which is the same rule stated validly.
 */
export function columnEditSchema(options: readonly string[]): RJSFSchema {
  return {
    type: "object",
    required: [...EDITABLE_FIELDS],
    properties: {
      required_capability: {
        type: "string",
        title: "required_capability",
        minLength: MIN_CAPABILITY_LENGTH,
        maxLength: MAX_CAPABILITY_LENGTH,
        pattern: CAPABILITY_PATTERN,
      },
      classification: {
        type: "string",
        title: "classification",
        enum: [...CLASSIFICATION_WORDS],
      },
      derived_from: {
        type: "array",
        title: "derived_from",
        maxItems: options.length === 0 ? 0 : MAX_DERIVED_FROM,
        uniqueItems: true,
        items: options.length === 0 ? { type: "string" } : { type: "string", enum: [...options] },
      },
    },
  };
}

/** Presentation only. The submit text is the sentence, so the button says what it does. */
export const COLUMN_EDIT_UI: UiSchema = Object.freeze<UiSchema>({
  "ui:submitButtonOptions": { submitText: "Review this change" },
});

/** What one column's form starts from. The three values the API answered, and nothing else. */
export function editableDefaults(row: ColumnRow): Record<string, unknown> {
  return {
    required_capability: row.required_capability,
    classification: row.classification,
    derived_from: [...row.derived_from],
  };
}

/** The body of one review, as the route's `ColumnEdit` model declares it. */
export interface ColumnEdit {
  readonly required_capability: string;
  readonly classification: string;
  readonly derived_from: readonly string[];
}

/**
 * What the editor submitted, or null if it was not a rule.
 *
 * **Assembled from three named keys rather than passed through.** That is the difference
 * between a body this console composed and a body the form library handed over: a `column`
 * or an `entity` in the form's state, from a schema change, a merge or a browser extension,
 * has nowhere here to travel. The route forbids both keys as well, and both are wanted, so a
 * person never sees a 422 about a field they did not fill in.
 *
 * Null means the shape was not what this screen asked for, and the caller does nothing. A
 * proposal assembled out of values nobody recognised is a question nobody meant to ask, and
 * on this screen the answer to it would be a verdict about who may see what.
 */
export function submittedEdit(data: unknown): ColumnEdit | null {
  if (typeof data !== "object" || data === null) {
    return null;
  }
  const fields = data as Record<string, unknown>;
  const capability = fields["required_capability"];
  const classification = fields["classification"];
  const derived = fields["derived_from"];
  if (
    typeof capability !== "string" ||
    typeof classification !== "string" ||
    !Array.isArray(derived) ||
    derived.some((name) => typeof name !== "string")
  ) {
    return null;
  }
  return {
    required_capability: capability,
    classification,
    derived_from: derived as string[],
  };
}

/** The field a person names an entity in. */
export const ENTITY_FIELD = "entity";

/**
 * The form an entity is named in.
 *
 * A form rather than a list, and that is the whole of what this control has to get right.
 * See `THE_CONSOLE_DOES_NOT_KNOW_WHAT_IS_CLASSIFIED`: there is no route that enumerates the
 * classified entities and there must not be one, so a person types a name and is answered or
 * refused identically whichever kind of nothing is behind it.
 *
 * Frozen and declared once at module level, because it does not depend on any answer and
 * because `SchemaForm` memoises on the schema's identity.
 */
export const CLASSIFICATION_QUERY_SCHEMA: RJSFSchema = Object.freeze<RJSFSchema>({
  type: "object",
  required: [ENTITY_FIELD],
  properties: {
    [ENTITY_FIELD]: { type: "string", title: "Entity", minLength: 1 },
  },
});

export const CLASSIFICATION_QUERY_UI: UiSchema = Object.freeze<UiSchema>({
  "ui:submitButtonOptions": { submitText: "Show its classification" },
});

/** The entity somebody named, or null. One key, read by name. */
export function submittedEntity(data: unknown): string | null {
  if (typeof data !== "object" || data === null) {
    return null;
  }
  const named = (data as Record<string, unknown>)[ENTITY_FIELD];
  return typeof named === "string" && named !== "" ? named : null;
}

// ------------------------------------------------------------ an uploaded table (M7.5.3)

/** The files the upload reads, as `brain.knowledge.table_file.TABLE_SUFFIXES` names them. */
export const TABLE_FILE_ACCEPT = ".csv,.xlsx";

/** Where the API holds an uploaded table's rows. The entity is the address. */
export function tableApiPath(entity: string): string {
  return `${classificationApiPath(entity)}/table`;
}

/** Where a mark is reviewed, and where it is applied. */
export function markReviewApiPath(entity: string, column: string): string {
  return `${classificationApiPath(entity)}/columns/${encodeURIComponent(column)}/marks/review`;
}

export function markApiPath(entity: string, column: string): string {
  return `${classificationApiPath(entity)}/columns/${encodeURIComponent(column)}/marks`;
}

/** Bytes as base64, without a library, as `brain.classification_routes.TableUpload` takes them. */
export function base64Of(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}

/** The body of one upload, as the route's `TableUpload` declares it. The entity is the address. */
export interface TableUpload {
  readonly title: string;
  readonly filename: string;
  readonly content_base64: string;
  readonly key_column: string | null;
}

/**
 * The upload body, or null when something the route requires is missing.
 *
 * Built from named values rather than from a form's state, for `submittedEdit`'s reason.
 */
export function uploadBody(
  title: string,
  filename: string,
  bytes: Uint8Array | null,
  keyColumn: string,
): TableUpload | null {
  if (title.trim() === "" || filename === "" || bytes === null || bytes.length === 0) {
    return null;
  }
  return {
    title: title.trim(),
    filename,
    content_base64: base64Of(bytes),
    key_column: keyColumn.trim() === "" ? null : keyColumn.trim(),
  };
}

/** What an upload said: the API's refusal, or the classification it produced. */
export interface Uploaded {
  readonly refused: string;
  readonly page: ClassificationPage | null;
}

/** Read `brain.classification_routes.TableUploaded`. An unreadable body is neither. */
export function readUploaded(payload: unknown): Uploaded {
  if (typeof payload !== "object" || payload === null) {
    return { refused: "", page: null };
  }
  const body = payload as { refused?: unknown; classification?: unknown };
  const refused = typeof body.refused === "string" ? body.refused : "";
  const page =
    body.classification === null || body.classification === undefined
      ? null
      : readClassification(body.classification);
  return { refused, page: page !== null && page.entity !== "" ? page : null };
}

/** The three marks, as `brain.knowledge.columns.ColumnAccess` names them, in that order. */
export const MARK_WORDS = ["open", "restricted", "derived"] as const;

/** The body of one mark, as the route's `ColumnMark` declares it. */
export interface ColumnMark {
  readonly access: string;
  readonly derived_from: readonly string[];
}

/**
 * The form one column's mark is proposed through.
 *
 * Two fields and no capability: the capability follows from the mark, and a form that let a
 * person type one would let a column marked restricted be governed by the table grant. The
 * derivation options are the table's other columns, for `derivationOptions`'s reason.
 */
export function columnMarkSchema(options: readonly string[]): RJSFSchema {
  return {
    type: "object",
    required: ["access", "derived_from"],
    properties: {
      access: { type: "string", title: "access", enum: [...MARK_WORDS] },
      derived_from: {
        type: "array",
        title: "derived_from",
        maxItems: options.length === 0 ? 0 : MAX_DERIVED_FROM,
        uniqueItems: true,
        items: options.length === 0 ? { type: "string" } : { type: "string", enum: [...options] },
      },
    },
  };
}

export const COLUMN_MARK_UI: UiSchema = Object.freeze<UiSchema>({
  "ui:submitButtonOptions": { submitText: "Review this mark" },
});

/** What one column's mark form starts from: the mark it carries, or restricted. */
export function markDefaults(row: ColumnRow): Record<string, unknown> {
  return {
    access: typeof row.access === "string" ? row.access : "restricted",
    derived_from: [...row.derived_from],
  };
}

/** What the mark form submitted, or null if it was not a mark. Two named keys, nothing else. */
export function submittedMark(data: unknown): ColumnMark | null {
  if (typeof data !== "object" || data === null) {
    return null;
  }
  const fields = data as Record<string, unknown>;
  const access = fields["access"];
  const derived = fields["derived_from"];
  if (
    typeof access !== "string" ||
    !(MARK_WORDS as readonly string[]).includes(access) ||
    !Array.isArray(derived) ||
    derived.some((name) => typeof name !== "string")
  ) {
    return null;
  }
  return { access, derived_from: derived as string[] };
}

/** What applying a mark said: whether it was applied, the verdict, and the table after. */
export interface Applied {
  readonly applied: boolean;
  readonly review: Review;
  readonly page: ClassificationPage;
}

/** Read `brain.classification_routes.MarkApplied`. Unreadable is not applied. */
export function readApplied(payload: unknown): Applied {
  if (typeof payload !== "object" || payload === null) {
    return { applied: false, review: readReview(null), page: readClassification(null) };
  }
  const body = payload as { applied?: unknown; review?: unknown; classification?: unknown };
  return {
    applied: body.applied === true,
    review: readReview(body.review),
    page: readClassification(body.classification),
  };
}
