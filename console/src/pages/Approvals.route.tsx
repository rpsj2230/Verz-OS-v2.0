/**
 * The approvals queue, and one approval on its own, which is where a link from a chat lands.
 *
 * Loaded on demand for the workspace's reason: it imports `approvals.css`, and a person who never
 * opens approvals should not download it.
 *
 * Task ids: M27.10.1
 */

import { lazy } from "react";
import type { OwnWorkEntry, PageRoutes } from "../routes/page";

const Approvals = lazy(async () => ({ default: (await import("./Approvals")).Approvals }));

export const routes: PageRoutes = [
  { path: "approvals", element: <Approvals /> },
  { path: "approvals/:suspensionId", element: <Approvals /> },
];

export const ownWork: OwnWorkEntry = { to: "/approvals", label: "My approvals", order: 30 };
