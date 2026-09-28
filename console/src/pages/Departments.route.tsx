/**
 * Departments and teams: the list at the bare path, one department at `departments/{slug}`, and each
 * of its views at `departments/{slug}/{view}`. A person's name on either links to their page under
 * `people/`.
 *
 * Task ids: M27.10.1, M27.16.1
 */

import type { PageRoutes } from "../routes/page";
import { Departments } from "./Departments";

export const routes: PageRoutes = [
  { path: "departments", element: <Departments /> },
  { path: "departments/:slug", element: <Departments /> },
  { path: "departments/:slug/:view", element: <Departments /> },
];
