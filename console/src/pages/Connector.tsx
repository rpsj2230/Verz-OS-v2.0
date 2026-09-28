/**
 * One source's page, at `/connectors/{name}` and `/connectors/{name}/{view}`. The page itself is
 * `connectors/ConnectorDetailPage.tsx`, built on the shared page kit; this module is what the route
 * file loads on demand, so somebody who never opens a source does not download it.
 *
 * Task ids: M27.11.9, M27.16.1
 */

import { useParams } from "react-router-dom";
import { ConnectorDetailPage } from "./connectors/ConnectorDetailPage";

export function Connector() {
  const { connector, view } = useParams();
  return connector === undefined ? null : <ConnectorDetailPage name={connector} tab={view} />;
}
