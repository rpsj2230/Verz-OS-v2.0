/**
 * Memory, a tab of Learning and memory, read one person at a time. The bare path asks for a
 * reference and the segment is that person's memory, resolved by the API and never listed.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Memory } from "./Memory";

export const routes: PageRoutes = [
  { path: "memory", element: <Memory /> },
  { path: "memory/:subject", element: <Memory /> },
];
