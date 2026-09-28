/**
 * People. The bare path is where somebody arrives from the menu and the segment is the subject key,
 * resolved against the page.
 *
 * Loaded on demand: it mounts the form library to write a grant, which is the measurement the
 * records route is split for.
 *
 * Task ids: M27.10.1
 */

import { lazy } from "react";
import type { PageRoutes } from "../routes/page";

const People = lazy(async () => ({ default: (await import("./People")).People }));

export const routes: PageRoutes = [
  { path: "people", element: <People /> },
  { path: "people/:subject", element: <People /> },
];
