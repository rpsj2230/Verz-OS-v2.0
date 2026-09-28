/**
 * This install, a tab of Version and updates. Each install path is the screen's key in
 * `brain.console.screens`, which `brain.ops.console_screens.routed_screen_keys` matches.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Install } from "./Install";

export const routes: PageRoutes = [
  { path: "install", element: <Install /> },
];
