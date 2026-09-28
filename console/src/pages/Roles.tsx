/**
 * The Roles tab of Roles and permissions, at `/roles`. The page is `roles/RolesPage.tsx`, built on
 * the shared page kit; this module keeps the name the route file loads.
 *
 * Task ids: M27.11.3, M27.16.1
 */

import { RolesPage } from "./roles/RolesPage";

// An import rather than a re-export, so a walk of this page's imports reaches the writes it draws.
export { RolesPage as Roles };
export { ROLES_HEADING, ROLES_LEDE } from "./roles/RolesPage";
