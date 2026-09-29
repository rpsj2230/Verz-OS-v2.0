/**
 * Elevation requests, a tab of Access reviews and elevation: the list, the ask, and one request's page.
 *
 * Task ids: M27.10.1, M27.16.1
 */

import type { PageRoutes } from "../routes/page";
import { Elevation, ElevationRequest } from "./Elevation";

export const routes: PageRoutes = [
  { path: "elevation", element: <Elevation /> },
  { path: "elevation/:requestId", element: <ElevationRequest /> },
];
