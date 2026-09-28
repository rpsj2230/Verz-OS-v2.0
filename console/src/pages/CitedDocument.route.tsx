/**
 * The document a citation on Ask opens, at the passage in the address's fragment, which no server
 * sees. Under Ask's own address because it is reached from an answer, and never a menu entry: a
 * reader arrives here by following a citation. Eager, because the page mounts neither heavy
 * library and imports no stylesheet of its own.
 *
 * Task ids: M8.1.2
 */

import type { PageRoutes } from "../routes/page";
import { CitedDocument } from "./CitedDocument";

export const routes: PageRoutes = [{ path: "ask/documents/:documentId", element: <CitedDocument /> }];
