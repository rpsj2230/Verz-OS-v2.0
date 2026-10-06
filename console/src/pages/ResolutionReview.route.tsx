/**
 * Possible duplicates: the pairs of records waiting for a person to say whether they are one
 * company or person, and the decision. See `brain.resolution_routes`.
 *
 * Task ids: M14.6.4, M14.8.5
 */

import type { PageRoutes } from "../routes/page";
import { ResolutionReview } from "./ResolutionReview";

export const routes: PageRoutes = [{ path: "duplicates", element: <ResolutionReview /> }];
