/**
 * Service levels: a reading of a window, where the window is the request rather than the address.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { ServiceLevels } from "./ServiceLevels";

export const routes: PageRoutes = [
  { path: "service-levels", element: <ServiceLevels /> },
];
