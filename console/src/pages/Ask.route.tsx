/**
 * Ask. One path and no parameter, which is the whole of what this route has to get right: a
 * question is the most sensitive value in the request and travels in a POST body, so there is no
 * address that could carry one.
 *
 * Task ids: M27.10.1
 */

import type { OwnWorkEntry, PageRoutes } from "../routes/page";
import { Ask } from "./Ask";

export const routes: PageRoutes = [
  { path: "ask", element: <Ask /> },
];

export const ownWork: OwnWorkEntry = { to: "/ask", label: "Ask", order: 10 };
