/**
 * One document's page, at `/library/{id}` and `/library/{id}/{view}`. The page is
 * `knowledge/KnowledgeDetailPage.tsx`, SCREEN 14's shape on the shared page kit; this reads the
 * address and hands it over.
 *
 * Task ids: M27.15.40, M27.16.1
 */

import { useParams } from "react-router-dom";
import { KnowledgeDetailPage } from "./knowledge/KnowledgeDetailPage";

export function KnowledgeDocument() {
  const { itemId, view } = useParams();
  return itemId === undefined ? null : <KnowledgeDetailPage itemId={itemId} view={view} />;
}
