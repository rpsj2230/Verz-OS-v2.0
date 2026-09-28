/**
 * The agent roster, which is where the workspace's way back lands.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Agents } from "./Agents";

export const routes: PageRoutes = [
  { path: "agents", element: <Agents /> },
];
