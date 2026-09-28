/**
 * What a page's route file declares: the addresses it answers at, and whether it is part of the
 * reader's own work.
 *
 * **Every page declares its own routes in its own file**, `src/pages/<Page>.route.tsx`, and
 * `routes/registry.ts` collects them. Until 2026-09-28 every route was a line in `App.tsx` and every
 * menu entry a line in `layout/Shell.tsx`, so every pull request that added a page edited the same
 * two lists, and on that day two of them jammed on it. A file per page is a file nobody else edits.
 *
 * **The menu is not declared here, except for the reader's own work.** Which administrative
 * screens a reader is offered is the API's answer (`brain.console.department_console`), so an
 * administrative page's menu entry is a line in that Python declaration and never a line in the
 * browser. The own-work group is different: it is drawn before the API has answered, because
 * asking, deciding an approval and reading records are the reader's own work on every console, so
 * a page that belongs in it says so here with `ownWork`.
 *
 * **A lazy page is split in its route file, not in the registry.** A route file is imported eagerly
 * by the registry, so a page that mounts a heavy library is written as a `lazy(...)` import in its
 * route file and the static graph from `main.tsx` stops there. `tests/bundle-split.test.ts` follows
 * the registry's eager glob into every route file and fails when one reaches a heavy library
 * without a dynamic import.
 *
 * Task ids: M27.10.1
 */

import type { RouteObject } from "react-router-dom";

/** Every address one page answers at, under the shell, relative to the root. */
export type PageRoutes = readonly RouteObject[];

/** A page that is part of the reader's own work, drawn in the menu before the API has answered. */
export interface OwnWorkEntry {
  /** The page's address, which must be one of its own routes. */
  readonly to: string;
  /** The menu label, which `brain.ops.console_design` compares with SCREEN 1's Use group. */
  readonly label: string;
  /** Where it sits in the group, lowest first. Numbers, so two files never contend for a line. */
  readonly order: number;
}

/** What a route file exports. */
export interface RouteFile {
  readonly routes: PageRoutes;
  readonly ownWork?: OwnWorkEntry;
}
