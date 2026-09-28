/**
 * One agent's workspace, at the address `brain.console.workspace.deep_link` spells: an agent, and
 * one tab of it.
 *
 * Loaded on demand for a smaller reason: it imports `agent-workspace.css`, and somebody who never
 * opens an agent should not download it. `tests/agent-page.test.tsx` walks the static graph from
 * `main.tsx` and fails when the workspace is reachable from it.
 *
 * Task ids: M27.10.1
 */

import { lazy } from "react";
import type { PageRoutes } from "../routes/page";

const Agent = lazy(async () => ({ default: (await import("./Agent")).Agent }));

export const routes: PageRoutes = [
  { path: "agents/:agentId", element: <Agent /> },
  { path: "agents/:agentId/:tab", element: <Agent /> },
];
