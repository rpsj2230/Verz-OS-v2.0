/**
 * Which page file draws an address, and whether that page is built on the shared parts.
 *
 * The register of console pages (`docs/console-pages.json`) states, for each primary page, whether
 * it is built on the page kit. A statement a person types is a statement that drifts, so
 * `tests/console-pages.test.ts` holds each one against this, which reads the source: the page's
 * own file and the files it reaches inside `src/pages/` are followed, and the page is built on the
 * shared parts when any of them imports one of the kit's page-level parts from `components/kit`.
 *
 * **Followed inside `src/pages/` only.** A page that reaches the kit through a shared component
 * outside its own folder (a table or a dialog that happens to import a kit part) is not built on
 * the kit by that: the page's own shape is what the owner asked to be rebuilt, and nearly every
 * component in the console reaches the kit somewhere, so following every import would answer yes
 * for the pages that were never rebuilt.
 *
 * **The kit's page-level parts are named here and are the three that give a page its shape**: the
 * header every page draws, the list page and the detail page. A page that imports only a card or a
 * chip from the kit has borrowed a piece and is not rebuilt on it.
 *
 * Task ids: M27.16.1, M27.16.4, M27.16.5
 */

import { existsSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { CONSOLE_ROOT, readConsoleFile } from "./repo";
import { consoleSourcePaths } from "./typescript";

/** The kit parts that give a page its shape. Importing any one of them is what "rebuilt" means. */
export const PAGE_SHAPING_PARTS: readonly string[] = ["PageHeader", "ListPage", "DetailPage"];

const IMPORT = /(?:import|export)\s+(?:type\s+)?(?:\{([^}]*)\}|\*\s+as\s+\w+|\w+)?\s*(?:from\s*)?["'](\.[^"']*)["']|import\(\s*["'](\.[^"']*)["']\s*\)/g;

/** Resolve a relative import from `fromFile` to a file under `console/`, or undefined for none. */
function resolveImport(fromFile: string, specifier: string): string | undefined {
  const base = resolve(CONSOLE_ROOT, dirname(fromFile), specifier);
  for (const candidate of [`${base}.tsx`, `${base}.ts`, join(base, "index.tsx"), join(base, "index.ts")]) {
    if (existsSync(candidate)) {
      return relative(CONSOLE_ROOT, candidate).split("\\").join("/");
    }
  }
  return undefined;
}

/**
 * The page file drawing each address, from `App.tsx` and every page's route file.
 *
 * `routeTable.drawnScreens` answers the same for the pages imported by a bare `./pages/Name`; some
 * pages are drawn by a component in a folder of their own, so this reads every relative import in
 * those files, and an element it cannot place is left out rather than guessed.
 */
export function pageFiles(): Map<string, string> {
  const sources = ["src/App.tsx", ...consoleSourcePaths("src/pages").filter((one) => one.endsWith(".route.tsx"))];
  const found = new Map<string, string>();
  for (const file of sources) {
    const text = readConsoleFile(file);
    const fileOf = new Map<string, string>();
    for (const one of text.matchAll(/import\s*\{([^}]*)\}\s*from\s*"(\.[^"]*)"/g)) {
      const target = resolveImport(file, one[2] as string);
      if (target === undefined) {
        continue;
      }
      for (const name of (one[1] as string).split(",")) {
        const bare = name.trim().split(/\s+as\s+/).pop() ?? "";
        if (bare !== "") {
          fileOf.set(bare, target);
        }
      }
    }
    for (const one of text.matchAll(/const\s+(\w+)\s*=\s*lazy\([^;]*?import\(\s*"(\.[^"]*)"\s*\)/gs)) {
      const target = resolveImport(file, one[2] as string);
      if (target !== undefined) {
        fileOf.set(one[1] as string, target);
      }
    }
    for (const one of text.matchAll(/\{\s*(?:path:\s*"([^"]*)"|index:\s*true),\s*element:\s*\(?\s*<(\w+)/g)) {
      const address = one[1] === undefined ? "/" : one[1] === "" ? "/" : `/${one[1]}`;
      const target = fileOf.get(one[2] as string);
      if (target !== undefined && !found.has(address)) {
        found.set(address, target);
      }
    }
  }
  return found;
}

/** The files a page reaches inside `src/pages/`, its own included, by following relative imports. */
export function pageClosure(entry: string): string[] {
  const seen = new Set<string>();
  const queue = [entry];
  while (queue.length > 0) {
    const file = queue.pop() as string;
    if (seen.has(file) || !file.startsWith("src/pages/")) {
      continue;
    }
    seen.add(file);
    const text = readConsoleFile(file);
    for (const one of text.matchAll(IMPORT)) {
      const specifier = one[2] ?? one[3];
      if (specifier === undefined) {
        continue;
      }
      const target = resolveImport(file, specifier);
      if (target !== undefined) {
        queue.push(target);
      }
    }
  }
  return [...seen].sort();
}

/** Whether `file` imports one of `parts` from the kit. */
export function importsKitPart(file: string, parts: readonly string[] = PAGE_SHAPING_PARTS): boolean {
  const text = readConsoleFile(file);
  for (const one of text.matchAll(/import\s*(?:type\s*)?\{([^}]*)\}\s*from\s*"([^"]*components\/kit(?:\/[^"]*)?)"/g)) {
    const names = (one[1] as string).split(",").map((name) => name.trim().split(/\s+as\s+/)[0] as string);
    if (names.some((name) => parts.includes(name))) {
      return true;
    }
  }
  return false;
}

/** Whether the page drawing `address` is built on the kit's page-shaping parts. Undefined when the address is not drawn by a file this can place. */
export function builtOnSharedParts(address: string): boolean | undefined {
  const entry = pageFiles().get(address);
  if (entry === undefined) {
    return undefined;
  }
  return pageClosure(entry).some((file) => importsKitPart(file));
}
