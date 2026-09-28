/**
 * The Capabilities tab of Roles and permissions, at `/capabilities`. The page is
 * `roles/CapabilitiesPage.tsx`, built on the shared page kit.
 *
 * Task ids: M27.7.6, M27.16.1
 */

import { CapabilitiesPage } from "./roles/CapabilitiesPage";

// An import rather than a re-export, so a walk of this page's imports reaches the writes it draws.
export { CapabilitiesPage as Capabilities };
export { CAPABILITIES_CRUMB as CAPABILITIES_HEADING, CAPABILITIES_LEDE } from "./roles/CapabilitiesPage";
