/**
 * Background jobs: every job the worker's schedule starts, and one job's page with its Dashboard,
 * Profile and About views. See `brain.jobs_routes`.
 *
 * One job's page is loaded on demand, because it carries the run history's list and somebody who
 * only reads the list should not download it.
 *
 * Task ids: M27.10.1, M27.15.47
 */

import { lazy } from "react";
import type { PageRoutes } from "../routes/page";
import { Jobs } from "./Jobs";

const Job = lazy(async () => ({ default: (await import("./Job")).Job }));

export const routes: PageRoutes = [
  { path: "jobs", element: <Jobs /> },
  { path: "jobs/:name", element: <Job /> },
  { path: "jobs/:name/:view", element: <Job /> },
];
