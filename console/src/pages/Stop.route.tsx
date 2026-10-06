/**
 * Stop: everything stopped this reader may see, stopping at once, and resuming with a written
 * reason. See `brain.halt_routes`.
 *
 * Task ids: M27.10.1, M27.2.8
 */

import type { PageRoutes } from "../routes/page";
import { StopPage } from "./operations/StopPage";

export const routes: PageRoutes = [{ path: "stop", element: <StopPage /> }];
