/**
 * One background job's page, at `/jobs/{name}` and `/jobs/{name}/{view}`. The page itself is
 * `operations/JobDetailPage.tsx`; this module is what the route file loads on demand.
 *
 * Task ids: M27.15.47, M27.16.1
 */

import { useParams } from "react-router-dom";
import { JobDetailPage } from "./operations/JobDetailPage";

export function Job() {
  const { name, view } = useParams();
  return name === undefined ? null : <JobDetailPage control={name} tab={view} />;
}
