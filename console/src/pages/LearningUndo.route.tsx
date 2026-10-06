/**
 * Undo one learning, the page a weekly learning digest links for each thing it names. The segment
 * is the memory's id; the API decides it is the reader's own.
 *
 * Task ids: M16.5.1
 */

import type { PageRoutes } from "../routes/page";
import { LearningUndo } from "./LearningUndo";

export const routes: PageRoutes = [{ path: "me/undo/:memoryId", element: <LearningUndo /> }];
