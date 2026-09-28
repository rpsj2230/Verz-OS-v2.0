/**
 * Notifications and email: who this install tells what, the switch that stops a notice, and the
 * email relay.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Notifications } from "./Notifications";

export const routes: PageRoutes = [
  { path: "notifications", element: <Notifications /> },
];
