/**
 * Referred to me: the caller's own referrals, read by the person named and needing no grant.
 *
 * Task ids: M27.10.1
 */

import type { OwnWorkEntry, PageRoutes } from "../routes/page";
import { Referrals } from "./Referrals";

export const routes: PageRoutes = [
  { path: "referrals", element: <Referrals /> },
];

export const ownWork: OwnWorkEntry = { to: "/referrals", label: "Referred to me", order: 60 };
