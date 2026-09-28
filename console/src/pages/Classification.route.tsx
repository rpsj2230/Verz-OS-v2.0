/**
 * Fields and records: the classification of a document's columns. The document and the column are
 * path segments, and the bare path is where somebody arrives from the menu.
 *
 * Loaded on demand, for the records screen's reason: it mounts the same two libraries.
 *
 * Task ids: M27.10.1
 */

import { lazy } from "react";
import type { PageRoutes } from "../routes/page";

const Classification = lazy(async () => ({ default: (await import("./Classification")).Classification }));

export const routes: PageRoutes = [
  { path: "classification", element: <Classification /> },
  { path: "classification/:entity", element: <Classification /> },
  { path: "classification/:entity/:column", element: <Classification /> },
];
