/**
 * The Staff sources page's address in the route table. The page itself is
 * `staff-sources/StaffSourcesPage.tsx`, built on the shared page kit; this module keeps the name
 * `StaffSources.route.tsx` imports, so the route did not have to change for the rebuild.
 *
 * An import and not a bare re-export, so that whatever follows a page's static imports (the console
 * audit's graph) reaches the directory the page is built from.
 *
 * Task ids: M1.6.12, M1.8.6, M1.8.9, M27.7.2, M27.16.1
 */

import { StaffSourcesPage } from "./staff-sources/StaffSourcesPage";

export { STAFF_SOURCES_HEADING, STAFF_SOURCES_LEDE } from "./staff-sources/StaffSourcesPage";

/** The name the route table imports. */
export const StaffSources = StaffSourcesPage;
