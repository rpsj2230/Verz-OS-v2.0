/**
 * Import and export: what can move and the audit trail export, taken as a confirmed write.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { DataTransfer } from "./DataTransfer";

export const routes: PageRoutes = [
  { path: "import-export", element: <DataTransfer /> },
];
