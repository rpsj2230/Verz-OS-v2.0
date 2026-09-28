/**
 * Webhooks: who outside the company is told when something happens here. A subscriber is changed
 * from the listing rather than opened.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Webhooks } from "./Webhooks";

export const routes: PageRoutes = [
  { path: "webhooks", element: <Webhooks /> },
];
