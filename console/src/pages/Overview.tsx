/**
 * The index route's page, rebuilt on the page kit in `pages/overview/`, and the one heading every
 * older page puts over a failure.
 *
 * The page itself is `overview/OverviewPage.tsx`; this file keeps the name the route file and the
 * older pages import, so moving the page moved no import anywhere else.
 *
 * Task ids: M27.16.1
 */

import { THAT_DID_NOT_WORK } from "../ui/FailureNotice";
import { OverviewPage } from "./overview/OverviewPage";

/** The one heading over any failure. The API's own sentence goes underneath it. */
export const SOMETHING_DID_NOT_WORK = THAT_DID_NOT_WORK;

export const Overview = OverviewPage;
