/**
 * Storage: the buckets, each one's retention and why, and where the store is.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Storage } from "./Storage";

export const routes: PageRoutes = [
  { path: "storage", element: <Storage /> },
];
