/**
 * Automations, the list of every automation a reader may see across the agents they may see. One
 * automation's page is `Automation.route.tsx`.
 *
 * Task ids: M27.12.3, M27.16.1
 */

import type { PageRoutes } from "../routes/page";
import { Automations } from "./Automations";

export const routes: PageRoutes = [{ path: "automations", element: <Automations /> }];
