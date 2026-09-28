/**
 * Skills: the library at `/skills`, and one skill at `/skills/{name}` with its Profile and About
 * views at `/skills/{name}/profile` and `/skills/{name}/about`. The name is resolved against the
 * Skills page's own answer rather than a route of its own.
 *
 * One skill's page loads on demand, so somebody who only reads the list does not download it.
 *
 * Task ids: M27.10.1, M27.16.1
 */

import { lazy } from "react";
import type { PageRoutes } from "../routes/page";
import { Skills } from "./Skills";

const Skill = lazy(async () => ({ default: (await import("./Skill")).Skill }));

export const routes: PageRoutes = [
  { path: "skills", element: <Skills /> },
  { path: "skills/:name", element: <Skill /> },
  { path: "skills/:name/:view", element: <Skill /> },
];
