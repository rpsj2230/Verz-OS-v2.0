/**
 * Adoption, a tab of Usage and cost.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Adoption } from "./Adoption";

export const routes: PageRoutes = [
  { path: "adoption", element: <Adoption /> },
];
