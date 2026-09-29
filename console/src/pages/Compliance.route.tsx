/**
 * Compliance: breach cases, sensitive topics and the processing register as three views at their
 * own addresses, and one breach case's page. One module because one authority answers all three.
 *
 * Task ids: M27.10.1, M27.16.1
 */

import type { PageRoutes } from "../routes/page";
import { BreachCase } from "./Compliance";
import { Compliance } from "./Compliance";

export const routes: PageRoutes = [
  { path: "compliance", element: <Compliance /> },
  { path: "compliance/:view", element: <Compliance /> },
  { path: "compliance/breaches/:caseId", element: <BreachCase /> },
];
