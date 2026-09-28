/**
 * Usage and cost, at the screen's key. The window is a control on the page rather than the address.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Usage } from "./Usage";

export const routes: PageRoutes = [
  { path: "usage", element: <Usage /> },
];
