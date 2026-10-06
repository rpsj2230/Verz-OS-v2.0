/**
 * Corrections, a tab of the Knowledge entry: what somebody said the right answer is, waiting for
 * whoever may add a new version of the document it is about.
 *
 * Task ids: M16.6.5, M16.6.6, M16.7.6
 */

import type { PageRoutes } from "../routes/page";
import { Corrections } from "./Corrections";

export const routes: PageRoutes = [{ path: "corrections", element: <Corrections /> }];
