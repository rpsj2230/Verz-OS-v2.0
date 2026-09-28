/**
 * Access review, at the screen's own key. A decision is a confirmed control on a row, not a page.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { AccessReview } from "./AccessReview";

export const routes: PageRoutes = [
  { path: "access_review", element: <AccessReview /> },
];
