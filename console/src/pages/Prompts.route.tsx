/**
 * Prompts, a tab of Agents: the house rules every agent opens with, and each agent's own
 * instructions. See `brain.prompt_routes`.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Prompts } from "./Prompts";

export const routes: PageRoutes = [
  { path: "prompts", element: <Prompts /> },
];
