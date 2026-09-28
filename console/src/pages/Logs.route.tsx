/**
 * Logs: the warnings and errors the application kept, redacted on their way in. See
 * `brain.log_routes`.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Logs } from "./Logs";

export const routes: PageRoutes = [
  { path: "logs", element: <Logs /> },
];
