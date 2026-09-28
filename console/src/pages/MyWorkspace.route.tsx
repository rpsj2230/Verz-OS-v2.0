/**
 * My workspace, SCREEN 12. One path and no parameter, because the page is about the person asking
 * and `brain.mine_routes` takes nothing that could name anybody else.
 *
 * Task ids: M27.10.1
 */

import type { OwnWorkEntry, PageRoutes } from "../routes/page";
import { MyWorkspace } from "./MyWorkspace";

export const routes: PageRoutes = [
  { path: "me", element: <MyWorkspace /> },
];

export const ownWork: OwnWorkEntry = { to: "/me", label: "My workspace", order: 20 };
