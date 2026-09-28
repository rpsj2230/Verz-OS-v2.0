/**
 * The Scopes tab of Roles and permissions, at `/scopes`. The page is `roles/ScopesPage.tsx`, built on
 * the shared page kit, where scopes are created, renamed and retired.
 *
 * Task ids: M27.7.4, M27.11.1, M27.16.1
 */

import { ScopesPage } from "./roles/ScopesPage";

// An import rather than a re-export, so a walk of this page's imports reaches the writes it draws.
export { ScopesPage as Scopes };
export { SCOPES_CRUMB as SCOPES_HEADING, SCOPES_LEDE } from "./roles/ScopesPage";
