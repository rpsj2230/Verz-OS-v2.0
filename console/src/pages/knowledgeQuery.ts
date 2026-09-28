/**
 * What adding a document asks the API, and the words the answer is said in. No React.
 *
 * The split is `skillsQuery.ts`' and `governQuery.ts`': this decides what may be asked and how an
 * answer is read, the pages render it (`knowledge/addForms.tsx`), so what a form does about a file it
 * can already tell will be refused is testable without mounting one.
 *
 * **Adding a document is asked of the API** (M7.6.3). The options say which kinds this person may
 * choose, which departments they may add to and which types and sizes the door takes; the form posts
 * the file raw with those words in the address and its name in a header, and shows the API's own
 * sentence when it is refused. Nothing here decides who may add what.
 *
 * The Knowledge list itself is `knowledge/knowledgeDocuments.ts`. The existence-plane library this
 * module used to read (`GET /govern/library`, three facts a row) is no longer drawn: the list reads
 * `GET /knowledge/documents`, which answers every column SCREEN 7 draws for the rows a reader may open.
 *
 * Task ids: M7.6.1, M7.6.3, M27.15.40
 */

/** The console address of the Knowledge list, at the screen's own key in `brain.console.screens`. */
export const KNOWLEDGE_PATH = "/library";

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
