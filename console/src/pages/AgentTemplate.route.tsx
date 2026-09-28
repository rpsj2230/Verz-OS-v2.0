/**
 * One template's page. Loaded on demand, because it carries the install form, and somebody who only
 * reads the catalogue should not download it.
 *
 * Task ids: M27.11.7, M27.16.1
 */

import { lazy } from "react";
import type { PageRoutes } from "../routes/page";

const AgentTemplate = lazy(async () => ({ default: (await import("./AgentTemplate")).AgentTemplate }));

export const routes: PageRoutes = [{ path: "agent-templates/:templateId", element: <AgentTemplate /> }];
