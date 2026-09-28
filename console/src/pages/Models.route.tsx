/**
 * The Models and routing module's providers: the list at the screen's key, and one provider's page
 * with its three views, loaded on demand.
 *
 * Task ids: M27.16.1, M27.10.1
 */

import { lazy } from "react";
import type { PageRoutes } from "../routes/page";
import { Models } from "./Models";

const Provider = lazy(async () => ({ default: (await import("./Provider")).Provider }));

export const routes: PageRoutes = [
  { path: "models", element: <Models /> },
  { path: "models/:provider", element: <Provider /> },
  { path: "models/:provider/:view", element: <Provider /> },
];
