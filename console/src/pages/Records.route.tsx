/**
 * Records. The entity is a path segment because it is what the screen is about, and the bare path
 * is where somebody arrives from the menu.
 *
 * Loaded on demand. It mounts the table library and the form library, which weigh 608 kB
 * against an application of 267 kB, so an eager import would put them in the first response for
 * everybody, before the sign-in redirect has been decided. `tests/bundle-split.test.ts` walks the
 * static graph from `main.tsx`, through the registry's glob into this file, and fails when either
 * library is reachable without a dynamic import.
 *
 * Task ids: M27.10.1
 */

import { lazy } from "react";
import type { OwnWorkEntry, PageRoutes } from "../routes/page";

const Records = lazy(async () => ({ default: (await import("./Records")).Records }));

export const routes: PageRoutes = [
  { path: "records", element: <Records /> },
  { path: "records/:entity", element: <Records /> },
];

export const ownWork: OwnWorkEntry = { to: "/records", label: "Records", order: 40 };
