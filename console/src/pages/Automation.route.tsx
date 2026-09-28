/**
 * One automation's page: its Dashboard at the bare address, and its Profile and About views.
 *
 * Loaded on demand, because it carries the change dialogs and the schedule form, and somebody who
 * only reads the list should not download them.
 *
 * Task ids: M27.12.3, M27.16.1
 */

import { lazy } from "react";
import type { PageRoutes } from "../routes/page";

const Automation = lazy(async () => ({ default: (await import("./Automation")).Automation }));

export const routes: PageRoutes = [
  { path: "automations/:automationId", element: <Automation /> },
  { path: "automations/:automationId/:view", element: <Automation /> },
];
