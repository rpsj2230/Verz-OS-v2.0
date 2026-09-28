/**
 * Models and health, SCREEN 11, at the screen's key. Its Edit routing action links to the routing
 * matrix rather than being a second editor here.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Models } from "./Models";

export const routes: PageRoutes = [
  { path: "models", element: <Models /> },
];
