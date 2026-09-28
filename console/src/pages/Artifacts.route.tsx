/**
 * Artifacts, at the screen's key. An artifact has no page of its own.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Artifacts } from "./Artifacts";

export const routes: PageRoutes = [
  { path: "artifacts", element: <Artifacts /> },
];
