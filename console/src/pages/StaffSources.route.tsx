/**
 * Staff sources, at the screen's own key. The trial is a request this page makes rather than a
 * thing somebody opens.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { StaffSources } from "./StaffSources";

export const routes: PageRoutes = [
  { path: "staff_sources", element: <StaffSources /> },
];
