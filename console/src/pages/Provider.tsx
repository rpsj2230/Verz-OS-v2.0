/**
 * One provider's page, at `/models/{provider}` and `/models/{provider}/{view}`. The page itself is
 * `models/ProviderDetailPage.tsx`, built on the shared page kit; this module keeps the name the route
 * file loads on demand, so somebody who never opens a provider does not download it.
 *
 * Task ids: M27.16.1, M5.6.4
 */

import { useParams } from "react-router-dom";
import { ProviderDetailPage } from "./models/ProviderDetailPage";

export function Provider() {
  const { provider, view } = useParams();
  return provider === undefined ? null : <ProviderDetailPage provider={provider} view={view} />;
}
