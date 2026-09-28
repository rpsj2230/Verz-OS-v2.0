/**
 * Roles, the first tab of Roles and permissions.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Roles } from "./Roles";

export const routes: PageRoutes = [
  { path: "roles", element: <Roles /> },
];
