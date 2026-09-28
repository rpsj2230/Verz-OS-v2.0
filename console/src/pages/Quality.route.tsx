/**
 * Quality and canaries, at the screen's key.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Quality } from "./Quality";

export const routes: PageRoutes = [
  { path: "quality", element: <Quality /> },
];
