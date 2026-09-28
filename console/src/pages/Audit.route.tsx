/**
 * The audit log. Its filters and an open subject's history are query parameters, so a colleague can
 * be sent the view and the back button undoes a filter.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Audit } from "./Audit";

export const routes: PageRoutes = [
  { path: "audit", element: <Audit /> },
];
