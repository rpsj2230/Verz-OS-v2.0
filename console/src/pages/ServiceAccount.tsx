/**
 * One service account's page, at `/service-accounts/{id}`. The page itself is
 * `service-accounts/ServiceAccountDetailPage.tsx`, built on the shared page kit.
 *
 * Task ids: M27.11.5, M27.16.1
 */

import { useParams } from "react-router-dom";
import { ServiceAccountDetailPage } from "./service-accounts/ServiceAccountDetailPage";

export function ServiceAccount() {
  const { clientId } = useParams();
  return clientId === undefined ? null : <ServiceAccountDetailPage clientId={clientId} />;
}
