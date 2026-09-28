/**
 * Settings: every installation value with where it came from, and branding saved.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Settings } from "./Settings";

export const routes: PageRoutes = [
  { path: "settings", element: <Settings /> },
];
