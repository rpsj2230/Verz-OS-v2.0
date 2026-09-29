/**
 * The Audit log's pages, at the names the route file and the tests import. The pages themselves are
 * in `audit/`, built on the shared page kit: `AuditPage.tsx` for the ledger, `AuditSubjectPage.tsx`
 * for one subject and `VerifyPage.tsx` for the check of the chain.
 *
 * Task ids: M27.7.13, M27.16.1
 */

import { useParams } from "react-router-dom";
import { AuditSubjectPage } from "./audit/AuditSubjectPage";

export { AuditPage as Audit, AUDIT_HEADING, AUDIT_LEDE, ENTRIES_LABEL, NO_ENTRIES, READING_THE_LEDGER } from "./audit/AuditPage";
export { CHECK_HEAD_LABEL, VerifyPage as VerifyLedger, WALK_LABEL } from "./audit/VerifyPage";

/** One subject's page, at `/audit/subject/{kind}/{id}` and its `permissions` view. */
export function AuditSubject() {
  const { kind, id, view } = useParams();
  return kind === undefined || id === undefined ? null : <AuditSubjectPage key={`${kind}:${id}`} kind={kind} id={id} view={view} />;
}
