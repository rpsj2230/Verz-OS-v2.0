/**
 * Scopes, a tab of Roles and permissions.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Scopes } from "./Scopes";

export const routes: PageRoutes = [
  { path: "scopes", element: <Scopes /> },
];
