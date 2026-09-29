/**
 * Retention, legal holds and erasure: four views at their own addresses, one legal hold's page and
 * one erasure request's page.
 *
 * Task ids: M27.10.1, M27.16.1
 */

import type { PageRoutes } from "../routes/page";
import { ErasureRequest, LegalHold, Retention } from "./Retention";

export const routes: PageRoutes = [
  { path: "retention", element: <Retention /> },
  { path: "retention/:view", element: <Retention /> },
  { path: "retention/holds/:holdId", element: <LegalHold /> },
  { path: "retention/erasures/:requestId", element: <ErasureRequest /> },
];
