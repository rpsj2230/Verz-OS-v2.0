/**
 * Access review, at the screen's own key, and one holding's page. The kind is in the address because
 * a grant and a pack may share a row id.
 *
 * Task ids: M27.10.1, M27.16.1
 */

import type { PageRoutes } from "../routes/page";
import { AccessReview } from "./AccessReview";
import { Holding } from "./AccessReview";

export const routes: PageRoutes = [
  { path: "access_review", element: <AccessReview /> },
  { path: "access_review/:kind/:rowId", element: <Holding /> },
];
