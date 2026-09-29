/**
 * Memory, a tab of Learning and memory, read one person at a time. The bare path chooses a person
 * by name, the segment is that person's memory, resolved by the API and never listed, and each of
 * its views has an address of its own.
 *
 * Task ids: M27.10.1, M27.16.1
 */

import type { PageRoutes } from "../routes/page";
import { Memory } from "./Memory";

export const routes: PageRoutes = [
  { path: "memory", element: <Memory /> },
  { path: "memory/:subject", element: <Memory /> },
  { path: "memory/:subject/:view", element: <Memory /> },
];
