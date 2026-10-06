/**
 * The page a vendor sends a person back to after they consented to a source there (M11.8.6). Under
 * the shell's sign-in, so the answer is handed over with the person's own session. See
 * `connectors/consentAtVendor.ts`.
 *
 * Task ids: M11.8.6
 */

import type { PageRoutes } from "../routes/page";
import { ConnectorConsent } from "./ConnectorConsent";

export const routes: PageRoutes = [{ path: "connector-consent", element: <ConnectorConsent /> }];
