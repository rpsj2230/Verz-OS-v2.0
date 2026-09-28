/**
 * Every page's routes, collected from the route files, and the group of the reader's own work.
 *
 * **Collected by a glob, so adding a page edits no shared file.** `import.meta.glob` with `eager`
 * is a static import of every `src/pages/*.route.tsx` that the bundler writes out at build time,
 * so a new page is a new route file and nothing else in the browser changes: not `App.tsx`, not
 * `layout/Shell.tsx`, not this file. Rejected: a list here that each page appends to, which is the
 * same shared line two pull requests contend for, moved one file along.
 *
 * **The order is the file names', and it does not matter which it is.** React Router ranks routes
 * by how specific their paths are, not by where they sit in the table, so the table is sorted only
 * so that it is the same table on every build.
 *
 * **What decides the menu is not here.** The administrative groups are the API's answer
 * (`layout/navigationQuery.ts`); the own-work group below is the one the shell draws before that
 * answer arrives, built from each route file's `ownWork` and ordered by its number.
 *
 * Task ids: M27.10.1
 */

import type { RouteObject } from "react-router-dom";
import type { NavGroup } from "../layout/navigationQuery";
import type { RouteFile } from "./page";

const FILES = import.meta.glob<RouteFile>("../pages/*.route.tsx", { eager: true });

/** The heading of the reader's own work, which `brain.ops.console_design` reads from here. */
export const OWN_WORK_HEADING = "Use";

/** The stable key of that group, beside the served groups' keys. */
export const OWN_WORK_KEY = "use";

/** The route files, by path, in a fixed order. */
function files(): RouteFile[] {
  return Object.keys(FILES)
    .sort()
    .map((path) => FILES[path])
    .filter((one): one is RouteFile => one !== undefined);
}

/** Every route every page declares, for the shell's children. */
export const PAGE_ROUTES: readonly RouteObject[] = files().flatMap((one) => [...one.routes]);

/** The reader's own work, drawn on every console and before the API has answered. */
export const OWN_WORK: NavGroup = {
  key: OWN_WORK_KEY,
  heading: OWN_WORK_HEADING,
  sections: files()
    .flatMap((one) => (one.ownWork === undefined ? [] : [one.ownWork]))
    .sort((a, b) => a.order - b.order)
    .map((one) => ({ to: one.to, label: one.label, tabs: [] })),
};
