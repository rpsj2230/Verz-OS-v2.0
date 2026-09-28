/**
 * Spend, a tab of Usage and cost.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Spend } from "./Spend";

export const routes: PageRoutes = [
  { path: "spend", element: <Spend /> },
];
