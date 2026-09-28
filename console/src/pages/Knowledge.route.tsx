/**
 * Knowledge, SCREEN 7, at the screen's own key, `library`: the list, and one document's page with
 * its three views at their own addresses.
 *
 * Task ids: M27.10.1, M27.15.40, M27.16.1
 */

import type { PageRoutes } from "../routes/page";
import { Knowledge } from "./Knowledge";
import { KnowledgeDocument } from "./KnowledgeDocument";

export const routes: PageRoutes = [
  { path: "library", element: <Knowledge /> },
  { path: "library/:itemId", element: <KnowledgeDocument /> },
  { path: "library/:itemId/:view", element: <KnowledgeDocument /> },
];
