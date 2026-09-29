/**
 * New agent, the drafts list and one draft, under the Agents list they are reached from.
 *
 * The draft page is loaded on demand, because it mounts the builder's form and the procedure canvas,
 * the two heaviest libraries in the console; `tests/bundle-split.test.ts` follows this file and fails
 * when it reaches either without a dynamic import. The other two pages are the kit alone.
 *
 * Task ids: M27.11.6
 */

import { lazy } from "react";
import type { PageRoutes } from "../routes/page";
import { DraftsPage } from "./agents/DraftsPage";
import { NewAgentPage } from "./agents/NewAgentPage";

const AgentDraft = lazy(async () => ({ default: (await import("./AgentDraft")).AgentDraft }));

export const routes: PageRoutes = [
  { path: "agents/new", element: <NewAgentPage /> },
  { path: "agents/drafts", element: <DraftsPage /> },
  { path: "agents/drafts/:draftId", element: <AgentDraft /> },
  { path: "agents/drafts/:draftId/:step", element: <AgentDraft /> },
];
