/**
 * Secrets and credentials: the vault's seal, every slot, run-token leases and audit shipping.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Vault } from "./Vault";

export const routes: PageRoutes = [
  { path: "vault", element: <Vault /> },
];
