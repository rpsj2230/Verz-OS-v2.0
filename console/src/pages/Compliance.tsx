/**
 * Compliance, at the names the route file and the tests import. The pages are in `compliance/`,
 * built on the shared page kit: `CompliancePage.tsx` for the three views and `BreachPage.tsx` for one
 * breach case.
 *
 * Task ids: M24.2.2, M24.2.3, M24.2.4, M27.16.1
 */

import { useParams } from "react-router-dom";
import { BreachPage } from "./compliance/BreachPage";
import { CompliancePage } from "./compliance/CompliancePage";

export { COMPLIANCE_HEADING, COMPLIANCE_LEDE, READING_COMPLIANCE } from "./compliance/CompliancePage";

export function Compliance() {
  const { view } = useParams();
  return <CompliancePage view={view} />;
}

export function BreachCase() {
  const { caseId } = useParams();
  return caseId === undefined ? null : <BreachPage key={caseId} caseId={caseId} />;
}
