/**
 * Connectors, SCREEN 9, at the screen's key in `brain.console.screens`.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Connectors } from "./Connectors";

export const routes: PageRoutes = [
  { path: "connectors", element: <Connectors /> },
];
