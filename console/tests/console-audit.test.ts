/**
 * The console audit is complete, every judgement in it is checked against the code, and
 * `docs/console-audit.md` is what the code says today.
 *
 * `docs/admin-console.md` asks for an audit before the console is called done, and says what it is:
 * everything an administrator would need to manage, read out of the schema, the modules, the routes
 * and the settings, compared screen by screen with what the console serves, and each gap built or
 * recorded with its reason. `support/consoleAudit.ts` holds the judgement and renders the document;
 * this file is why the document can be believed.
 *
 * **Complete both ways.** Every table, installation value, route under `/api/v1` and `/setup`, and
 * console address is claimed by an area or excused with a reason, and nothing is claimed that does
 * not exist, so a table added next month fails here until somebody says what it is for.
 *
 * **Every write followed.** Every call `support/writes.ts` finds is mapped to the routes it can
 * reach, the mapping is proved by building the address with the function the call uses, and every
 * write route has a row, an audit entry and a behaviour, each a Python test that is found by name in
 * its file or a reason there is none.
 *
 * **Current.** Every rendered file must equal its file in `docs/console-audit/`, and nothing else may
 * sit there. With `WRITE_CONSOLE_AUDIT=1` in the environment the files are written instead, and a
 * file nothing renders any more is removed, which is how they are regenerated. One file per area
 * rather than one document since 2026-09-28, so that two console changes meet in the audit only
 * when they touch the same area: see `renderAudit`.
 *
 * Task ids: M27.8.1, M27.8.17, M27.10.1
 */

import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, test } from "vitest";
import { apiDocument } from "./support/openapi";
import { PAGES } from "./support/pageCases";
import { REPO_ROOT, readConsoleFile, readRepoFile } from "./support/repo";
import {
  AREAS,
  AUDIT_DIRECTORY,
  AUDIT_INDEX,
  NOT_ADMINISTERED,
  PROOFS,
  READ_AFTER_AN_ACTION,
  WRITE_ROUTES,
  claims,
  declaredRoutes,
  inventory,
  renderAudit,
  standardAreas,
  templateOf,
  type Measured,
} from "./support/consoleAudit";
import { consoleSourcePaths, staticImportGraph } from "./support/typescript";
import { everyWrite } from "./support/writes";

/**
 * Every address the route table registers, read from `App.tsx` and every page's route file, with
 * the page file drawing it.
 */
function screens(): Map<string, string> {
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

/**
 * Every file a page's static imports reach, the page among them. A page that imports nothing is
 * itself alone, which `staticImportGraph` refuses to answer because for an entry it means the walk
 * broke; here it only means the page is one file, as the not-found page is.
 */
const reached = new Map<string, readonly string[]>();

function reachedFrom(page: string): readonly string[] {
  const known = reached.get(page);
  if (known !== undefined) {
    return known;
  }
  // A thin route module that only re-exports its page (`export { X } from "./x/XPage"`) reaches
  // the page's directory as surely as one that imports it.
  const local = /^(?:import|export) [^;]*from "\.{1,2}\//m.test(readConsoleFile(page));
  const found = local ? staticImportGraph(page).files : [page];
  reached.set(page, found);
  return found;
}

/**
 * The addresses a source file is drawn at: its own, or those of every page whose static imports
 * reach it. Followed through the graph rather than one import deep, because a page rebuilt on the
 * kit is a thin route module over a directory of its own (`pages/agents/`), and the components that
 * write are imported from there.
 */
function addressesOf(file: string, drawn: Map<string, string>): string[] {
  const direct = [...drawn].filter(([, page]) => page === file).map(([address]) => address);
  if (direct.length > 0) {
    return direct;
  }
  return [...drawn]
    .filter(([, page]) => page.startsWith("src/") && reachedFrom(page).includes(file))
    .map(([address]) => address);
}

function measure(): Measured {
  const document = apiDocument();
  const drawn = screens();
  const readBy: Record<string, string[]> = {};
  for (const [pattern, page] of Object.entries(PAGES)) {
    for (const path of Object.keys(page.answers)) {
      const template = templateOf(document, path);
      if (template !== null) {
        (readBy[`GET ${template}`] ??= []).push(pattern);
      }
    }
  }
  for (const [route, read] of Object.entries(READ_AFTER_AN_ACTION)) {
    (readBy[route] ??= []).push(read.screen);
  }
  const writtenBy: Record<string, string[]> = {};
  const writes = everyWrite();
  for (const write of writes) {
    for (const one of WRITE_ROUTES[write.key] ?? []) {
      writtenBy[one.route] = [...new Set([...(writtenBy[one.route] ?? []), ...addressesOf(write.file, drawn)])].sort();
    }
  }
  const stock = inventory();
  return {
    routes: declaredRoutes(document),
    tables: [...stock.tables],
    installation: stock.installation.map((one) => one.name),
    screens: [...drawn.keys()].sort(),
    readBy: Object.fromEntries(Object.entries(readBy).map(([route, by]) => [route, [...new Set(by)].sort()])),
    writtenBy,
    writeCount: writes.length,
  };
}

/** Every leaf id the work breakdown holds. */
function leaves(): Set<string> {
  const wbs = JSON.parse(readRepoFile("docs/wbs.json")) as { modules: { leaf_ids: string[] }[] };
  return new Set(wbs.modules.flatMap((one) => one.leaf_ids));
}

/** The body of one Python test function, from its `def` to the next top-level statement. */
function pythonTest(reference: string): { readonly file: string; readonly body: string } {
  const [file, name] = reference.split("::") as [string, string];
  const text = readRepoFile(file);
  const start = text.search(new RegExp(`^(async )?def ${name}\\(`, "m"));
  if (start < 0) {
    throw new Error(`${reference} is not a test in ${file}.`);
  }
  const rest = text.slice(start + 1);
  const end = rest.search(/^\S/m);
  return { file: text, body: end < 0 ? rest : rest.slice(0, end) };
}

describe("the console audit", () => {
  test("the areas are the standard's own bullets, in its order, and each is judged", () => {
    // What breaks if this is deleted: the audit answering a list somebody edited rather than the
    // owner's standard, so a bullet added to docs/admin-console.md is never measured.
    expect(Object.keys(AREAS)).toEqual(standardAreas());
  }, 60_000);

  test("every table, installation value, route and address is claimed by an area or excused, and nothing else is", () => {
    // What breaks if this is deleted: a table or a route that exists and that nobody asked whether
    // an administrator needs to manage, which is the audit's whole question left unasked for it.
    const measured = measure();
    const areas = Object.values(AREAS);
    const excused = new Set(Object.keys(NOT_ADMINISTERED));

    const unclaimedTables = measured.tables.filter((one) => !excused.has(one) && !areas.some((area) => area.tables.includes(one)));
    const unclaimedValues = measured.installation.filter((one) => !areas.some((area) => area.installation.includes(one)));
    const unclaimedRoutes = measured.routes.filter((one) => !excused.has(one) && !areas.some((area) => area.routes.some((claim) => claims(claim, one))));
    const unclaimedScreens = measured.screens.filter((one) => !excused.has(one) && !areas.some((area) => area.screens.includes(one)));
    expect({ unclaimedTables, unclaimedValues, unclaimedRoutes, unclaimedScreens }).toEqual({
      unclaimedTables: [],
      unclaimedValues: [],
      unclaimedRoutes: [],
      unclaimedScreens: [],
    });

    for (const [name, area] of Object.entries(AREAS)) {
      expect(area.tables.filter((one) => !measured.tables.includes(one)), `${name} claims a table that is not there`).toEqual([]);
      expect(area.installation.filter((one) => !measured.installation.includes(one)), name).toEqual([]);
      expect(area.screens.filter((one) => !measured.screens.includes(one)), name).toEqual([]);
      expect(area.routes.filter((claim) => !measured.routes.some((route) => claims(claim, route))), name).toEqual([]);
    }
    for (const [what, why] of Object.entries(NOT_ADMINISTERED)) {
      const exists = measured.tables.includes(what) || measured.routes.includes(what) || measured.screens.includes(what);
      expect(exists, `${what} is excused and does not exist`).toBe(true);
      expect(areas.some((area) => area.tables.includes(what) || area.screens.includes(what) || area.routes.some((claim) => claims(claim, what))), `${what} is both claimed and excused`).toBe(false);
      expect(why.split(" ").length, what).toBeGreaterThan(5);
    }
  }, 60_000);

  test("every gap names a leaf the work breakdown holds or says why it is not one", () => {
    // What breaks if this is deleted: a gap written down and pointed at nothing, which is the gap
    // recorded and forgotten in the same sentence.
    const known = leaves();
    for (const [name, area] of Object.entries(AREAS)) {
      for (const gap of area.gaps) {
        expect(gap.leaf === undefined ? gap.because !== undefined && gap.because.split(" ").length > 8 : known.has(gap.leaf), `${name}: ${gap.what}`).toBe(true);
      }
    }
    for (const [route, proofs] of Object.entries(PROOFS)) {
      for (const proof of [proofs.row, proofs.audit, proofs.behaviour]) {
        if ("leaf" in proof && proof.leaf !== undefined) {
          expect(known.has(proof.leaf), route).toBe(true);
        }
      }
    }
  }, 60_000);

  test("every write a screen sends is mapped to the routes it reaches, and the mapping is built by the call's own function", () => {
    // What breaks if this is deleted: a write the console sends that the proofs below never follow,
    // or a mapping that names a route the call cannot reach, which is a proof about the wrong write.
    const document = apiDocument();
    const writes = everyWrite();
    expect(writes.map((one) => one.key).filter((key) => WRITE_ROUTES[key] === undefined)).toEqual([]);
    expect(Object.keys(WRITE_ROUTES).filter((key) => !writes.some((one) => one.key === key))).toEqual([]);
    for (const [key, routes] of Object.entries(WRITE_ROUTES)) {
      const site = writes.find((one) => one.key === key);
      const source = site === undefined ? "" : readConsoleFile(site.file);
      for (const one of routes) {
        const [method, template] = one.route.split(" ") as [string, string];
        const built = one.versioned ? `/api/v1${one.built}` : one.built;
        expect(templateOf(document, built), `${key} builds ${built}`).toBe(template);
        const operations = (document["paths"] as Record<string, Record<string, unknown>>)[template] ?? {};
        expect(Object.keys(operations), one.route).toContain(method.toLowerCase());
        expect(key.includes(one.spelled) || source.includes(one.spelled), `${key} does not use ${one.spelled}`).toBe(true);
        expect(site?.method === method || (site?.method === "STREAM" && method === "POST"), key).toBe(true);
      }
    }
    const reached = new Set(Object.values(WRITE_ROUTES).flatMap((routes) => routes.map((one) => one.route)));
    expect([...reached].sort()).toEqual(Object.keys(PROOFS).sort());
  }, 60_000);

  test("every read made after an action is built by the function the console uses", () => {
    // What breaks if this is deleted: the audit saying a route is called by a screen because a table
    // here says so, when nothing in the console builds its address.
    const document = apiDocument();
    const drawn = screens();
    for (const [route, read] of Object.entries(READ_AFTER_AN_ACTION)) {
      const address = read.versioned === false ? read.built : `/api/v1${read.built}`;
      expect(`GET ${templateOf(document, address) ?? ""}`, route).toBe(route);
      const page = drawn.get(read.screen) ?? "";
      const uses = page === "" ? [] : reachedFrom(page);
      const word = new RegExp(`\\b${read.spelled}\\b`);
      expect(uses.some((file) => word.test(readConsoleFile(file).replace(/^import[^;]*;/gm, ""))), route).toBe(true);
    }
  }, 60_000);

  test("every proof names a Python test that exists, and says truly whether it needs a database", () => {
    // What breaks if this is deleted: a proof table citing a test that was renamed, so the claim that
    // a write reaches the system rests on nothing, or a proof marked as runnable anywhere that in
    // fact needs the scratch Postgres only CI has.
    for (const [route, proofs] of Object.entries(PROOFS)) {
      for (const proof of [proofs.row, proofs.audit, proofs.behaviour]) {
        if ("test" in proof) {
          const found = pythonTest(proof.test);
          const imports = /from tests\.fixtures\.scratch_postgres import \(?([^)\n]*(?:\n[^)]*)*)\)?/.exec(found.file)?.[1] ?? "";
          const names = imports.split(/[\s,()]+/).filter((one) => /^[a-z_]+$/.test(one));
          if (proof.database) {
            expect(names.length, `${route}: ${proof.test} is marked as needing a database and its file imports no scratch database`).toBeGreaterThan(0);
          } else {
            expect(names.filter((one) => new RegExp(`\\b${one}\\(`).test(found.body)), `${route}: ${proof.test} uses a scratch database`).toEqual([]);
          }
        } else {
          const reason = "none" in proof ? proof.none : proof.notApplicable;
          expect(reason.split(" ").length, route).toBeGreaterThan(5);
        }
      }
    }
  }, 60_000);

  test("docs/console-audit/ is what the code says today, file by file, and holds nothing else", () => {
    // What breaks if this is deleted: the files go stale the day after they are written, which is
    // the reason they are generated at all, and a file for an area that was renamed stays behind
    // and is served beside its successor.
    const rendered = renderAudit(measure());
    const directory = join(REPO_ROOT, ...AUDIT_DIRECTORY.split("/"));
    if (process.env["WRITE_CONSOLE_AUDIT"] === "1") {
      mkdirSync(directory, { recursive: true });
      for (const name of readdirSync(directory)) {
        if (!(name in rendered)) {
          rmSync(join(directory, name));
        }
      }
      for (const [name, text] of Object.entries(rendered)) {
        writeFileSync(join(directory, name), text, "utf8");
      }
    }
    expect(existsSync(join(directory, AUDIT_INDEX)), `${AUDIT_DIRECTORY} has not been generated`).toBe(true);
    expect(readdirSync(directory).sort()).toEqual(Object.keys(rendered).sort());
    for (const [name, text] of Object.entries(rendered)) {
      expect(readFileSync(join(directory, name), "utf8").replace(/\r\n/g, "\n"), name).toBe(text);
      expect(text, name).not.toContain(String.fromCharCode(0x2014));
    }
  }, 60_000);

  test("the files carry every area and every write, so splitting them dropped nothing", () => {
    // What breaks if this is deleted: an area or a write route that no file renders, which reads as
    // an audit with nothing to say about it rather than one that never looked.
    const rendered = renderAudit(measure());
    const all = Object.values(rendered).join("\n");
    for (const name of Object.keys(AREAS)) {
      expect(all, name).toContain(`### ${name}`);
    }
    for (const route of Object.keys(PROOFS)) {
      expect(all, route).toContain(`| \`${route}\` |`);
    }
    expect(Object.keys(rendered)).toHaveLength(Object.keys(AREAS).length + 2);
  }, 60_000);
});
