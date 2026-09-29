/**
 * Department, SCREEN 2's overview, which a department's console offers where the company's offers
 * the Dashboard, with its Profile and About views at addresses of their own. No segment names the
 * department: it is the reader's own grants, decided by the API, so there is no address that could
 * name somebody else's.
 *
 * Task ids: M27.10.1, M27.16.1
 */

import type { PageRoutes } from "../routes/page";
import { Department } from "./Department";

export const routes: PageRoutes = [
  { path: "department", element: <Department /> },
  { path: "department/:view", element: <Department /> },
];
