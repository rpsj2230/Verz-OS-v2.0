/**
 * Elevation requests, a tab of Access reviews and elevation: the break-glass landing and the rules.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Elevation } from "./Elevation";

export const routes: PageRoutes = [
  { path: "elevation", element: <Elevation /> },
];
