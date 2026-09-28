/**
 * Capacity, a tab of Limits, budgets and capacity, at the screen's key, `connections`.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Capacity } from "./Capacity";

export const routes: PageRoutes = [
  { path: "connections", element: <Capacity /> },
];
