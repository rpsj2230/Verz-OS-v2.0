/**
 * Exporting the knowledge inventory (M25.3.3): every document the reader may see on this list, with
 * its level and department and who that reaches, its steward and its review, as a file.
 *
 * **The route decides what the file holds and records that it left.** `POST /knowledge/inventory`
 * builds the document from exactly the rows the Knowledge list would show this reader, records it on
 * the Exports log under their name with the reason and reference given, and hands the document over
 * only after that record has committed. It carries no document's text, and no line about a document
 * it left out. This took the place of the inert "Export inventory" control, whose sentence said an
 * unrecorded export of titles was the channel the Exports screen exists to watch: the route that
 * records it has landed, so the sentence went in the same commit.
 *
 * **The form is `ReportExport`'s**, shared with the access certification report.
 *
 * Task ids: M25.3.3, M27.15.40, M27.16.1
 */

import { request } from "../../api/client";
import { ReportExport, type ReportAsked } from "../exports/ReportExport";

export const KNOWLEDGE_EXPORT_API_PATH = "/knowledge/inventory";

export const EXPORT_LABEL = "Export inventory";
export const EXPORT_DESCRIPTION =
  "A file listing every document on this screen with who may read it, its steward and its review, and none of what it says. It is recorded on the Exports log under your name.";
export const EXPORT_QUESTION = "Export the knowledge inventory?";
export const EXPORT_CONSEQUENCE =
  "The file lists every document you may see, with its level, its department, its steward and its review date. It holds no document's text. It is recorded on the Exports log under your name with this reason and reference, and is not kept on the server.";

export function KnowledgeExport() {
  return (
    <ReportExport
      send={(asked: ReportAsked) => request<unknown>(KNOWLEDGE_EXPORT_API_PATH, { method: "POST", body: asked })}
      label={EXPORT_LABEL}
      description={EXPORT_DESCRIPTION}
      question={EXPORT_QUESTION}
      consequence={EXPORT_CONSEQUENCE}
      formId="knowledge-export"
    />
  );
}
