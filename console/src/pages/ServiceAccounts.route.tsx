/**
 * Service accounts and API keys: the caller's own integrations. One account's page is
 * `ServiceAccount.route.tsx`.
 *
 * Task ids: M27.10.1, M27.16.1
 */

import type { PageRoutes } from "../routes/page";
import { ServiceAccounts } from "./ServiceAccounts";

export const routes: PageRoutes = [
  { path: "service-accounts", element: <ServiceAccounts /> },
];
