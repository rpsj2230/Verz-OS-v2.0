/**
 * Capabilities, a tab of Roles and permissions.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Capabilities } from "./Capabilities";

export const routes: PageRoutes = [
  { path: "capabilities", element: <Capabilities /> },
];
