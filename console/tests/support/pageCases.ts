/**
 * Every page the console registers, the address it is mounted at, and what the stand-in API answers
 * it with.
 *
 * Written once and read by several tests. `tests/phone-width.test.tsx` holds every page to a phone's
 * width with these answers, and `tests/screen-states.test.tsx` mounts the same pages in the four
 * states a request can leave them in, answering the empty state with these same bodies with every
 * list emptied. Two copies would be two sets of fixtures that drift, and the drift would be
 * invisible: a page whose answer shape changed would be fixed in one test and go on passing in the
 * other against a body the API no longer sends.
 *
 * **Each module keeps its own cases, and this file only collects them.** A case lives in
 * `pageCases/<module>.ts`, named for the first segment of its address (`/` is `overview`, `/*` is
 * `not-found`), which exports `PAGES` and, when its pages ask a route that has not landed,
 * `AWAITED_ROUTES`. An eager `import.meta.glob` reads every such file, as `src/routes/registry.ts`
 * reads the route files, so adding or rebuilding a page edits no file another page's change also
 * edits. Rejected: one object every page appended to, which is what this was until 2026-09-29. Any
 * two console pull requests met at its last lines whatever they built, and about ten of them were
 * rebased two to four times each in one day.
 *
 * **The file name is checked, not trusted.** A case in a file its address does not name, or an
 * address two files both claim, is refused as the files are read. A catch-all file would be the
 * shared list again, and a second case for one address would silently replace the first, which the
 * one object literal used to refuse at compile time.
 *
 * Task ids: none
 */

import type { PageCase } from "./pageFixtures";

export { RUNG_ID, UNBROKEN, type PageCase } from "./pageFixtures";

/** What one module's file under `pageCases/` exports. */
interface CaseFile {
  readonly PAGES: Readonly<Record<string, PageCase>>;
  readonly AWAITED_ROUTES?: Readonly<Record<string, string>>;
}

const FILES = import.meta.glob<CaseFile>("./pageCases/*.ts", { eager: true });

/** The module an address belongs to, which names the file its case lives in. */
export function moduleOf(pattern: string): string {
  if (pattern === "/") {
    return "overview";
  }
  if (pattern === "/*") {
    return "not-found";
  }
  return pattern.split("/")[1] ?? pattern;
}

/** One export of every module file, merged, refusing a key two files both hold. */
function collect<T>(pick: (file: CaseFile) => Readonly<Record<string, T>> | undefined, byAddress: boolean): Readonly<Record<string, T>> {
  const merged: Record<string, T> = {};
  const heldBy = new Map<string, string>();
  for (const path of Object.keys(FILES).sort()) {
    const file = FILES[path];
    const module = /([^/]+)\.ts$/.exec(path)?.[1] ?? path;
    for (const [key, value] of Object.entries((file === undefined ? undefined : pick(file)) ?? {})) {
      const earlier = heldBy.get(key);
      if (earlier !== undefined) {
        throw new Error(`${key} is held by both ${earlier} and ${path}; one address has one case.`);
      }
      if (byAddress && moduleOf(key) !== module) {
        throw new Error(`The case for ${key} belongs in pageCases/${moduleOf(key)}.ts, not ${path}.`);
      }
      heldBy.set(key, path);
      merged[key] = value;
    }
  }
  return merged;
}

/**
 * Addresses a page asks that the API document does not declare yet, because another package is
 * building the route, and why each is answered here anyway.
 *
 * A page case must answer every request a page makes, or `screen-states` reports the page as asking
 * for something nobody answers; and `long-lists` reads every answered address against the API
 * document. The agent pages ask the shared stats route (`agents/agentStats.ts`) that the stats
 * package serves, so it is answered here in the shape that package was briefed with, and listed so
 * the document check knows it is expected rather than a typo. Delete the entry when the route lands.
 * Each module lists its own, beside its cases.
 */
export const AWAITED_ROUTES: Readonly<Record<string, string>> = collect((file) => file.AWAITED_ROUTES, false);

/** Whether an address is one of `AWAITED_ROUTES`. */
export function awaited(path: string): boolean {
  return Object.keys(AWAITED_ROUTES).some((route) =>
    new RegExp(`^${route.replace(/\{[^}]+\}/g, "[^/]+")}$`).test(path),
  );
}

/** Every page case, from every module's file. */
export const PAGES: Readonly<Record<string, PageCase>> = collect((file) => file.PAGES, true);
