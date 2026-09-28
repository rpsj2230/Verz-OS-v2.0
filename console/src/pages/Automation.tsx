/**
 * One automation's page, at `/automations/{id}` and `/automations/{id}/{view}`. The page itself is
 * `automations/AutomationDetailPage.tsx`, built on the shared page kit; this module is what the route
 * file loads on demand, so somebody who never opens an automation does not download it.
 *
 * Task ids: M27.12.3, M27.16.1
 */

import { useParams } from "react-router-dom";
import { AutomationDetailPage } from "./automations/AutomationDetailPage";

export function Automation() {
  const { automationId, view } = useParams();
  return automationId === undefined ? null : <AutomationDetailPage id={automationId} tab={view} />;
}
