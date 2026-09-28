/**
 * One agent's page, at the address `brain.console.workspace.deep_link` spells: an agent, which
 * opens its Dashboard, and one view or section of it (`profile`, `about`, `automations`, `settings`).
 *
 * Loaded on demand for a smaller reason: it imports `agent-workspace.css` and the automation and
 * model components, and somebody who never opens an agent should not download them.
 * `tests/agent-page.test.tsx` walks the static graph from `main.tsx` and fails when the page is
 * reachable from it.
 *
 * Task ids: M27.10.1, M27.10.2
 */

import { lazy } from "react";
import type { PageRoutes } from "../routes/page";

const Agent = lazy(async () => ({ default: (await import("./Agent")).Agent }));

export const routes: PageRoutes = [
  { path: "agents/:agentId", element: <Agent /> },
  { path: "agents/:agentId/:tab", element: <Agent /> },
];
