/**
 * Compliance: sensitive-topic routing, the processing register and breach cases, one page because
 * one authority answers all three.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Compliance } from "./Compliance";

export const routes: PageRoutes = [
  { path: "compliance", element: <Compliance /> },
];
