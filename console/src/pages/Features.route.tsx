/**
 * Features and plugins: which genuinely new features this install has switched on, and the switch.
 * See `brain.feature_routes`.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Features } from "./Features";

export const routes: PageRoutes = [
  { path: "features", element: <Features /> },
];
