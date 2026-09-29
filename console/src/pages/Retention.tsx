/**
 * Retention, legal holds and erasure, at the names the route file and the tests import. The pages
 * are in `retention/`, built on the shared page kit: `RetentionPage.tsx` for the four views and
 * `RetentionDetail.tsx` for one hold and one erasure request.
 *
 * Task ids: M27.7.24, M27.16.1
 */

import { useParams } from "react-router-dom";
import { ErasurePage, HoldPage } from "./retention/RetentionDetail";
import { RetentionPage } from "./retention/RetentionPage";

export { READING_RETENTION, RETENTION_HEADING, RETENTION_LEDE } from "./retention/RetentionPage";

export function Retention() {
  const { view } = useParams();
  return <RetentionPage view={view} />;
}

export function LegalHold() {
  const { holdId } = useParams();
  return holdId === undefined ? null : <HoldPage key={holdId} holdId={holdId} />;
}

export function ErasureRequest() {
  const { requestId } = useParams();
  return requestId === undefined ? null : <ErasurePage key={requestId} requestId={requestId} />;
}
