/**
 * The Audit log, one subject's page and the check of the chain. The ledger's filters are query
 * parameters, so a colleague can be sent the view and the back button undoes a filter; a subject and
 * its view are path segments, so a link from the Overview's activity opens that subject.
 *
 * Task ids: M27.10.1, M27.16.1, M32.5.2.3
 */

import { lazy } from "react";
import type { PageRoutes } from "../routes/page";
import { Audit } from "./Audit";
import { AuditSubject } from "./Audit";
import { VerifyLedger } from "./Audit";

/**
 * Loaded on demand: the trace page draws the trace graph, whose canvas library is one nobody who
 * reads the ledger should download. `tests/bundle-split.test.ts` walks the static graph from
 * `main.tsx` and fails when it is reachable.
 */
const TraceRead = lazy(async () => ({ default: (await import("./audit/TracePage")).TracePage }));

export const routes: PageRoutes = [
  { path: "audit", element: <Audit /> },
  { path: "audit/verify", element: <VerifyLedger /> },
  { path: "audit/trace", element: <TraceRead /> },
  { path: "audit/trace/:traceId", element: <TraceRead /> },
  { path: "audit/subject/:kind/:id", element: <AuditSubject /> },
  { path: "audit/subject/:kind/:id/:view", element: <AuditSubject /> },
];
