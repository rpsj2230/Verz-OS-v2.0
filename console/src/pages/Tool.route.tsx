/**
 * One tool's page, with its switches. Loaded on demand, for the reason every detail page is.
 *
 * Task ids: M12.1.1, M27.16.1
 */

import { lazy } from "react";
import type { PageRoutes } from "../routes/page";

const Tool = lazy(async () => ({ default: (await import("./Tool")).Tool }));

export const routes: PageRoutes = [{ path: "tools/:name", element: <Tool /> }];
