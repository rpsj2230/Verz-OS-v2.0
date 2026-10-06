/**
 * The whole company, a Super Admin's three tabs: everything in the install, all activity and what
 * the company spent. Each is its own address, so a colleague can be sent one view with its filters.
 *
 * Task ids: M33.1.1.1, M33.1.1.2, M33.1.1.3
 */

import type { PageRoutes } from "../routes/page";
import { ActivityPage, ConsumptionPage, EstatePage } from "./company/CompanyPages";

export const routes: PageRoutes = [
  { path: "company/estate", element: <EstatePage /> },
  { path: "company/activity", element: <ActivityPage /> },
  { path: "company/consumption", element: <ConsumptionPage /> },
];
