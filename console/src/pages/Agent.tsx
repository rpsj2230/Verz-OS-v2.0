/**
 * One agent's page, at the address `brain.console.workspace.deep_link` spells: `/agents/{id}` and
 * `/agents/{id}/{view}`. The page itself is `agents/AgentDetailPage.tsx`, built on the shared page
 * kit; this module keeps the name `App.tsx` loads on demand, so somebody who never opens an agent
 * does not download it, which `tests/agent-page.test.tsx` holds against the static import graph.
 *
 * Task ids: M39.1.2.1, M39.1.2.4, M27.10.2
 */

import { useParams } from "react-router-dom";
import { AgentDetailPage } from "./agents/AgentDetailPage";

export function Agent() {
  const { agentId, tab } = useParams();
  return agentId === undefined ? null : <AgentDetailPage agentId={agentId} tab={tab} />;
}
