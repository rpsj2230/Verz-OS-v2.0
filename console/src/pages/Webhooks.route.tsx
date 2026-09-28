/**
 * Webhooks, E2 of Channels and notifications: who outside the company is told when something
 * happens here, and one subscriber's page with its Dashboard, Profile and About views.
 *
 * Task ids: M27.10.1, M27.8.12, M27.16.1
 */

import { lazy } from "react";
import type { PageRoutes } from "../routes/page";
import { Webhooks } from "./Webhooks";

const Webhook = lazy(async () => ({ default: (await import("./Webhook")).Webhook }));

export const routes: PageRoutes = [
  { path: "webhooks", element: <Webhooks /> },
  { path: "webhooks/:id", element: <Webhook /> },
  { path: "webhooks/:id/:view", element: <Webhook /> },
];
