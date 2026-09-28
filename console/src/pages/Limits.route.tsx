/**
 * Rate limits, the first tab of Limits, budgets and capacity, at the screen's key.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Limits } from "./Limits";

export const routes: PageRoutes = [
  { path: "limits", element: <Limits /> },
];
