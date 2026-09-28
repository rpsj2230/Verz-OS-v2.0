/**
 * Subscribers, a tab of Notifications and email: who is told what, and how one stops.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Subscribers } from "./Subscribers";

export const routes: PageRoutes = [
  { path: "subscribers", element: <Subscribers /> },
];
