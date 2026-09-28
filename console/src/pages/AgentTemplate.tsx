/**
 * One template's page, at `/agent-templates/{id}`. The page itself is
 * `agent-templates/AgentTemplateDetailPage.tsx`, built on the shared page kit.
 *
 * Task ids: M27.11.7, M27.16.1
 */

import { useParams } from "react-router-dom";
import { AgentTemplateDetailPage } from "./agent-templates/AgentTemplateDetailPage";

export function AgentTemplate() {
  const { templateId } = useParams();
  return templateId === undefined ? null : <AgentTemplateDetailPage templateId={templateId} />;
}
