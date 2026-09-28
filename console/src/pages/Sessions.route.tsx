/**
 * Sessions, at the screen's key. A session is ended from the listing rather than opened.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Sessions } from "./Sessions";

export const routes: PageRoutes = [
  { path: "sessions", element: <Sessions /> },
];
