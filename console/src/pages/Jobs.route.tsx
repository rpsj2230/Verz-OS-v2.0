/**
 * Scheduled jobs: every job the worker's schedule starts, how it last went, and pause, resume and
 * run now. See `brain.jobs_routes`.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Jobs } from "./Jobs";

export const routes: PageRoutes = [
  { path: "jobs", element: <Jobs /> },
];
