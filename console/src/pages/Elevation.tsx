/**
 * Elevation requests' pages, at the names the route file and the tests import. The pages themselves
 * are in `review/`, built on the shared page kit: `ElevationPage.tsx` for the list and the ask, and
 * `RequestPage.tsx` for one request.
 *
 * Task ids: M27.7.8, M27.16.1
 */

import { useParams } from "react-router-dom";
import { RequestPage } from "./review/RequestPage";

export { ElevationPage as Elevation, ELEVATION_HEADING } from "./review/ElevationPage";

/** One request's page, at `/elevation/{request id}`. */
export function ElevationRequest() {
  const { requestId } = useParams();
  return requestId === undefined ? null : <RequestPage key={requestId} requestId={requestId} />;
}
