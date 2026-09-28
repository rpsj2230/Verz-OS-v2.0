/**
 * The routing matrix, a tab of Models and routing. The rung being edited is a path segment; the
 * bare path is the matrix on its own.
 *
 * Loaded on demand, for the records screen's reason: it mounts the same two libraries, so an
 * eager import here would undo the split whatever the records route did.
 *
 * Task ids: M27.10.1
 */

import { lazy } from "react";
import type { PageRoutes } from "../routes/page";

const Matrix = lazy(async () => ({ default: (await import("./Matrix")).Matrix }));

export const routes: PageRoutes = [
  { path: "routing", element: <Matrix /> },
  { path: "routing/:rungId", element: <Matrix /> },
];
