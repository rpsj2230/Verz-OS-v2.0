/**
 * One service account's page. Loaded on demand, because it carries the issue and retire acts, and
 * somebody who only reads the list should not download them.
 *
 * Task ids: M27.11.5, M27.16.1
 */

import { lazy } from "react";
import type { PageRoutes } from "../routes/page";

const ServiceAccount = lazy(async () => ({ default: (await import("./ServiceAccount")).ServiceAccount }));

export const routes: PageRoutes = [{ path: "service-accounts/:clientId", element: <ServiceAccount /> }];
