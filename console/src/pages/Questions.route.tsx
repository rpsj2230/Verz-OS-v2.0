/**
 * Questions and gaps, at the screen's key.
 *
 * Task ids: M27.10.1
 */

import type { PageRoutes } from "../routes/page";
import { Questions } from "./Questions";

export const routes: PageRoutes = [
  { path: "questions", element: <Questions /> },
];
