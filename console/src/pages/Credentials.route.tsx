/**
 * Secrets and credentials: every vault slot the install declares, and one slot's own page.
 *
 * Task ids: M27.11.10, M27.16.1
 */

import type { PageRoutes } from "../routes/page";
import { Credential } from "./Credential";
import { CredentialsPage } from "./credentials/CredentialsPage";

export const routes: PageRoutes = [
  { path: "credentials", element: <CredentialsPage /> },
  { path: "credentials/:family/:name", element: <Credential /> },
  { path: "credentials/:family/:name/:view", element: <Credential /> },
];
