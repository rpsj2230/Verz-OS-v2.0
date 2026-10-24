/**
 * Exporting the access certification report (M27.15.21): every grant and pack the reviewer may
 * decide, with who holds it, who granted it, when it lapses and its last review, as a file.
 *
 * **The route decides what the file holds and records that it left.** `POST
 * /govern/access-review/export` builds the document from exactly the rows the review screen would
 * show this reviewer, records it on the Exports log (`ops.data_export`, whose trigger writes the
 * ledger entry) under their name with the reason and reference given, and hands the document over
 * only after that record has committed. The file names no row it leaves out and carries no count of
 * them.
 *
 * **The form is `ReportExport`'s**, which the knowledge inventory takes its export through as well;
 * this file holds the words that are the certification report's own. The constants the review tests
 * read are re-exported from there, so a test of this screen still reads them at the address it
 * always did.
 *
 * Task ids: M27.15.21, M27.16.1
 */

import { request } from "../../api/client";
import { ReportExport, type ReportAsked } from "../exports/ReportExport";
import { ACT_LABELS } from "./reviewActions";

export {
  EXPORT_REASONS,
  KEEP_IT,
  REASON_BLANK,
  REASON_HINT,
  REFERENCE_BLANK,
  REFERENCE_HINT,
  REFERENCE_PATTERN,
  REFERENCE_SHAPE,
  REVIEW_EXPORT,
} from "../exports/ReportExport";

export const CERTIFICATION_EXPORT_API_PATH = "/govern/access-review/export";

export const EXPORT_DESCRIPTION =
  "A file of every grant listed on this screen with its last review, for whoever certifies access. It is recorded on the Exports log under your name.";
export const EXPORT_QUESTION = "Export the access certification report?";
export const EXPORT_CONSEQUENCE =
  "The file holds every grant you may review, with who holds it, who granted it and its last review. It is recorded on the Exports log under your name with this reason and reference, and is not kept on the server.";

export function CertificationExport() {
  return (
    <ReportExport
      send={(asked: ReportAsked) => request<unknown>(CERTIFICATION_EXPORT_API_PATH, { method: "POST", body: asked })}
      label={ACT_LABELS.exportReport}
      description={EXPORT_DESCRIPTION}
      question={EXPORT_QUESTION}
      consequence={EXPORT_CONSEQUENCE}
      formId="certification-export"
    />
  );
}
