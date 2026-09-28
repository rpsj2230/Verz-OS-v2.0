/**
 * Packs, the fourth tab of Roles and permissions beside Roles, Capabilities and Scopes.
 *
 * Task ids: M27.15.24, M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Packs } from "./Packs";

export const routes: PageRoutes = [
  { path: "packs", element: <Packs /> },
];
