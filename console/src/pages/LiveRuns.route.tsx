/**
 * Live runs. One path and no parameter: a run is a row with nothing to open, and the path is the
 * screen's key in `brain.console.screens`, which is what
 * `brain.ops.console_screens.routed_screen_keys` matches.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { LiveRuns } from "./LiveRuns";

export const routes: PageRoutes = [
  { path: "runs", element: <LiveRuns /> },
];
