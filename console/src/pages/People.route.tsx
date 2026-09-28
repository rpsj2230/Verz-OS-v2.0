/**
 * People: the list at the bare path, one person at `people/{id}`, and each of their views at
 * `people/{id}/{view}`.
 *
 * Loaded on demand, because a person's page carries six views and their forms, and somebody who
 * never opens People should not download them.
 *
 * Task ids: M27.10.1, M27.16.1
 */

import { lazy } from "react";
import type { PageRoutes } from "../routes/page";

const People = lazy(async () => ({ default: (await import("./People")).People }));

export const routes: PageRoutes = [
  { path: "people", element: <People /> },
  { path: "people/:personId", element: <People /> },
  { path: "people/:personId/:view", element: <People /> },
];
