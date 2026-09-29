/**
 * One draft of an agent, at `/agents/drafts/{id}` and `/agents/drafts/{id}/{step}`. The page itself is
 * `agents/DraftPage.tsx`; this module keeps the name the route file loads on demand, so somebody who
 * never opens a draft does not download the form library and the canvas it mounts.
 *
 * Task ids: M27.11.6
 */

import { useParams } from "react-router-dom";
import { DraftPage } from "./agents/DraftPage";

export function AgentDraft() {
  const { draftId, step } = useParams();
  return draftId === undefined ? null : <DraftPage draftId={draftId} step={step} />;
}
