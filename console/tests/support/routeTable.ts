/**
 * The console's route table, read from the source.
 *
 * Every address the router registers, with the page file that draws it, read from `App.tsx` and each
 * page's `.route.tsx` file rather than from a running router. It lived inside
 * `console-audit.test.ts` until the reference-screen records needed the same answer to "is this a
 * page the console has": two readers of the route table would be two places for it to disagree, so
 * there is one and both tests import it.
 *
 * Task ids: M27.8.1, M27.15.83
 */

import { readConsoleFile } from "./repo";
import { consoleSourcePaths } from "./typescript";

/**
 * Every address the route table registers, read from `App.tsx` and every page's route file, with
 * the page file drawing it.
 */
export function drawnScreens(): Map<string, string> {
  const tables = [
    readConsoleFile("src/App.tsx"),
    ...consoleSourcePaths("src/pages")
      .filter((one) => one.endsWith(".route.tsx"))
      .map((one) => readConsoleFile(one)),
  ];
  const app = tables.join("\n");
  const fileOf = new Map<string, string>();
  for (const found of app.matchAll(/import \{ (\w+) \} from "\.\/(?:pages\/)?(\w+)";/g)) {
    fileOf.set(found[1] as string, `src/pages/${found[2] as string}.tsx`);
  }
  for (const found of app.matchAll(/const (\w+) = lazy\([^;]*?import\("\.\/(?:pages\/)?(\w+)"\)/gs)) {
    fileOf.set(found[1] as string, `src/pages/${found[2] as string}.tsx`);
  }
  const constants: Record<string, string> = { CALLBACK_PATH: "/auth/callback", SIGNED_OUT_PATH: "/signed-out", FIRST_RUN_PATH: "/first-run", STAFF_LIST_RETURN_PATH: "/first-run/staff-list" };
  const drawn = new Map<string, string>();
  for (const found of app.matchAll(/\{\s*(?:path: ("[^"]*"|\w+)|index: true), element: \(?\s*<(\w+)/g)) {
    const raw = found[1];
    const address =
      raw === undefined ? "/" : raw.startsWith('"') ? `/${raw.slice(1, -1)}` : (constants[raw] ?? raw);
    drawn.set(address === "//" ? "/" : address, fileOf.get(found[2] as string) ?? `<${found[2] as string}>`);
  }
  return drawn;
}
