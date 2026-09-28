/**
 * Connectors, the list of every source this release ships, at the screen's key in
 * `brain.console.screens`. One source's page is `Connector.route.tsx`.
 *
 * Task ids: M27.10.1, M27.11.9
 */

import type { PageRoutes } from "../routes/page";
import { Connectors } from "./Connectors";

export const routes: PageRoutes = [
  { path: "connectors", element: <Connectors /> },
];
