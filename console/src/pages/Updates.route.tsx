/**
 * Version and updates, at the screen's key.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Updates } from "./Updates";

export const routes: PageRoutes = [
  { path: "updates", element: <Updates /> },
];
