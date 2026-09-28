/**
 * Backup and recovery, at the screen's key.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Recovery } from "./Recovery";

export const routes: PageRoutes = [
  { path: "recovery", element: <Recovery /> },
];
