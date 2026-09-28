/**
 * The Dashboard, at the index route. Eager: it reaches nothing the shell does not already reach, so
 * a chunk would buy a round trip and save no bytes.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Overview } from "./Overview";

export const routes: PageRoutes = [
  { index: true, element: <Overview /> },
];
