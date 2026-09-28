/**
 * Service accounts and API keys: an integration registered, a key issued and shown once, a key
 * revoked and the account retired, each the caller's own. One path: an account has no page of its
 * own.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { ServiceAccounts } from "./ServiceAccounts";

export const routes: PageRoutes = [
  { path: "service-accounts", element: <ServiceAccounts /> },
];
