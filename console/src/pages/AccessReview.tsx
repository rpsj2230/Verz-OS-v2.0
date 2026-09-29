/**
 * Access review's pages, at the names the route file and the tests import. The pages themselves are
 * in `review/`, built on the shared page kit: `ReviewPage.tsx` for the list and `HoldingPage.tsx` for
 * one grant or pack under review.
 *
 * Task ids: M27.7.9, M27.16.1
 */

import { useParams } from "react-router-dom";
import { HoldingPage } from "./review/HoldingPage";

export { ReviewPage as AccessReview, REVIEW_HEADING, REVIEW_LEDE } from "./review/ReviewPage";

/** One holding's page, at `/access_review/{kind}/{row id}`. */
export function Holding() {
  const { kind, rowId } = useParams();
  return kind === undefined || rowId === undefined ? null : <HoldingPage key={`${kind}:${rowId}`} kind={kind} rowId={rowId} />;
}
