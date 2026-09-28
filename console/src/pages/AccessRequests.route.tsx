/**
 * Access requests: ask for a field or a department, and read the requests sent to you.
 *
 * Task ids: M27.10.1
 */

import type { OwnWorkEntry, PageRoutes } from "../routes/page";
import { AccessRequests } from "./AccessRequests";

export const routes: PageRoutes = [
  { path: "access-requests", element: <AccessRequests /> },
];

export const ownWork: OwnWorkEntry = { to: "/access-requests", label: "Access requests", order: 50 };
