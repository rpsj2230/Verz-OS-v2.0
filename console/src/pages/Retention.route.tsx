/**
 * Retention, legal holds and erasure, at the screen's key.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Retention } from "./Retention";

export const routes: PageRoutes = [
  { path: "retention", element: <Retention /> },
];
