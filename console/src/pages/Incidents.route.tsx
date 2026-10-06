/**
 * Incidents: which connected sources are degraded now, since when, and what stops working.
 *
 * Task ids: M27.2.7
 */

import type { PageRoutes } from "../routes/page";
import { IncidentsPage } from "./operations/IncidentsPage";

export const routes: PageRoutes = [{ path: "incidents", element: <IncidentsPage /> }];
