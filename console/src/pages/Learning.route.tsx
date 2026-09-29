/**
 * Learning, SCREEN 8: what the system has learnt, one tier per view. The bare path is the first
 * tier and each other view has an address of its own; a learning opens in a drawer on its view.
 *
 * Task ids: M27.10.1, M27.16.1
 */

import type { PageRoutes } from "../routes/page";
import { Learning } from "./Learning";

export const routes: PageRoutes = [
  { path: "learning", element: <Learning /> },
  { path: "learning/:view", element: <Learning /> },
];
