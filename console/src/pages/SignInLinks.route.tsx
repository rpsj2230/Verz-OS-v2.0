/**
 * Sign-in links, a tab of Sign-in, directory and sessions. No registry key: the page cites
 * `brain.console.sign_in_links` instead.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { SignInLinks } from "./SignInLinks";

export const routes: PageRoutes = [
  { path: "sign-in-links", element: <SignInLinks /> },
];
