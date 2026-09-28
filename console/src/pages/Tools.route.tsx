/**
 * Tools, a tab of Skills and tools: every tool with what it needs and does, and the switch that
 * stops one.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Tools } from "./Tools";

export const routes: PageRoutes = [
  { path: "tools", element: <Tools /> },
];
