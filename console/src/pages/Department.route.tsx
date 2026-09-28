/**
 * Department, SCREEN 2's overview, which a department's console offers where the company's offers
 * the Dashboard. One path and no parameter: the department is the reader's own grants, decided by
 * the API, so there is no segment that could name somebody else's.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Department } from "./Department";

export const routes: PageRoutes = [
  { path: "department", element: <Department /> },
];
