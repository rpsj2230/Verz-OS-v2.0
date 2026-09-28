/**
 * One source's page: its Dashboard at the bare address, and its Profile and About views.
 *
 * Loaded on demand, because it carries the edit and key forms and Connect Lark, and somebody who
 * only reads the list should not download them.
 *
 * Task ids: M27.11.9, M27.16.1
 */

import { lazy } from "react";
import type { PageRoutes } from "../routes/page";

const Connector = lazy(async () => ({ default: (await import("./Connector")).Connector }));

export const routes: PageRoutes = [
  { path: "connectors/:connector", element: <Connector /> },
  { path: "connectors/:connector/:view", element: <Connector /> },
];
