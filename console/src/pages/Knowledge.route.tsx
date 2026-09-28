/**
 * Knowledge, SCREEN 7, at the screen's own key, `library`. An item has no page of its own.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Knowledge } from "./Knowledge";

export const routes: PageRoutes = [
  { path: "library", element: <Knowledge /> },
];
