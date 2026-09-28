/**
 * Departments and teams, the Organisation card of SCREEN 10 at full width. A person's row links to
 * their page under `people/`.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Departments } from "./Departments";

export const routes: PageRoutes = [
  { path: "departments", element: <Departments /> },
];
