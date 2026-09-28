/**
 * The Routing page of the Models and routing module: the failover matrix, one step's editor at its
 * own address, and what changing it takes. The page itself is `models/RoutingPage.tsx`, built on
 * the shared page kit; this module keeps the name the route file loads on demand.
 *
 * Task ids: M5.3.3, M27.15.38, M27.16.1
 */

import { RoutingPage } from "./models/RoutingPage";

export function Matrix() {
  return <RoutingPage />;
}
