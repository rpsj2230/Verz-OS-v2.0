/**
 * Learning, SCREEN 8. The review is one page and a learning has no address.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Learning } from "./Learning";

export const routes: PageRoutes = [
  { path: "learning", element: <Learning /> },
];
