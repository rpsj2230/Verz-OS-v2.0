/**
 * The routing matrix, a tab of Models and routing. The step being edited is a path segment; the
 * bare path is the matrix on its own.
 *
 * Loaded on demand, as it always was, so the entry chunk stays the shell's.
 *
 * Task ids: M5.3.3, M27.10.1, M27.16.1
 */

import { lazy } from "react";
import type { PageRoutes } from "../routes/page";

const Matrix = lazy(async () => ({ default: (await import("./Matrix")).Matrix }));

export const routes: PageRoutes = [
  { path: "routing", element: <Matrix /> },
  { path: "routing/:rungId", element: <Matrix /> },
];
