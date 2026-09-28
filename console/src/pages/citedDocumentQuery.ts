/**
 * The document a citation on the Ask screen links to: its address, what the API sends for it, and
 * which passage the link named.
 *
 * **The passage is named in the fragment and nowhere else.** `brain.gate.provenance.Anchor.fragment`
 * builds `chunk=<id>&page=<n>`, the Ask screen puts it after the `#`, and a fragment is never sent
 * to a server, so which passage a person followed is in no request log. `anchorOf` reads it back
 * here and the page marks that passage. See `A_PASSAGE_IS_NAMED_IN_THE_FRAGMENT`.
 *
 * **The document is read at the reader's own reach.** `brain.cited_document_routes` reads it
 * through the handler and the policy the answer went through, and answers a withheld document and
 * an absent one with the same 404, which this console draws in the API's own words and does not
 * explain.
 *
 * Task ids: M8.1.2
 */

/** Written down because the fragment is the only place the passage's position may travel. */
export const A_PASSAGE_IS_NAMED_IN_THE_FRAGMENT =
  "The chunk a citation names is put after the address's #, which a browser never sends to a " +
  "server, so the passage somebody followed is not in any access log. The page reads it from " +
  "the address it was opened at and marks that passage; the request asks for the document.";

/** The console address a document citation opens, under the Ask screen's own. */
export const CITED_DOCUMENT_ADDRESS = "/ask/documents";

/** The heading over the document, when its title cannot be shown to this reader. */
export const UNTITLED = "A cited document";

/** While the document is being read. */
export const READING_THE_DOCUMENT = "Reading the document.";

/** Said above the passages. What the page is, and that the reader's own reach decided it. */
export const CITED_DOCUMENT_LEDE =
  "The passages of this document you are able to read, in order. The passage the answer cited is marked.";

/** Said when no passage of the document came back, which the route answers as a 404 today. */
export const NO_PASSAGES = "Nothing in this document is here for you to read.";

/** Said when the read stopped before the end of a long document. Never how much is left. */
export const MORE_THAN_SHOWN = "This document is longer than this page shows.";

/** Said when the cited passage is not among those shown. */
export const CITED_PASSAGE_NOT_SHOWN =
  "The passage the answer cited is further into the document than this page shows.";

/** Said when the cited passage is not in the document as this reader may read it now. */
export const CITED_PASSAGE_GONE =
  "The passage the answer cited is not in this document as you are able to read it now.";

/** The label on the passage the answer cited, which a screen reader announces with it. */
export const CITED_HERE = "Cited in the answer";

/** When the API sent something this page cannot read. */
export const UNREADABLE_DOCUMENT = "The console could not read the answer to that.";

/** Where the API serves one document. Encoded, because the reference came from an address. */
export function citedDocumentApiPath(documentId: string): string {
  return `/knowledge/documents/${encodeURIComponent(documentId)}`;
}

/** The console address a document citation links to, with the passage in the fragment. */
export function citedDocumentAddress(documentId: string, anchor: string): string {
  const base = `${CITED_DOCUMENT_ADDRESS}/${encodeURIComponent(documentId)}`;
  return anchor === "" ? base : `${base}#${anchor}`;
}

/** The chunk a fragment names, or the empty string when it names none. */
export function anchorOf(hash: string): string {
  const fragment = hash.startsWith("#") ? hash.slice(1) : hash;
  for (const part of fragment.split("&")) {
    const [key, value] = part.split("=", 2);
    if (key === "chunk" && value !== undefined) {
      return decodeURIComponent(value);
    }
  }
  return "";
}

/** One passage as the API sent it. */
export interface CitedPassageView {
  readonly chunkId: string;
  readonly section: string;
  readonly text: string;
  readonly updatedAt: string;
}

/** The document as the API sent it. No count anywhere: `truncated` says only that there is more. */
export interface CitedDocumentView {
  readonly documentId: string;
  readonly title: string;
  readonly passages: readonly CitedPassageView[];
  readonly truncated: boolean;
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/** The body, or null when it is not the shape `CitedDocument` declares. */
export function readCitedDocument(body: unknown): CitedDocumentView | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }
  const fields = body as Record<string, unknown>;
  if (typeof fields["document_id"] !== "string" || !Array.isArray(fields["passages"])) {
    return null;
  }
  const passages: CitedPassageView[] = [];
  for (const one of fields["passages"] as unknown[]) {
    if (typeof one !== "object" || one === null) {
      return null;
    }
    const row = one as Record<string, unknown>;
    if (typeof row["chunk_id"] !== "string" || typeof row["text"] !== "string") {
      return null;
    }
    passages.push({
      chunkId: row["chunk_id"],
      section: text(row["section"]),
      text: row["text"],
      updatedAt: text(row["updated_at"]),
    });
  }
  return {
    documentId: fields["document_id"],
    title: text(fields["title"]),
    passages,
    truncated: fields["truncated"] === true,
  };
}
