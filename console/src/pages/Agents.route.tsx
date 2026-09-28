/**
 * The Agents list, built on the shared page kit (`agents/AgentsPage.tsx`), which is where an agent
 * page's trail leads back to.
 *
 * Task ids: M27.10.1, M27.10.2
 */

import type { PageRoutes } from "../routes/page";
import { Agents } from "./Agents";

export const routes: PageRoutes = [
  { path: "agents", element: <Agents /> },
];
