/**
 * Skills, SCREEN 6. The segment is the skill's name, resolved against the page rather than a route
 * of its own.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Skills } from "./Skills";

export const routes: PageRoutes = [
  { path: "skills", element: <Skills /> },
  { path: "skills/:name", element: <Skills /> },
];
