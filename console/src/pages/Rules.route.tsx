/**
 * Quick answers: the fast-lane rules a department's administrator adds, tries and retires, which
 * answer from the next question. See `brain.rule_routes`.
 *
 * Task ids: M6.5.1
 */

import type { PageRoutes } from "../routes/page";
import { Rules } from "./Rules";

export const routes: PageRoutes = [{ path: "rules", element: <Rules /> }];
