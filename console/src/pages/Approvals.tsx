/**
 * The approvals queue and one approval on its own, at the names the route file and the tests
 * import. The pages are in `approvals/`, built on the shared page kit around the phone-first card
 * `styles/approvals.css` draws, which this module imports so it arrives with the page.
 *
 * Task ids: M35.3.1.2, M35.3.1.1, M40.6.1.5, M40.1.2.3, M27.8.6, M27.16.1, M27.15.31
 */

import "../styles/approvals.css";
import { useParams } from "react-router-dom";
import { ApprovalPage } from "./approvals/ApprovalPage";
import { ApprovalsPage } from "./approvals/ApprovalsPage";

export {
  A_DECISION_IS_CLAIMED_ONLY_WHEN_THE_API_CONFIRMS_IT,
  ApprovalCard,
  approvalAddress,
  APPROVALS_ADDRESS,
  APPROVE_LABEL,
  APPROVED_SENTENCE,
  DecisionControls,
  LAPSES_LABEL,
  NO_REASON_CHOSEN,
  OPEN_ON_ITS_OWN,
  RAISED_LABEL,
  REASON_LABEL,
  REJECT_LABEL,
  REJECTED_SENTENCE,
  RUNS_AS_LABEL,
} from "./approvals/ApprovalCard";
export {
  A_CONFIRMATION_IS_DRAWN_WHERE_THE_THUMB_IS,
  APPROVAL_LIST_LABEL,
  APPROVALS_HEADING,
  APPROVALS_LEDE,
  FILTERS_LABEL,
  MORE_APPROVALS,
  NO_APPROVALS,
} from "./approvals/ApprovalsPage";

export function Approvals() {
  const { suspensionId } = useParams();
  return suspensionId === undefined ? <ApprovalsPage /> : <ApprovalPage key={suspensionId} suspensionId={suspensionId} />;
}
