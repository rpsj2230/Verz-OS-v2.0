/**
 * Errors: failed jobs by kind and failed questions by reference, a tab of Logs and errors. See
 * `brain.error_routes`.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Errors } from "./Errors";

export const routes: PageRoutes = [
  { path: "errors", element: <Errors /> },
];
