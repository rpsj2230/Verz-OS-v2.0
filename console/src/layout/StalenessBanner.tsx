/**
 * The frame's one line about a page read from a copy of the database that is behind (M36.1.2.3).
 *
 * The sentence is the API's own and is drawn as sent,
 * once, above whichever page is showing. Nothing is drawn while what the page shows is current,
 * which is nearly always: a read of the primary carries no banner, so a banner on a current page
 * would teach people to ignore the one that matters.
 *
 * Task ids: M36.1.2.3
 */

import { useStaleness } from "../api/staleness";
import { Note } from "../components/kit";

export function StalenessBanner() {
  const said = useStaleness();
  return said === null ? null : (
    <div data-slot="staleness-banner" className="px-4 pt-2">
      <Note>{said}</Note>
    </div>
  );
}
