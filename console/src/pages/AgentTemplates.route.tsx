/**
 * The template catalogue, at an address of its own rather than under `agents/`, because an agent
 * slug is a path segment there and a template is not an agent.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { AgentTemplates } from "./AgentTemplates";

export const routes: PageRoutes = [
  { path: "agent-templates", element: <AgentTemplates /> },
];
