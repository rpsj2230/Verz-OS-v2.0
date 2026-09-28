/**
 * The Packs tab of Roles and permissions, at `/packs`. The page is `roles/PacksPage.tsx`, built on the
 * shared page kit, where packs are created, versioned, copied and retired.
 *
 * Task ids: M27.15.24, M27.16.1
 */

import { PacksPage } from "./roles/PacksPage";

// An import rather than a re-export, so a walk of this page's imports reaches the writes it draws.
export { PacksPage as Packs };
export { PACKS_CRUMB as PACKS_HEADING, PACKS_LEDE } from "./roles/PacksPage";
