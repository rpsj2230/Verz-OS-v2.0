/**
 * One webhook subscriber's page, at `/webhooks/{id}` and `/webhooks/{id}/{view}`. The page itself is
 * `webhooks/WebhookDetailPage.tsx`; this module is what the route file loads on demand.
 *
 * Task ids: M27.8.12, M27.16.1
 */

import { useParams } from "react-router-dom";
import { WebhookDetailPage } from "./webhooks/WebhookDetailPage";

export function Webhook() {
  const { id, view } = useParams();
  return id === undefined ? null : <WebhookDetailPage id={id} tab={view} />;
}
